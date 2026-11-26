"""Build the IEP Word document from the saved record (Stage 9).

The document is generated on demand and never edited by GABAY afterwards. A
finalized IEP is immutable, so its document is always reproducible.
"""

import io
from datetime import date

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from app.core.config import get_settings
from app.models.iep import Iep, IepStatus
from app.models.learner import Learner
from app.services.extraction.schema import FindingCategory

DOMAIN_NAMES = {
    "reading": "Reading", "writing": "Writing", "mathematics": "Mathematics",
    "behavior_social": "Behavior and social skills", "communication": "Communication",
    "motor": "Motor skills", "self_help": "Self-help and daily living", "cognitive": "Cognitive skills",
    "other": "Other",
}
METHOD_NAMES = {
    "percent_accuracy": "Percent accuracy", "trials": "Trials", "frequency": "Frequency count",
    "duration": "Duration", "rate": "Rate", "rubric": "Rubric level", "checklist": "Checklist",
}
UNIT_NAMES = {"percent": "%", "trials": "trials", "count": "times", "minutes": "minutes",
              "wpm": "words per minute", "level": "rubric level"}
GRADE_NAMES = {"K": "Kindergarten", "NG": "Non-graded"}


def _fmt_date(value) -> str:
    if not value:
        return "—"
    if isinstance(value, str):
        try:
            value = date.fromisoformat(value)
        except ValueError:
            return value
    return value.strftime("%d %B %Y").lstrip("0")


def _age(birth: date, on: date) -> str:
    years = on.year - birth.year - ((on.month, on.day) < (birth.month, birth.day))
    return f"{years} years"


def _number(value: float | None) -> str:
    if value is None:
        return "—"
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def _target(goal) -> str:
    if goal.target_value is None:
        return "—"
    unit = UNIT_NAMES.get(goal.target_unit or "", goal.target_unit or "")
    text = f"{_number(goal.target_value)}%" if goal.target_unit == "percent" else f"{_number(goal.target_value)} {unit}"
    return f"{text} {goal.criterion}" if goal.criterion else text


def _shade(cell, hex_fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_fill)
    tc_pr.append(shd)


def _field(paragraph, instruction: str) -> None:
    """Insert a Word field such as PAGE or NUMPAGES."""
    run = paragraph.add_run()
    for tag, text in (("begin", None), (None, instruction), ("separate", None), (None, "1"), ("end", None)):
        if tag:
            el = OxmlElement("w:fldChar")
            el.set(qn("w:fldCharType"), tag)
        elif text == instruction:
            el = OxmlElement("w:instrText")
            el.set(qn("xml:space"), "preserve")
            el.text = instruction
        else:
            el = OxmlElement("w:t")
            el.text = text
        run._r.append(el)


def _heading(doc, text: str, size: int = 12) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(4)
    run = p.add_run(text.upper())
    run.bold = True
    run.font.size = Pt(size)
    run.font.color.rgb = RGBColor(0x1F, 0x2A, 0x5A)


def _kv_table(doc, rows: list[tuple[str, str]], label_width: float = 4.5):
    table = doc.add_table(rows=0, cols=2)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for label, value in rows:
        cells = table.add_row().cells
        cells[0].width = Cm(label_width)
        cells[1].width = Cm(18 - label_width)
        cells[0].text = ""
        run = cells[0].paragraphs[0].add_run(label)
        run.bold = True
        run.font.size = Pt(9.5)
        _shade(cells[0], "EEF1F8")
        cells[1].text = ""
        cells[1].paragraphs[0].add_run(value or "—").font.size = Pt(9.5)
    return table


def _bullets(doc, items: list[str]) -> None:
    if not items:
        doc.add_paragraph("None recorded.").runs[0].italic = True
        return
    for item in items:
        p = doc.add_paragraph(item, style="List Bullet")
        p.paragraph_format.space_after = Pt(1)


def build_iep_docx(iep: Iep, learner: Learner) -> bytes:
    settings = get_settings()
    doc = Document()
    section = doc.sections[0]
    section.orientation = WD_ORIENT.PORTRAIT
    section.page_width, section.page_height = Cm(21.0), Cm(29.7)
    for side in ("left_margin", "right_margin"):
        setattr(section, side, Cm(1.5))
    section.top_margin = Cm(1.5)
    section.bottom_margin = Cm(1.5)

    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(10)

    is_draft = iep.status == IepStatus.DRAFT.value

    # Header (draft banner) and footer (record reference + page numbers).
    header = section.header.paragraphs[0]
    header.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if is_draft:
        run = header.add_run("DRAFT – NOT FINAL")
        run.bold = True
        run.font.size = Pt(14)
        run.font.color.rgb = RGBColor(0xC0, 0x1C, 0x1C)
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = footer.add_run(
        f"Generated by GABAY from IEP record #{iep.id} v{iep.version_number} on {_fmt_date(date.today())} · Page "
    )
    run.font.size = Pt(8)
    _field(footer, "PAGE")
    footer.add_run(" of ").font.size = Pt(8)
    _field(footer, "NUMPAGES")

    # Title block.
    for text, size, bold in (
        ("Republic of the Philippines · Department of Education", 9, False),
        (settings.school_name, 12, True),
        ("Special Needs Education (SNEd) Program", 10, False),
        ("INDIVIDUALIZED EDUCATION PROGRAM (IEP)", 16, True),
    ):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(2)
        r = p.add_run(text)
        r.bold = bold
        r.font.size = Pt(size)

    # Learner information.
    _heading(doc, "I. Learner information")
    status = {"draft": "Draft", "finalized": "Finalized", "superseded": "Superseded"}[iep.status]
    _kv_table(doc, [
        ("Name of learner", learner.full_name),
        ("Learner code", learner.learner_code),
        ("Date of birth / age", f"{_fmt_date(learner.birth_date)} ({_age(learner.birth_date, iep.start_date or date.today())})"),
        ("Sex", learner.sex.capitalize()),
        ("Grade and section", f"{GRADE_NAMES.get(learner.grade_level, 'Grade ' + learner.grade_level)} – {learner.section}"),
        ("School year", iep.school_year),
        ("IEP period", f"{_fmt_date(iep.start_date)} to {_fmt_date(iep.end_date)}"),
        ("Annual review date", _fmt_date(iep.annual_review_date)),
        ("IEP version / status", f"Version {iep.version_number} – {status}"
         + (f" (finalized {_fmt_date(iep.finalized_at.date())})" if iep.finalized_at else "")),
    ])
    if iep.version_number > 1:
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(6)
        p.add_run(f"Amendment of IEP version {iep.version_number - 1}. Reason: ").bold = True
        p.add_run(iep.amendment_reason or "—")

    # Present levels, diagnosis, strengths, needs.
    by_cat: dict[str, list] = {}
    for f in iep.findings:
        by_cat.setdefault(f.category, []).append(f)
    _heading(doc, "II. Present levels of performance")
    levels = by_cat.get(FindingCategory.PRESENT_LEVEL.value, [])
    if levels:
        _kv_table(doc, [(DOMAIN_NAMES.get(f.domain or "", "General"), f.text) for f in levels])
    else:
        doc.add_paragraph("None recorded.").runs[0].italic = True
    if by_cat.get(FindingCategory.DIAGNOSIS.value):
        _heading(doc, "Diagnosis / clinical impression", 10)
        _bullets(doc, [f.text for f in by_cat[FindingCategory.DIAGNOSIS.value]])
    _heading(doc, "Strengths", 10)
    _bullets(doc, [f.text for f in by_cat.get(FindingCategory.STRENGTH.value, [])])
    _heading(doc, "Needs", 10)
    _bullets(doc, [f.text for f in by_cat.get(FindingCategory.NEED.value, [])])
    if by_cat.get(FindingCategory.RECOMMENDATION.value):
        _heading(doc, "Assessment recommendations", 10)
        _bullets(doc, [f.text for f in by_cat[FindingCategory.RECOMMENDATION.value]])

    # Goals.
    _heading(doc, "III. Annual goals")
    findings_by_id = {f.id: f for f in iep.findings}
    if not iep.goals:
        doc.add_paragraph("No goals recorded.").runs[0].italic = True
    for n, goal in enumerate(iep.goals, 1):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(8)
        p.paragraph_format.keep_with_next = True
        title = f"Goal {n}"
        if goal.goal_code:
            title += f" ({goal.goal_code})"
        p.add_run(title).bold = True
        need = findings_by_id.get(goal.addresses_finding_id) if goal.addresses_finding_id else None
        rows = [
            ("Domain / skill", " – ".join(x for x in (DOMAIN_NAMES.get(goal.domain or "", goal.domain or ""), goal.skill_name) if x) or "—"),
            ("Need addressed", need.text if need else "—"),
            ("Annual goal", goal.statement),
            ("Baseline", goal.baseline or "—"),
            ("Target", _target(goal)),
            ("Measurement", METHOD_NAMES.get(goal.measurement_method or "", goal.measurement_method or "—")),
            ("Responsible staff", goal.responsible_staff or "—"),
            ("Start / target date", f"{_fmt_date(goal.start_date)} to {_fmt_date(goal.target_date)}"),
            ("Progress review dates", ", ".join(_fmt_date(d) for d in (goal.review_dates or [])) or "—"),
        ]
        _kv_table(doc, rows)

    # Accommodations, services, notes.
    _heading(doc, "IV. Accommodations and modifications")
    doc.add_paragraph(iep.accommodations or "None recorded.")
    _heading(doc, "V. Services and related services")
    doc.add_paragraph(iep.services or "None recorded.")
    if iep.notes:
        _heading(doc, "Notes")
        doc.add_paragraph(iep.notes)

    # Team and signatures.
    _heading(doc, "VI. IEP team")
    members = list(iep.team_members or []) + [{"name": "", "role": "Parent / guardian"}]
    table = doc.add_table(rows=1, cols=4)
    table.style = "Table Grid"
    for cell, text in zip(table.rows[0].cells, ("Name", "Role", "Signature", "Date"), strict=True):
        cell.text = ""
        r = cell.paragraphs[0].add_run(text)
        r.bold = True
        _shade(cell, "EEF1F8")
    for m in members:
        cells = table.add_row().cells
        cells[0].text = m.get("name") or ""
        cells[1].text = m.get("role") or ""
        cells[2].text = ""
        cells[3].text = ""
        cells[2].paragraphs[0].paragraph_format.space_after = Pt(14)

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def filename(iep: Iep, learner: Learner) -> str:
    return f"IEP_{learner.learner_code}_{iep.school_year}_v{iep.version_number}{'_DRAFT' if iep.status == 'draft' else ''}.docx"
