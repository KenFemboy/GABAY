from app.core.config import get_settings
from app.core.errors import APIError
from app.services.extraction.base import Extractor
from app.services.extraction.rules import RuleBasedExtractor


def get_extractor(method: str = "rule") -> Extractor:
    if method == "rule":
        return RuleBasedExtractor()
    if method == "ai":
        # Placeholder for a later stage: AI extraction on de-identified text.
        if not get_settings().extraction_ai_enabled:
            raise APIError(409, "ai_extraction_disabled", "AI extraction is not enabled.")
        raise APIError(501, "ai_extraction_unavailable", "AI extraction is not implemented yet.")
    raise APIError(422, "unknown_extraction_method", f"Unknown extraction method: {method}.")
