# GABAY backend image. The same image runs the API (default) or the OCR worker:
#   docker build -t gabay-backend .
#   docker run --env-file .env -p 8000:8000 gabay-backend
#   docker run --env-file .env gabay-backend python -m app.workers.ocr_worker
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Tesseract OCR with English and Filipino language data (OCR_LANGUAGES=eng+fil).
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng tesseract-ocr-fil \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY alembic.ini .
COPY app ./app

RUN useradd --create-home --uid 10001 gabay && mkdir -p /app/storage /app/.models && chown gabay /app/storage /app/.models
USER gabay

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
