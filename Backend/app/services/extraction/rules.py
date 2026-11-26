"""Deterministic, rule-based extraction from assessment report text.

How it works:

1. The page texts are split into lines, keeping each line's page and
   character offsets so every finding can point back to its source.
2. Headings split the text into sections. A heading is a numbered upper-case
   title ("III. BEHAVIOR AND SOCIAL SKILLS"), any upper-case line, a short
   known title ("Recommendations"), or an inline label ("Diagnosis: ...").
   Each heading is mapped to a section kind with ``SECTION_KEYWORDS``;
   unknown headings (school name, "REASON FOR REFERRAL", ...) are ignored.
3. Per section kind:
   * diagnosis / strengths / needs / recommendations: each list item, or
     each sentence if there is no list, becomes one finding of that category.
     A diagnosis is only ever taken from such an explicitly labelled section.
   * a domain section (Reading, Mathematics, ...): the whole section becomes
     a ``present_level`` finding, and each sentence is also checked against
     need/strength cue words.
   * observations: sentences are checked against the cue words only.

The rules are a heuristic. Every result is a draft that a person reviews.
"""

import re
from dataclasses import dataclass, field

from app.services.extraction.schema import (
    ExtractionResult,
    FindingCategory,
    FindingDomain,
    FindingDraft,
    PageText,
    SourceRef,
)

C = FindingCategory
D = FindingDomain

# Section kinds that are not a category or a domain.
OBSERVATION = "observation"
IGNORED = None

# Checked in order against the start of the upper-cased heading title.
SECTION_KEYWORDS: list[tuple[str, object]] = [
    (r"(DIAGNOS(IS|ES|TIC)|CLINICAL IMPRESSION|IMPRESSION|CLASSIFICATION|DIYAGNOSIS)\b", C.DIAGNOSIS),
    (r"(RECOMMENDATIONS?|REKOMENDASYON|SUGGESTIONS?|SUGGESTED INTERVENTIONS?|INTERVENTIONS?)\b", C.RECOMMENDATION),
    (r"PRESENT LEVELS?\b|PLAAFP\b|CURRENT LEVEL", C.PRESENT_LEVEL),
    (r"(STRENGTHS?|ASSETS|KALAKASAN)\b", C.STRENGTH),
    (r"(NEEDS|AREAS? OF (CONCERN|NEED|DIFFICULTY)|AREAS? FOR IMPROVEMENT|WEAKNESS(ES)?|PANGANGAILANGAN)\b", C.NEED),
    (r"(READING|LITERACY|PAGBASA)\b", D.READING),
    (r"(WRITING|PAGSULAT|HANDWRITING)\b", D.WRITING),
    (r"(MATH(EMATICS)?|NUMERACY|ARITHMETIC|MATEMATIKA)\b", D.MATHEMATICS),
    (r"(BEHAVIOU?R|SOCIAL|SOCIO-?EMOTIONAL|EMOTIONAL|ADAPTIVE BEHAVIOU?R)", D.BEHAVIOR_SOCIAL),
    (r"(COMMUNICATION|LANGUAGE|SPEECH)\b", D.COMMUNICATION),
    (r"((FINE |GROSS )?MOTOR|PSYCHOMOTOR)\b", D.MOTOR),
    (r"(SELF-?HELP|DAILY LIVING|SELF-?CARE)\b", D.SELF_HELP),
    (r"(COGNITIVE|INTELLECTUAL|COGNITION)\b", D.COGNITIVE),
    (r"(OBSERBASYON|OBSERVATIONS?|REMARKS|ANECDOTAL)\b", OBSERVATION),
]

# Lines that end the current section (signatures etc.).
STOP_LABEL = re.compile(
    r"^\s*(prepared|noted|checked|approved|reviewed|attested|evaluated) by\b|^\s*(signature|conforme)\b",
    re.IGNORECASE,
)

NEED_CUES = re.compile(
    r"\b(difficult(y|ies)?|hard time|limited|struggl\w*|unable|cannot|can't|not yet|"
    r"needs? (support|help|assistance|reminders?|prompt\w*|cues?)|restless|slowly|slow\b|poor|weak\w*|"
    r"delay(ed)?|below (grade|age|the expected)|inconsistent\w*|distract\w*|upset|tantrums?|"
    r"avoids?|refuses?|fist grip|with support|echoes|"
    r"nahihirapan|hindi pa|kailangan|mahina)\b",
    re.IGNORECASE,
)
STRENGTH_CUES = re.compile(
    r"\b(able to|can\b|recogni[sz]es|independently|works well|responds well|enjoys|follows|"
    r"participates|friendly|strong|good|excellent|within (the )?(expected|normal|average) range|"
    r"age-appropriate|masigla|palakaibigan|mahusay|mabuti|kaya)\b",
    re.IGNORECASE,
)

DOMAIN_GUESS: list[tuple[re.Pattern, FindingDomain]] = [
    (re.compile(r"\b(fine|gross) motor\b", re.I), D.MOTOR),
    (re.compile(r"\b(read\w*|phonics|decod\w*|comprehension|letters?|words?|pagbasa|salita)\b", re.I), D.READING),
    (re.compile(r"\b(writ\w*|spell\w*|pencil|copies|tracing)\b", re.I), D.WRITING),
    (re.compile(r"\b(math\w*|numbers?|count\w*|add\w*|subtract\w*|multipl\w*|arithmetic|manipulatives?)\b", re.I), D.MATHEMATICS),
    (re.compile(r"\b(speech|language|speaks?|conversation\w*|vocabulary|communicat\w*|phrases?)\b", re.I), D.COMMUNICATION),
    (re.compile(r"\b(behavio\w*|social|peers?|transitions?|routine|restless|tantrum\w*|schedule|praise|on task)\b", re.I), D.BEHAVIOR_SOCIAL),
    (re.compile(r"\b(motor|grip|button\w*|cutting|pegboards?)\b", re.I), D.MOTOR),
    (re.compile(r"\b(toilet\w*|dressing|feeding|self-help|hygiene)\b", re.I), D.SELF_HELP),
]

NUMBERING = re.compile(r"^\s*(?:[IVXLC|l1]{1,5}|\d{1,2}|[A-Ha-h])[.)]\s+")
LIST_MARKER = re.compile(r"^\s*(?:\d{1,2}[.)]|[a-hA-H][.)]|[-•*–·])\s+")
INLINE_LABEL = re.compile(r"^\s*([A-Za-z][A-Za-z /&()-]{1,48}?)\s*:\s*(\S.*)?$")
SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(\"'“])")


@dataclass
class Line:
    page: int
    start: int
    end: int
    text: str  # page_text[start:end]

    @property
    def blank(self) -> bool:
        return not self.text.strip()


@dataclass
class Section:
    kind: object  # FindingCategory | FindingDomain | OBSERVATION | None
    lines: list[Line] = field(default_factory=list)


@dataclass
class Span:
    page: int
    start: int
    end: int


# Words allowed after the keyword in an inline label ("Reading skills:", "Motor development:").
LABEL_SUFFIX = {"SKILL", "SKILLS", "DEVELOPMENT", "AREA", "AREAS", "DOMAIN", "LEVEL", "PERFORMANCE",
                "ABILITY", "ABILITIES", "IMPRESSION", "AND", "/"}


def _classify_title(title: str, *, whole_label: bool = False) -> object:
    """Map a heading title to a section kind.

    With ``whole_label`` (inline "Label: text"), the keyword must make up the
    whole label apart from LABEL_SUFFIX words, so "Fine motor activities: ..."
    inside a recommendation does not start a new section.
    """
    upper = title.upper().strip()
    for pattern, kind in SECTION_KEYWORDS:
        m = re.match(pattern, upper)
        if m:
            if whole_label and any(w not in LABEL_SUFFIX for w in upper[m.end():].split()):
                continue
            return kind
    return IGNORED


def _letters(text: str) -> str:
    return "".join(ch for ch in text if ch.isalpha())


def _heading(line: Line) -> tuple[bool, object, Line | None]:
    """Return (is_heading, kind, rest_of_line) for a line."""
    raw = line.text.strip()
    if not raw:
        return False, IGNORED, None

    # Inline label: "Diagnosis: Autism ..." / "Reading: decodes ...".
    m = INLINE_LABEL.match(line.text)
    if m:
        kind = _classify_title(NUMBERING.sub("", m.group(1)), whole_label=True)
        if kind is not IGNORED:
            rest = None
            if m.group(2):
                offset = line.start + m.start(2)
                rest = Line(line.page, offset, line.end, line.text[m.start(2):])
            return True, kind, rest

    title = NUMBERING.sub("", raw).rstrip(":").strip()
    letters = _letters(title)
    if len(letters) < 3 or len(title) > 70:
        return False, IGNORED, None
    numbered = NUMBERING.match(raw) is not None
    upper = letters.isupper()
    if upper and (numbered or not raw.endswith(".")):
        return True, _classify_title(title), None
    # Short mixed-case known title on its own line: "Recommendations".
    if not raw.endswith(".") and len(title.split()) <= 4:
        kind = _classify_title(title)
        if kind is not IGNORED:
            return True, kind, None
    return False, IGNORED, None


def _lines(pages: list[PageText]) -> list[Line]:
    out: list[Line] = []
    for page in pages:
        pos = 0
        for part in page.text.split("\n"):
            out.append(Line(page.page_number, pos, pos + len(part), part))
            pos += len(part) + 1
        out.append(Line(page.page_number, pos, pos, ""))  # page break acts as a blank line
    return out


def _sections(lines: list[Line]) -> list[Section]:
    sections: list[Section] = [Section(IGNORED)]
    for line in lines:
        if STOP_LABEL.match(line.text):
            sections.append(Section(IGNORED))
            continue
        is_heading, kind, rest = _heading(line)
        if is_heading:
            sections.append(Section(kind, [rest] if rest else []))
        else:
            sections[-1].lines.append(line)
    return [s for s in sections if s.kind is not IGNORED and any(not ln.blank for ln in s.lines)]


def _trim(page_text: str, span: Span) -> Span | None:
    start, end = span.start, span.end
    while start < end and page_text[start].isspace():
        start += 1
    while end > start and page_text[end - 1].isspace():
        end -= 1
    return Span(span.page, start, end) if end > start else None


def _paragraphs(section: Section) -> list[Span]:
    """Contiguous lines on the same page.

    OCR sometimes puts a blank line between the lines of one paragraph, so a
    blank line only ends the paragraph when the text before it ends a sentence
    or the next line starts with a capital letter.
    """
    spans: list[Span] = []
    current: Span | None = None
    last_text = ""
    after_blank = False
    for line in section.lines:
        if line.blank:
            after_blank = True
            continue
        stripped = line.text.strip()
        continues = (
            current is not None
            and current.page == line.page
            and (
                not after_blank
                or (not last_text.endswith((".", "!", "?", ":")) and stripped[:1].islower())
            )
        )
        if continues:
            current.end = line.end
        else:
            current = Span(line.page, line.start, line.end)
            spans.append(current)
        last_text = stripped
        after_blank = False
    return spans


def _items(section: Section) -> list[Span] | None:
    """List items (numbered / bulleted); None if the section has no list."""
    if not any(LIST_MARKER.match(ln.text) for ln in section.lines):
        return None
    items: list[Span] = []
    current: Span | None = None
    for line in section.lines:
        if line.blank:
            current = None
            continue
        marker = LIST_MARKER.match(line.text)
        if marker:
            current = Span(line.page, line.start + marker.end(), line.end)
            items.append(current)
        elif current is not None and current.page == line.page:
            current.end = line.end  # wrapped continuation of the item
        elif not line.text.rstrip().endswith(":"):  # skip intros like "We recommend:"
            current = Span(line.page, line.start, line.end)
            items.append(current)
    return items


def _sentences(span: Span, page_text: str) -> list[Span]:
    text = page_text[span.start:span.end]
    out: list[Span] = []
    pos = 0
    for m in SENTENCE_BOUNDARY.finditer(text):
        out.append(Span(span.page, span.start + pos, span.start + m.start()))
        pos = m.end()
    out.append(Span(span.page, span.start + pos, span.end))
    return out


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _guess_domain(text: str) -> FindingDomain | None:
    for pattern, domain in DOMAIN_GUESS:
        if pattern.search(text):
            return domain
    return None


def _cue_category(text: str) -> FindingCategory | None:
    if NEED_CUES.search(text):
        return C.NEED  # a sentence with both kinds of cue counts as a need
    if STRENGTH_CUES.search(text):
        return C.STRENGTH
    return None


class RuleBasedExtractor:
    method = "rule"
    version = "rules-1"

    def extract(self, pages: list[PageText]) -> ExtractionResult:
        texts = {p.page_number: p.text for p in pages}
        findings: list[FindingDraft] = []
        seen: set[tuple[str, str]] = set()

        def add(category: FindingCategory, span: Span | None, domain=None, text: str | None = None) -> None:
            if span is not None:
                span = _trim(texts[span.page], span)
                if span is None:
                    return
            body = text if text is not None else _normalize(texts[span.page][span.start:span.end])
            body = body.strip(" ;,")
            if len(_letters(body)) < 3:
                return
            key = (category.value, body.lower())
            if key in seen:
                return
            seen.add(key)
            source = None
            if span is not None:
                quote = _normalize(texts[span.page][span.start:span.end])
                source = SourceRef(page=span.page, start=span.start, end=span.end, quote=quote[:500])
            findings.append(
                FindingDraft(category=category, domain=domain, text=body[:2000], source=source)
            )

        for section in _sections(_lines(pages)):
            kind = section.kind
            if kind in (C.DIAGNOSIS, C.STRENGTH, C.NEED, C.RECOMMENDATION):
                units = _items(section)
                if units is None:
                    units = [s for p in _paragraphs(section) for s in _sentences(p, texts[p.page])]
                for unit in units:
                    trimmed = _trim(texts[unit.page], unit)
                    if trimmed is None:
                        continue
                    text = _normalize(texts[trimmed.page][trimmed.start:trimmed.end])
                    domain = None if kind == C.DIAGNOSIS else _guess_domain(text)
                    add(kind, trimmed, domain)
            elif kind == C.PRESENT_LEVEL:
                for para in _paragraphs(section):
                    text = _normalize(texts[para.page][para.start:para.end])
                    add(C.PRESENT_LEVEL, para, _guess_domain(text))
            elif isinstance(kind, FindingDomain):
                paragraphs = _paragraphs(section)
                if not paragraphs:
                    continue
                # Whole section = present level; the source points at its first page.
                first = paragraphs[0]
                same_page = [p for p in paragraphs if p.page == first.page]
                full_text = " ".join(_normalize(texts[p.page][p.start:p.end]) for p in paragraphs)
                add(C.PRESENT_LEVEL, Span(first.page, first.start, same_page[-1].end), kind, full_text)
                for para in paragraphs:
                    for sentence in _sentences(para, texts[para.page]):
                        text = _normalize(texts[sentence.page][sentence.start:sentence.end])
                        category = _cue_category(text)
                        if category is not None:
                            add(category, sentence, kind)
            elif kind == OBSERVATION:
                for para in _paragraphs(section):
                    for sentence in _sentences(para, texts[para.page]):
                        text = _normalize(texts[sentence.page][sentence.start:sentence.end])
                        category = _cue_category(text)
                        if category is not None:
                            add(category, sentence, _guess_domain(text))

        return ExtractionResult(extractor=self.version, findings=findings)
