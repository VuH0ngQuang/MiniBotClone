import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta

RUN_HOUR = int(os.getenv("RUN_HOUR", "17"))  # 5 PM
RUN_MINUTE = int(os.getenv("RUN_MINUTE", "40"))
LOG_FILE = "job.log"

logger = logging.getLogger("job")
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


def secondsUntilNextRun() -> float:
    now = datetime.now()
    target = now.replace(hour=RUN_HOUR, minute=RUN_MINUTE, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def runScrapeAndUploadJob() -> None:
    logger.info("Starting scheduled job: scraper.py + uploader.py")
    try:
        runStep("scraper.py")
        runStep("uploader.py")
        logger.info("Scheduled job finished successfully")
    except subprocess.CalledProcessError as e:
        logger.error(f"Scheduled job failed: {e}")


def startScheduler() -> None:
    logger.info(f"Job scheduler started; will run daily at {RUN_HOUR:02d}:{RUN_MINUTE:02d}")
    while True:
        waitSeconds = secondsUntilNextRun()
        logger.info(f"Sleeping {waitSeconds / 3600:.2f}h until next run")
        time.sleep(waitSeconds)
        runScrapeAndUploadJob()


if __name__ == "__main__":
    startScheduler()
