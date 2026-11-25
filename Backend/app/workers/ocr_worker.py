"""OCR worker: claims queued OCR jobs from the database and processes them.

Run from Backend/ in its own terminal (or container):

    python -m app.workers.ocr_worker          # run until Ctrl+C
    python -m app.workers.ocr_worker --once   # process at most one job, then exit

Several workers may run at once; ``claim_next`` uses SKIP LOCKED.
"""

import argparse
import logging
import signal
import time
from collections.abc import Callable

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.assessment import Document
from app.services import ocr_job_service
from app.services.ocr_service import OcrEngine, OcrError, TesseractEngine, extract_pages
from app.services.storage_service import StorageBackend, StorageError, get_storage

logger = logging.getLogger("gabay.ocr_worker")

RECOVER_EVERY_SECONDS = 60


def process_one(
    session_factory: Callable[[], Session],
    storage: StorageBackend,
    engine: OcrEngine,
    settings: Settings | None = None,
) -> bool:
    """Claim and process one job. Returns False when the queue is empty."""
    settings = settings or get_settings()
    db = session_factory()
    try:
        job = ocr_job_service.claim_next(db)
        if job is None:
            return False
        logger.info("Processing OCR job %s (attempt %s)", job.id, job.attempts)
        try:
            document = db.get(Document, job.document_id)
            if document is None:
                raise OcrError("document_missing", "The document no longer exists.")
            check = getattr(engine, "check", None)
            if check is not None:
                check()
            try:
                data = storage.get(document.storage_key)
            except StorageError as exc:
                raise OcrError(
                    "storage_unavailable", "The document could not be read from storage."
                ) from exc
            pages = extract_pages(data, document.mime_type, engine=engine, settings=settings)
            ocr_job_service.complete(db, job, pages, settings)
            failed = sum(1 for p in pages if p.status != "ok")
            logger.info("OCR job %s done: %s pages, %s failed", job.id, len(pages), failed)
        except OcrError as exc:
            logger.warning("OCR job %s failed: %s", job.id, exc.code)
            ocr_job_service.fail(db, job, exc.code, exc.message)
        except Exception:
            logger.exception("OCR job %s crashed", job.id)
            ocr_job_service.fail(
                db, job, "internal_error", "Processing failed unexpectedly. Try again later."
            )
        return True
    finally:
        db.close()


def recover(session_factory: Callable[[], Session], settings: Settings) -> None:
    db = session_factory()
    try:
        ocr_job_service.recover_stale(db, settings)
    finally:
        db.close()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="GABAY OCR worker")
    parser.add_argument("--once", action="store_true", help="process at most one job and exit")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    from app.db.session import SessionLocal  # imported late so tests never touch the real DB

    settings = get_settings()
    storage = get_storage()
    engine = TesseractEngine(settings)
    try:
        engine.check()
        logger.info("Tesseract ready (languages: %s)", settings.ocr_languages)
    except OcrError as exc:
        # Keep running: jobs will fail with a clear message until it is installed.
        logger.error("%s", exc.message)

    recover(SessionLocal, settings)
    if args.once:
        process_one(SessionLocal, storage, engine, settings)
        return

    stopping = False

    def stop(signum, _frame) -> None:
        nonlocal stopping
        logger.info("Signal %s received; finishing the current job and stopping.", signum)
        stopping = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    last_recover = time.monotonic()
    logger.info("OCR worker started; polling every %ss", settings.ocr_worker_poll_seconds)
    while not stopping:
        if time.monotonic() - last_recover >= RECOVER_EVERY_SECONDS:
            recover(SessionLocal, settings)
            last_recover = time.monotonic()
        try:
            worked = process_one(SessionLocal, storage, engine, settings)
        except Exception:  # database down etc.; keep the worker alive
            logger.exception("Worker loop error")
            worked = False
        if not worked:
            # Sleep in small steps so Ctrl+C is responsive.
            deadline = time.monotonic() + settings.ocr_worker_poll_seconds
            while not stopping and time.monotonic() < deadline:
                time.sleep(0.2)
    logger.info("OCR worker stopped.")


if __name__ == "__main__":
    main()
