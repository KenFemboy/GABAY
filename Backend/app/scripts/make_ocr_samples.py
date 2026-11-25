"""Generate SYNTHETIC sample documents for trying out OCR (Stage 5).

All names and details are made up. Never use real learner documents in development.

    python -m app.scripts.make_ocr_samples            # writes to Backend/samples/
    python -m app.scripts.make_ocr_samples --out DIR

Expected result after uploading and clicking "Process document"
(with the default OCR_REVIEW_CONFIDENCE=70):

    01_text_layer_report.pdf     Processed      text taken from the PDF, no OCR
    02_scanned_report_3p.pdf     Processed      3 clean scanned pages, OCR'd in order
    03_phone_photo.jpg           Processed or   tilted, uneven light; usually good enough
                                 Needs Review
    04_faded_copy.pdf            Needs Review   page 2 is faded; OCR text has errors to fix
    05_filipino_notes.png        Processed      mixed English/Filipino text (eng+fil)
    06_broken.pdf                Uploaded +     passes the upload check but cannot be opened;
                                 error shown    processing fails with a clear message
"""

import argparse
import random
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

# --- Synthetic content -------------------------------------------------------

HEADER = [
    "DEPARTMENT OF EDUCATION - SAMPLE SCHOOL (SYNTHETIC)",
    "Special Needs Education Program",
    "",
]

REPORT_PAGES = [
    [
        "INFORMAL ASSESSMENT REPORT",
        "",
        "Learner: Sample Learner A          Grade: 3          Section: Rosal",
        "School Year: 2025-2026             Date of Assessment: August 1, 2025",
        "Assessed by: Section Adviser (sample)",
        "",
        "I. READING",
        "The learner recognizes all letters of the alphabet and most letter sounds.",
        "Reads simple CVC words with support. Oral reading fluency is about 25 words",
        "per minute on a Grade 1 passage. Comprehension is limited to recalling the",
        "main character of the story.",
        "",
        "II. MATHEMATICS",
        "Counts objects up to 50 and writes numbers up to 20. Adds single-digit",
        "numbers using counters. Has difficulty with subtraction and word problems.",
    ],
    [
        "III. BEHAVIOR AND SOCIAL SKILLS",
        "The learner follows simple two-step instructions. Works well in pairs but",
        "becomes restless during long seatwork. Responds well to praise and a",
        "visual schedule.",
        "",
        "IV. COMMUNICATION",
        "Speaks in short sentences. Understands questions asked in Filipino and",
        "English but usually answers in Filipino.",
        "",
        "V. MOTOR SKILLS",
        "Holds a pencil with a fist grip. Copies shapes and letters slowly.",
        "Can button and unbutton large buttons independently.",
    ],
    [
        "VI. RECOMMENDATIONS",
        "1. Daily phonics practice using decodable texts (15 minutes).",
        "2. Use of manipulatives for addition and subtraction.",
        "3. Visual schedule and short work periods with breaks.",
        "4. Fine motor activities: tracing, cutting, and pegboards.",
        "5. Refer to the SNED Coordinator for a formal assessment.",
        "",
        "Prepared by: Section Adviser (sample)",
        "Noted by: SNED Coordinator (sample)",
    ],
]

FILIPINO_NOTES = [
    "OBSERBASYON NG GURO",
    "",
    "Ang mag-aaral ay masigla at palakaibigan sa kanyang mga kaklase.",
    "Nakakabasa siya ng mga simpleng salita ngunit nahihirapan sa mahahabang",
    "pangungusap. Mas mabuti ang kanyang pag-unawa kapag may larawan.",
    "",
    "The learner participates actively in group activities and enjoys",
    "singing and drawing. Needs reminders to stay on task.",
    "",
    "Rekomendasyon: Dagdag na pagsasanay sa pagbasa araw-araw.",
]

# --- Helpers -----------------------------------------------------------------

PAGE_PX = (1700, 2200)  # US Letter at 200 DPI


def load_font(size: int) -> ImageFont.ImageFont:
    for name in ("arial.ttf", "Arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def render_page(lines: list[str], *, page_label: str | None = None) -> Image.Image:
    img = Image.new("RGB", PAGE_PX, "white")
    draw = ImageDraw.Draw(img)
    body = load_font(34)
    bold = load_font(40)
    y = 150
    for i, line in enumerate(HEADER + lines):
        font = bold if i < 2 or (line.isupper() and line) else body
        draw.text((150, y), line, fill="black", font=font)
        y += 58
    if page_label:
        draw.text((PAGE_PX[0] // 2 - 60, PAGE_PX[1] - 120), page_label, fill="black", font=body)
    return img


def add_scan_noise(img: Image.Image, rng: random.Random, amount: int = 1500) -> Image.Image:
    img = img.copy()
    draw = ImageDraw.Draw(img)
    for _ in range(amount):
        x, y = rng.randrange(img.width), rng.randrange(img.height)
        shade = rng.randint(120, 200)
        draw.point((x, y), fill=(shade, shade, shade))
    return img


def save_pdf(images: list[Image.Image], path: Path) -> None:
    images[0].save(path, format="PDF", save_all=True, append_images=images[1:], resolution=200)


def _pdf_escape(text: str) -> bytes:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)").encode("latin-1")


def text_layer_pdf(pages: list[list[str]]) -> bytes:
    """A real 'digital' PDF (like one exported from Word): selectable text, no images."""
    body = [b"<< /Type /Catalog /Pages 2 0 R >>"]
    kids = b" ".join(b"%d 0 R" % (4 + 2 * i) for i in range(len(pages)))
    body.append(b"<< /Type /Pages /Kids [" + kids + b"] /Count %d >>" % len(pages))
    body.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    for i, lines in enumerate(pages):
        ops = [b"BT /F1 11 Tf 14 TL 72 740 Td"]
        for line in HEADER + lines:
            for wrapped in textwrap.wrap(line, 90) or [""]:
                ops.append(b"(" + _pdf_escape(wrapped) + b") Tj T*")
        ops.append(b"ET")
        stream = b"\n".join(ops)
        body.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R >>" % (5 + 2 * i)
        )
        body.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    out = b"%PDF-1.4\n"
    offsets = []
    for number, obj in enumerate(body, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + obj + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(body) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer << /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(body) + 1, xref)
    return out


# --- Samples -----------------------------------------------------------------


def make_samples(out: Path) -> list[Path]:
    rng = random.Random(2025)  # deterministic output
    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    def write(name: str) -> Path:
        path = out / name
        written.append(path)
        return path

    # 1. Digital PDF with a text layer.
    write("01_text_layer_report.pdf").write_bytes(text_layer_pdf(REPORT_PAGES))

    # 2. Clean 3-page scan (image-only PDF).
    pages = [
        add_scan_noise(render_page(lines, page_label=f"Page {n} of 3"), rng)
        for n, lines in enumerate(REPORT_PAGES, 1)
    ]
    save_pdf(pages, write("02_scanned_report_3p.pdf"))

    # 3. Phone photo: tilted, warm uneven light, slight blur, JPEG.
    photo = render_page(REPORT_PAGES[0]).rotate(2.5, expand=True, fillcolor=(90, 80, 70))
    shade = Image.linear_gradient("L").resize(photo.size).point(lambda v: 255 - v // 4)
    tint = Image.new("RGB", photo.size, (255, 240, 215))
    photo = Image.composite(photo, Image.blend(photo, tint, 0.35), shade)
    photo = ImageEnhance.Contrast(photo).enhance(0.75).filter(ImageFilter.GaussianBlur(1.0))
    photo.resize((photo.width * 3 // 4, photo.height * 3 // 4)).save(
        write("03_phone_photo.jpg"), format="JPEG", quality=80
    )

    # 4. Faded photocopy: page 1 fine; page 2 low-resolution, faded and speckled, so it
    #    reads with errors and low confidence (~65%) - something to correct on review.
    good = add_scan_noise(render_page(REPORT_PAGES[0], page_label="Page 1 of 2"), rng)
    bad = render_page(REPORT_PAGES[1], page_label="Page 2 of 2")
    bad = bad.resize((bad.width // 2, bad.height // 2)).resize(bad.size)
    bad = ImageEnhance.Contrast(bad).enhance(0.35).filter(ImageFilter.GaussianBlur(1.0))
    bad = add_scan_noise(bad, random.Random(2025), amount=200000)
    save_pdf([good, bad], write("04_faded_copy.pdf"))

    # 5. Mixed Filipino/English notes as a PNG.
    render_page(FILIPINO_NOTES).save(write("05_filipino_notes.png"), format="PNG")

    # 6. Broken PDF: starts with %PDF- so it passes upload checks, but is not a real PDF.
    write("06_broken.pdf").write_bytes(b"%PDF-1.4\nThis file is damaged on purpose.\n")

    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default="samples", help="output folder (default: samples)")
    args = parser.parse_args()
    for path in make_samples(Path(args.out)):
        print(f"wrote {path} ({path.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
