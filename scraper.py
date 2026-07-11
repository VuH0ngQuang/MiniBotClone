import hashlib
import json
import logging
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as html_to_markdown
from slugify import slugify

# data["articles"] is list
# data["articles"][0] is dict

BASE_URL = "https://support.optisigns.com/api/v2/help_center/en-us/articles.json"
REQUEST_TIMEOUT = 20

MANIFEST_FILE = "manifest.json"
CHANGED_IDS_FILE = "changed_ids.txt"
LOG_FILE = "job.log"

logger = logging.getLogger("scraper")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _fileHandler = logging.FileHandler(LOG_FILE)
    _fileHandler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(_fileHandler)
    _streamHandler = logging.StreamHandler()
    _streamHandler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(_streamHandler)


def scrap() -> dict[int, dict[str, str]]:
    pageNum: int = 1
    result: dict[int, dict[str, str]] = {}
    response = requests.get(BASE_URL + "?page=" + str(pageNum), timeout=REQUEST_TIMEOUT)
    data = response.json()
    pageTotal = data["page_count"]

    while pageNum <= pageTotal:
        articles = data["articles"]
        for article in articles:
            tmp = {}
            tmp["url"] = article["html_url"]
            tmp["created_at"] = article["created_at"]
            tmp["updated_at"] = article["updated_at"]
            tmp["title"] = article["title"]
            tmp["body"] = article["body"]
            result[article["id"]] = tmp

        pageNum += 1
        if pageNum > pageTotal:
            break
        if data["next_page"] is None:
            break
        response = requests.get(data["next_page"], timeout=REQUEST_TIMEOUT)
        data = response.json()

    return result


def htmlBodyToMarkdown(htmlBody: str) -> str:
    data = BeautifulSoup(htmlBody, "lxml")
    for tag in data.find_all(["style", "script", "nav", "footer", "iframe","img"]):
        tag.decompose()

    md = html_to_markdown(str(data), heading_style="ATX", bullets="-")
    md = re.sub(r"\n{3,}", "\n\n", md).strip()
    return md


def articleToMarkdown(articleId: int, article: dict[str, str]) -> str:
    bodyMd = htmlBodyToMarkdown(article["body"])
    return (
        f"# {article['title']}\n\n"
        f"- ID: {articleId}\n"
        f"- URL: {article['url']}\n"
        f"- Created: {article['created_at']}\n"
        f"- Updated: {article['updated_at']}\n\n"
        f"{bodyMd}\n"
    )


def contentHash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def loadManifest(outPath: Path) -> dict[str, str]:
    manifestPath = outPath / MANIFEST_FILE
    if not manifestPath.exists():
        return {}
    return json.loads(manifestPath.read_text(encoding="utf-8"))


def exportMarkdown(articles: dict[int, dict[str, str]], outDir: str = "articles_md") -> None:
    outPath = Path(outDir)
    outPath.mkdir(parents=True, exist_ok=True)

    oldManifest = loadManifest(outPath)

    newManifest: dict[str, str] = {}
    changedIds: list[str] = []
    addedCount = 0
    updatedCount = 0
    skippedCount = 0

    for articleId, article in articles.items():
        content = articleToMarkdown(articleId, article)
        h = contentHash(content)
        idStr = str(articleId)

        newManifest[idStr] = h

        if idStr not in oldManifest:
            addedCount += 1
            changedIds.append(idStr)
        elif oldManifest[idStr] != h:
            updatedCount += 1
            changedIds.append(idStr)
        else:
            skippedCount += 1
            continue

        filePath = outPath / f"{articleId}.md"
        filePath.write_text(content, encoding="utf-8")
        logger.info(f"saved: {filePath}")

    (outPath / MANIFEST_FILE).write_text(json.dumps(newManifest, indent=2), encoding="utf-8")

    (outPath / CHANGED_IDS_FILE).write_text("\n".join(changedIds), encoding="utf-8")

    logger.info(
        f"Scrape summary: added={addedCount}, updated={updatedCount}, "
        f"skipped={skippedCount}, total={len(articles)}"
    )
    logger.info(f"Changed IDs written to {outPath / CHANGED_IDS_FILE} ({len(changedIds)} ids)")


if __name__ == '__main__':
    data = scrap()
    exportMarkdown(data)