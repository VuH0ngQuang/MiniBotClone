FROM python:3.12-slim

ENV TZ=Asia/Ho_Chi_Minh
RUN apt-get update && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py job.py scraper.py uploader.py ./

ENV RUN_ONCE=true

CMD ["python3", "main.py"]
