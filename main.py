import logging
import os
import subprocess
import sys

from dotenv import load_dotenv

from google import genai
from google.genai import types

import job

os.environ.setdefault("GEMINI_API_KEY", os.getenv("API_KEY", ""))

SYSTEM_PROMPT = """You are OptiBot, the customer-support bot for OptiSigns.com.
• Tone: helpful, factual, concise.
• Only answer using the uploaded docs.
• Max 5 bullet points; else link to the doc.
• Cite up to 3 "Article URL:" lines per reply."""

LOG_FILE = "job.log"

logger = logging.getLogger("main")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _fileHandler = logging.FileHandler(LOG_FILE)
    _fileHandler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(_fileHandler)
    _streamHandler = logging.StreamHandler()
    _streamHandler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(_streamHandler)


def runStep(script: str) -> None:
    subprocess.run([sys.executable, script], check=True)


runStep("scraper.py")
runStep("uploader.py")

load_dotenv(override=True)

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)

fileSearchStoreName = os.getenv("FILE_SEARCH_STORE_NAME")
assert fileSearchStoreName is not None
if not fileSearchStoreName.startswith("fileSearchStores/"):
    fileSearchStoreName = f"fileSearchStores/{fileSearchStoreName}"

response = client.models.generate_content(
    model="gemini-3.1-flash-lite",
    contents="How do I add a YouTube video?",
    config=types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=[
            types.Tool(
                file_search=types.FileSearch(
                    file_search_store_names=[fileSearchStoreName]
                )
            )
        ],
    ),
)

logger.info(f"Sanity-check Q: How do I add a YouTube video?\n{response.text}")

if __name__ == "__main__":
    if os.getenv("RUN_ONCE", "false").lower() not in ("1", "true", "yes"):
        job.startScheduler()
