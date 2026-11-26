from typing import Protocol

from app.services.extraction.schema import ExtractionResult, PageText


class Extractor(Protocol):
    method: str  # stored on the version: "rule", later "ai"
    version: str  # e.g. "rules-1"; bump when the logic changes

    def extract(self, pages: list[PageText]) -> ExtractionResult: ...
