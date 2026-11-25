# GABAY

Full-stack foundation for the GABAY application.

## Prerequisites

- Node.js 20+
- Python 3.11+
- PostgreSQL 15+

## Local setup

1. Create a PostgreSQL database named `gabay`.
2. Copy `Backend/.env.example` to `Backend/.env`, update `DATABASE_URL` if needed, and set
   `JWT_SECRET_KEY` to a random value:
   `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
3. Copy `Frontend/.env.example` to `Frontend/.env`.
4. Install and start the backend:

   ```powershell
   cd Backend
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   alembic upgrade head
   python -m app.scripts.create_admin --email you@school.edu.ph --name "Your Name"
   uvicorn app.main:app --reload
   ```

   `create_admin` prompts for a password (min. 10 characters) and creates the first
   System Administrator. There is no open registration; the administrator creates
   all other accounts from the **Users** page.

5. Install and start the frontend in a second terminal:

   ```powershell
   cd Frontend
   npm install
   npm run dev
   ```

The frontend is available at `http://localhost:5173`. The API is available at
`http://localhost:8000`, with interactive documentation at `/docs`.

## Foundation endpoints

- `GET /api/health` checks API and database availability.
- `GET /api/version` returns the API version.
- `GET /api/config/status` reports non-secret configuration status.

## Authentication and roles

- `POST /api/auth/login` – email + password, returns a JWT access token (60 min by default).
- `GET /api/auth/me` – the signed-in user (safe fields only).
- `POST /api/auth/change-password` – signs out all existing sessions.
- `POST /api/auth/logout` – client discards its token.
- `GET/POST /api/users`, `GET/PATCH /api/users/{id}` – System Administrator only.

Roles: `system_admin`, `sned_coordinator`, `teacher`, `school_head` (School Head / SNED Focal).
Passwords are hashed with Argon2id. Use `require_roles(...)` from `app/core/permissions.py`
to protect new endpoints; the frontend route/navigation checks are a usability layer only.

## Learners

The learner record is the centre of GABAY: assessments, IEPs, ILAW entries, progress records
and evaluations all carry a `learner_id`.

- `GET /api/learners` – list with `search` (name or code), `grade_level`, `section`,
  `school_year`, `status`, `offset`, `limit`.
- `POST /api/learners`, `GET/PATCH /api/learners/{id}` – learner codes are unique
  (case-insensitive). Learners are never deleted; set `status` to `transferred`,
  `graduated` or `inactive` instead.
- `GET /api/learners/{id}/summary` – count and latest status per module.
- `GET/POST /api/learners/{id}/assignments`, `DELETE /api/learners/{id}/assignments/{assignment_id}`
  – teacher assignments per school year. `GET /api/users/teachers` lists active Teachers for the picker.

Access: the SNED Coordinator manages all learners and assignments. The School Head can read
all learners. Teachers can read only the learners assigned to them for the learner's current
school year; other records return 404. The System Administrator has no learner access.
Later modules must call `learner_service.get_visible_learner(...)` before touching a learner's data.

For development, seed fake learners with `python -m app.scripts.seed_learners`.
**Never use real learner data in development.**

## Assessments and document storage

Each learner can have informal (section adviser) and formal (psychologist) assessments, and each
assessment can have one uploaded document.

- `GET /api/assessments?learner_id=`, `POST /api/assessments`, `GET /api/assessments/{id}`
- `POST /api/assessments/{id}/document` – multipart `file`. Only PDF, JPG and PNG files are
  accepted, up to `MAX_UPLOAD_MB` (default 15). The type is checked from the file's header bytes,
  not only its name. A file already uploaded for the same learner (same SHA-256) is rejected.
- `GET /api/assessments/{id}/document?download=false|true` – checks access, then returns
  `{url, expires_in}`: a signed URL that is valid for `SIGNED_URL_TTL_SECONDS` (default 60).
- `DELETE /api/assessments/{id}/document` – SNED Coordinator only. Not allowed while the
  assessment is processing or once it is finalized. Removing the document returns it to Draft.
- `PATCH /api/assessments/{id}/status` – body `{status}`, SNED Coordinator only. Only the
  transitions listed in `next_statuses` on the assessment are accepted; anything else returns
  409 `invalid_status_transition`.

Status flow: Draft → Uploaded → Processing → Processed → Needs Review → Finalized. Draft ↔
Uploaded happens automatically on upload and on remove, and Processing and its outcomes are set
by OCR (see below). The Coordinator moves Processed / Needs Review → Finalized, and can reopen
Finalized to Needs Review. All allowed transitions are defined in one place,
`Backend/app/services/assessment_status.py`.
The Coordinator and assigned Teachers can create assessments and upload documents. The School
Head can only view them.

Files never go into PostgreSQL. The database stores only metadata and a random storage key
(`assessments/{uuid}.pdf`). Storage is chosen with `STORAGE_BACKEND`:

- `local` (default) – files are saved under `Backend/storage/` (gitignored). Signed URLs point at
  `GET /api/files/{token}` on this API. No cloud keys are needed.
- `supabase` – a private Supabase Storage bucket. One-time setup:
  1. In the Supabase dashboard, go to **Storage**, create a bucket named `gabay-documents`, and
     leave **Public bucket** turned off.
  2. Optional, as a second check: set the bucket's file size limit to 15 MB and its allowed MIME
     types to `application/pdf, image/jpeg, image/png`.
  3. In `Backend/.env`, set `STORAGE_BACKEND=supabase`, `SUPABASE_URL`, and
     `SUPABASE_SERVICE_ROLE_KEY` (from **Project Settings → API**). This key bypasses Supabase's
     access rules, so keep it in the backend `.env` only. Never put it in `Frontend/.env` or
     commit it.

  No storage RLS policies are needed, because only the backend talks to the bucket.

## OCR processing

Uploaded documents are read by a background **OCR worker**. For each PDF page, the worker uses
the PDF's own text layer when there is one. Otherwise it renders the page at 300 DPI, converts
it to grayscale, resizes it and boosts the contrast, then runs Tesseract (`eng+fil`). Each page's
text and confidence are saved in page order. If one page fails, the rest of the document still
goes through. OCR text (`raw_text`) and the human-corrected text (`reviewed_text`) are kept apart.

- `POST /api/assessments/{id}/process` – Coordinator or assigned Teacher. Queues a job and
  returns **202** right away (status → Processing). Reprocessing from Processed / Needs Review
  replaces the OCR text and discards any corrections.
- `GET /api/assessments/{id}/ocr` – `{job, pages, summary}` for anyone who can see the learner.
- `PUT /api/assessments/{id}/ocr/pages/{n}` – body `{reviewed_text}` (`null` reverts to the OCR
  text). Allowed only while Processed or Needs Review.

When the job finishes, the assessment goes to **Processed** if every page was read with
confidence ≥ `OCR_REVIEW_CONFIDENCE` (default 70). If not, it goes to **Needs Review**. If no page
could be read, it goes back to **Uploaded**, with the error shown in the UI. The review screen
(**Review text** on an assessment) shows the original page next to editable text.

### Install Tesseract (development, Windows)

1. Download the Windows installer from the UB Mannheim build
   (https://github.com/UB-Mannheim/tesseract/wiki) and run it.
2. On **Choose Components → Additional language data**, tick **Filipino**. English is included by
   default.
3. In `Backend/.env`, set `TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe`.
4. Check that it works: `GET http://localhost:8000/api/config/status` should show
   `"ocr_available": true`.

On Debian/Ubuntu: `sudo apt install tesseract-ocr tesseract-ocr-eng tesseract-ocr-fil`, and leave
`TESSERACT_CMD` blank.

### Run the worker

In a third terminal, alongside the API and the frontend:

```powershell
cd Backend
.\.venv\Scripts\Activate.ps1
alembic upgrade head          # once, creates the ocr_jobs / ocr_pages tables
python -m app.workers.ocr_worker
```

If the worker isn't running, jobs stay queued and the assessment stays in Processing. Use
`python -m app.workers.ocr_worker --once` to process a single job and exit.

To get test documents, run `python -m app.scripts.make_ocr_samples`. It writes synthetic samples
to `Backend/samples/` (gitignored), one for each OCR outcome, and the expected results are listed
at the top of the script. Never use real learner documents in development.

### Docker (production)

`Backend/Dockerfile` installs Tesseract with English and Filipino. The same image runs either
process:

```bash
docker build -t gabay-backend Backend
docker run --env-file Backend/.env -p 8000:8000 gabay-backend                       # API
docker run --env-file Backend/.env gabay-backend python -m app.workers.ocr_worker   # worker
```

With local storage, both containers must share the storage directory (a volume). With Supabase,
they don't need to.

## Validation

```powershell
cd Frontend
npm run lint
npm run build

cd ..\Backend
python -m pytest
alembic upgrade head
alembic downgrade base
```

Never commit `.env` files or real credentials. Use the example files as the
template for local configuration.