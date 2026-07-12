import json
import logging
import math
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from dotenv import load_dotenv, set_key

from google import genai
from google.genai import types

load_dotenv()
ENV_PATH = ".env"
LOG_FILE = "job.log"

logger = logging.getLogger("uploader")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _fileHandler = logging.FileHandler(LOG_FILE)
    _fileHandler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(_fileHandler)
    _streamHandler = logging.StreamHandler()
    _streamHandler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(_streamHandler)

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)

ARTICLES_DIR = "articles_md"
CHANGED_IDS_FILE = os.path.join(ARTICLES_DIR, "changed_ids.txt")
DOC_MAP_FILE = os.path.join(ARTICLES_DIR, "uploaded_documents.json")

MAX_WORKERS = 20
MAX_TOKENS_PER_CHUNK = 200
MAX_OVERLAP_TOKENS = 20


def estimateTokenCount(text: str) -> int:
    cleaned = re.sub(r"\s+", " ", text).strip()
    return max(1, math.ceil(len(cleaned) / 4))


def estimateChunksForText(text: str) -> int:
    totalTokens = estimateTokenCount(text)
    effectiveStep = MAX_TOKENS_PER_CHUNK - MAX_OVERLAP_TOKENS
    return math.ceil(totalTokens / effectiveStep)


fileSearchStoreName = os.getenv("FILE_SEARCH_STORE_NAME")

if not fileSearchStoreName:
    fileSearchStore = client.file_search_stores.create(
        config={
            "display_name": "optisigns-articles",
            "embedding_model": "models/gemini-embedding-2",
        }
    )
    assert fileSearchStore.name is not None
    fileSearchStoreName = fileSearchStore.name
    set_key(ENV_PATH, "FILE_SEARCH_STORE_NAME", fileSearchStoreName)
    logger.info(f"Created new file search store: {fileSearchStoreName}")
    logger.info(f"Saved FILE_SEARCH_STORE_NAME to {ENV_PATH}")
else:
    logger.info(f"Using existing file search store: {fileSearchStoreName}")

if not fileSearchStoreName.startswith("fileSearchStores/"):
    fileSearchStoreName = f"fileSearchStores/{fileSearchStoreName}"
FILE_SEARCH_STORE_NAME: str = fileSearchStoreName


changedIdsPath = Path(CHANGED_IDS_FILE)
if not changedIdsPath.exists():
    raise SystemExit(
        f"{CHANGED_IDS_FILE} not found. Run the scraper first — it writes "
        f"this file listing which article ids are new/updated this run."
    )

changedIds = [line.strip() for line in changedIdsPath.read_text().splitlines() if line.strip()]

if not changedIds:
    logger.info("No new or updated articles this run. Nothing to upload.")
    raise SystemExit(0)

filenames = [f"{articleId}.md" for articleId in changedIds]

docMapPath = Path(DOC_MAP_FILE)
docMap: dict[str, str] = json.loads(docMapPath.read_text()) if docMapPath.exists() else {}


def deleteOldDocumentIfExists(threadClient: genai.Client, articleId: str) -> None:
    oldDocName = docMap.get(articleId)
    if oldDocName:
        try:
            threadClient.file_search_stores.documents.delete(name=oldDocName, config={"force": True})
            logger.info(f"deleted old document for id {articleId}: {oldDocName}")
        except Exception as e:
            logger.warning(f"could not delete old document for id {articleId}: {e}")


def uploadFile(filename: str) -> tuple[str, int, str | None]:
    threadClient = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    articleId = filename.removesuffix(".md")
    filePath = os.path.join(ARTICLES_DIR, filename)

    deleteOldDocumentIfExists(threadClient, articleId)

    with open(filePath, "r", encoding="utf-8") as f:
        content = f.read()
    estimatedChunks = estimateChunksForText(content)

    operation = threadClient.file_search_stores.upload_to_file_search_store(
        file=filePath,
        file_search_store_name=FILE_SEARCH_STORE_NAME,
        config={
            "display_name": filename,
            "chunking_config": {
                "white_space_config": {
                    "max_tokens_per_chunk": MAX_TOKENS_PER_CHUNK,
                    "max_overlap_tokens": MAX_OVERLAP_TOKENS,
                }
            },
        },
    )

    while not operation.done:
        time.sleep(5)
        operation = threadClient.operations.get(operation)

    documentName = operation.response.document_name if operation.response else None
    return articleId, estimatedChunks, documentName


succeeded = 0
failed = 0
totalEstimatedChunks = 0

with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
    futures = {executor.submit(uploadFile, f): f for f in filenames}
    for future in as_completed(futures):
        filename = futures[future]
        try:
            articleId, chunks, documentName = future.result()
            succeeded += 1
            totalEstimatedChunks += chunks
            if documentName:
                docMap[articleId] = documentName  # remember for next delta run
            logger.info(f"Done ({succeeded}/{len(filenames)}): {filename} -> {documentName} (~{chunks} chunks)")
        except Exception as e:
            failed += 1
            logger.error(f"Failed: {filename} ({e})")


docMapPath.write_text(json.dumps(docMap, indent=2), encoding="utf-8")

store = client.file_search_stores.get(name=FILE_SEARCH_STORE_NAME)

logger.info(
    f"Upload summary: {succeeded} succeeded, {failed} failed out of {len(filenames)} changed files. "
    f"Estimated chunks embedded: ~{totalEstimatedChunks} "
    f"(heuristic: ~4 chars/token, max_tokens_per_chunk={MAX_TOKENS_PER_CHUNK}, "
    f"max_overlap_tokens={MAX_OVERLAP_TOKENS}). "
    f"Store '{FILE_SEARCH_STORE_NAME}': "
    f"active_documents={store.active_documents_count}, "
    f"pending_documents={store.pending_documents_count}, "
    f"failed_documents={store.failed_documents_count}, "
    f"size_bytes={store.size_bytes}"
)
