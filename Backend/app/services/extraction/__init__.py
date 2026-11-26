"""Information extraction from reviewed OCR text (Stage 6).

* ``schema``   - the extraction schema (categories, domains, finding shape)
* ``base``     - the ``Extractor`` interface every extractor implements
* ``rules``    - deterministic rule-based extractor (the only one enabled)
* ``registry`` - picks an extractor by method name
"""
