"""Turn a stored document into ordered page texts. Pure functions, no database.

* PDF: use the page's text layer when it has enough text; otherwise render the
  page to an image and OCR it.
* JPG/PNG: one page, OCR'd.

Every page is processed in isolation: one bad page is recorded as failed and
the rest still run. Only problems that affect the whole document (unreadable
PDF, Tesseract missing) raise ``OcrError``.

Never log page text: it contains learner data.
"""

import io
import logging
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol

import pypdfium2 as pdfium
from PIL import Image, ImageFilter, ImageOps, UnidentifiedImageError

from app.core.config import Settings, get_settings
from app.models.ocr import OcrPageSource, OcrPageStatus

logger = logging.getLogger(__name__)

# Guard against decompression bombs (a 600-DPI A3 page is ~70 MP).
Image.MAX_IMAGE_PIXELS = 120_000_000

# Preprocessing targets for the longest image side, in pixels.
MIN_LONG_SIDE = 2500
MAX_LONG_SIDE = 3500

PAGE_LIMIT_MESSAGE = "Page limit reached; this page was not processed."


class OcrError(Exception):
    """The whole document could not be processed."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class PageResult:
    page_number: int  # 1-based
    source: OcrPageSource
    status: OcrPageStatus
    text: str = ""
    confidence: float | None = None
    error: str | None = None


class OcrEngine(Protocol):
    def recognize(self, image: Image.Image) -> tuple[str, float | None]:
        """Return (text, mean confidence 0-100 or None if no words)."""


# --- Preprocessing -----------------------------------------------------------


def preprocess(image: Image.Image) -> Image.Image:
    """Grayscale, normalise size, stretch contrast, remove speckle noise."""
    img = ImageOps.grayscale(image)
    long_side = max(img.size)
    if long_side < MIN_LONG_SIDE or long_side > MAX_LONG_SIDE:
        target = MIN_LONG_SIDE if long_side < MIN_LONG_SIDE else MAX_LONG_SIDE
        scale = target / long_side
        size = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
        img = img.resize(size, Image.Resampling.LANCZOS)
    img = ImageOps.autocontrast(img, cutoff=1)
    return img.filter(ImageFilter.MedianFilter(3))


# --- Tesseract ---------------------------------------------------------------


def build_text_and_confidence(data: dict) -> tuple[str, float | None]:
    """Rebuild text from pytesseract ``image_to_data`` output, keeping line breaks.

    Confidence is the mean word confidence weighted by word length.
    """
    lines: list[str] = []
    paragraphs: list[str] = []
    current_key = None
    current_par = None
    words: list[str] = []
    weighted = 0.0
    weight = 0

    def flush_line() -> None:
        if words:
            lines.append(" ".join(words))
            words.clear()

    for i, word in enumerate(data.get("text", [])):
        word = (word or "").strip()
        if not word:
            continue
        par_key = (data["block_num"][i], data["par_num"][i])
        line_key = (*par_key, data["line_num"][i])
        if line_key != current_key:
            flush_line()
            if par_key != current_par and lines:
                paragraphs.append("\n".join(lines))
                lines.clear()
            current_key, current_par = line_key, par_key
        words.append(word)
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            conf = -1
        if conf >= 0:
            weighted += conf * len(word)
            weight += len(word)
    flush_line()
    if lines:
        paragraphs.append("\n".join(lines))

    text = "\n\n".join(paragraphs)
    return text, (round(weighted / weight, 1) if weight else None)


class TesseractEngine:
    def __init__(self, settings: Settings | None = None) -> None:
        import pytesseract

        self.settings = settings or get_settings()
        self.pytesseract = pytesseract
        if self.settings.tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = self.settings.tesseract_cmd

    def check(self) -> None:
        """Raise OcrError if Tesseract or a configured language is missing."""
        try:
            self.pytesseract.get_tesseract_version()
            installed = set(self.pytesseract.get_languages(config=""))
        except (self.pytesseract.TesseractNotFoundError, OSError) as exc:
            raise OcrError(
                "ocr_unavailable", "Tesseract OCR is not installed on the processing server."
            ) from exc
        missing = [lang for lang in self.settings.ocr_languages.split("+") if lang not in installed]
        if missing:
            raise OcrError(
                "ocr_language_missing",
                f"Tesseract is missing the language data for: {', '.join(missing)}.",
            )

    def recognize(self, image: Image.Image) -> tuple[str, float | None]:
        data = self.pytesseract.image_to_data(
            image,
            lang=self.settings.ocr_languages,
            config="--oem 1 --psm 3",
            timeout=self.settings.ocr_page_timeout_seconds,
            output_type=self.pytesseract.Output.DICT,
        )
        return build_text_and_confidence(data)


def tesseract_status(settings: Settings | None = None) -> dict:
    """Non-secret availability info for /api/config/status."""
    settings = settings or get_settings()
    try:
        engine = TesseractEngine(settings)
        engine.pytesseract.get_tesseract_version()
        installed = sorted(engine.pytesseract.get_languages(config=""))
    except Exception:  # noqa: BLE001 - any failure means "not available"
        return {"ocr_available": False, "ocr_languages_installed": []}
    wanted = settings.ocr_languages.split("+")
    return {
        "ocr_available": all(lang in installed for lang in wanted),
        "ocr_languages_installed": [lang for lang in wanted if lang in installed],
    }


# --- Page extraction ---------------------------------------------------------


def _short_error(exc: BaseException) -> str:
    name = exc.__class__.__name__
    if "Timeout" in name or isinstance(exc, RuntimeError) and "timeout" in str(exc).lower():
        return "OCR timed out on this page."
    return f"This page could not be processed ({name})."


def _ocr_page(number: int, image: Image.Image, engine: OcrEngine) -> PageResult:
    text, confidence = engine.recognize(preprocess(image))
    return PageResult(number, OcrPageSource.OCR, OcrPageStatus.OK, text.strip(), confidence)


def _pdf_pages(data: bytes, engine: OcrEngine, settings: Settings) -> Iterator[PageResult]:
    try:
        pdf = pdfium.PdfDocument(data)
    except pdfium.PdfiumError as exc:
        raise OcrError("pdf_unreadable", "The PDF could not be opened. It may be damaged or encrypted.") from exc
    try:
        total = len(pdf)
        if total == 0:
            raise OcrError("pdf_empty", "The PDF has no pages.")
        for index in range(total):
            number = index + 1
            if number > settings.ocr_max_pages:
                yield PageResult(
                    number, OcrPageSource.OCR, OcrPageStatus.FAILED, error=PAGE_LIMIT_MESSAGE
                )
                continue
            page = None
            try:
                page = pdf[index]
                textpage = page.get_textpage()
                try:
                    layer = textpage.get_text_range().replace("\r\n", "\n").strip()
                finally:
                    textpage.close()
                if len(layer) >= settings.ocr_min_text_layer_chars:
                    yield PageResult(number, OcrPageSource.TEXT_LAYER, OcrPageStatus.OK, layer)
                    continue
                bitmap = page.render(scale=settings.ocr_dpi / 72)
                try:
                    image = bitmap.to_pil()
                    yield _ocr_page(number, image, engine)
                finally:
                    bitmap.close()
            except OcrError:
                raise
            except Exception as exc:  # noqa: BLE001 - isolate page failures
                logger.warning("OCR failed on page %s: %s", number, exc.__class__.__name__)
                yield PageResult(
                    number, OcrPageSource.OCR, OcrPageStatus.FAILED, error=_short_error(exc)
                )
            finally:
                if page is not None:
                    page.close()
    finally:
        pdf.close()


def _image_pages(data: bytes, engine: OcrEngine) -> Iterator[PageResult]:
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
        image = ImageOps.exif_transpose(image)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise OcrError("image_unreadable", "The image could not be opened.") from exc
    try:
        yield _ocr_page(1, image, engine)
    except OcrError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("OCR failed on image: %s", exc.__class__.__name__)
        yield PageResult(1, OcrPageSource.OCR, OcrPageStatus.FAILED, error=_short_error(exc))


def extract_pages(
    data: bytes, mime_type: str, *, engine: OcrEngine, settings: Settings | None = None
) -> list[PageResult]:
    """Return one result per page, in page order."""
    settings = settings or get_settings()
    if mime_type == "application/pdf":
        pages = list(_pdf_pages(data, engine, settings))
    elif mime_type in {"image/png", "image/jpeg"}:
        pages = list(_image_pages(data, engine))
    else:
        raise OcrError("unsupported_file_type", "This file type cannot be processed.")
    return pages
