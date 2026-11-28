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

## Information extraction

Once an assessment's OCR text has been reviewed and the assessment is **Finalized**, GABAY can
pull structured findings out of it in five categories: **diagnosis, strengths, needs, present
levels of performance and recommendations**. Each finding can carry a domain (reading,
mathematics, behavior/social, communication, motor, …) and a source reference: the page, the
character offsets and a quote of the text it came from.

Workflow: **Analysis** on a finalized assessment → **Run extraction** (creates draft *v1*) →
edit, add, delete or reorder findings → the **SNED Coordinator approves**. Running extraction
again, or **Edit as new draft**, creates *v2*, and so on. Approving a new version supersedes the
old one. Only one draft can be open per assessment.

Extraction is **rule-based** (`Backend/app/services/extraction/rules.py`), with no AI and no
network calls:
- Headings such as `III. BEHAVIOR AND SOCIAL SKILLS`, `RECOMMENDATIONS` and `Diagnosis:` split
  the text into sections.
- List items or sentences under Diagnosis, Strengths, Needs and Recommendations become findings.
- Each domain section becomes a present-level finding, and its sentences are sorted into
  strengths and needs using cue words in English and Filipino.
- A diagnosis is only taken from an explicitly labelled line.

The schema is in `Backend/app/services/extraction/schema.py`. AI extraction on de-identified
text is not built yet (`EXTRACTION_AI_ENABLED` is a placeholder).

- `POST /api/assessments/{id}/extractions` – run extraction (Coordinator or assigned Teacher).
- `GET /api/assessments/{id}/extractions`, `GET /api/extractions/{version_id}` – versions and findings.
- `POST/PATCH/DELETE /api/extractions/{version_id}/findings[/{finding_id}]`,
  `PUT /api/extractions/{version_id}/order` – edit a draft.
- `POST /api/extractions/{version_id}/copy` – edit as new draft.
- `POST /api/extractions/{version_id}/approve` – SNED Coordinator only.
- `DELETE /api/extractions/{version_id}` – discard a draft.
- `GET /api/learners/{id}/findings` – **approved findings only**, the input for goal matching.
  Backend code must use `extraction_service.approved_findings_for_learner()` for this and never
  read draft versions.

## Goal bank

The **Goal bank** (sidebar) holds measurable goals organised by **domain and skill**. The domain
codes are the same as the extraction finding domains.

**What a goal holds:**
- the goal statement (condition + behavior + criterion);
- a **measurement method** (percent accuracy, trials, frequency, duration, rate, rubric, checklist);
- a numeric **target** and unit, an optional criterion, and a grade band;
- a **status**: Draft → Active → Archived;
- a **version** number.

**Who can do what:** only the SNED Coordinator creates, edits, activates and archives goals, and
manages the domains and skills (**Domains & skills** tab). Teachers and the School Head can browse
active goals.

**Versioning:** editing a goal whose current version is *used* creates a new version, and the old
version is kept unchanged. A version counts as used once another record references it (for
example an IEP, through `goal_service.record_goal_usage()`). A goal that isn't used yet is edited
in place.

**Starter set:** a draft set of 9 domains, 30 skills and 50 measurable goals, waiting for the
Coordinator's review. Load it with:

```powershell
cd Backend
python -m app.scripts.seed_goal_bank     # safe to re-run; never overwrites existing goals
```

Everything is loaded as **Draft**. The Coordinator reviews each goal and activates it.

**Embeddings:** every active goal gets a vector from a local model
(`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` via fastembed, which runs on the
server with no API key).
- The model downloads once, about 240 MB, into `Backend/.models/`.
- Vectors are stored in PostgreSQL, one per goal version and model. Reindexing skips goals that
  haven't changed, refreshes edited ones, and removes vectors of archived goals and old versions,
  so running it again never creates duplicates.
- Indexing runs from the **Reindex** button or `python -m app.scripts.reindex_goals`. If the OCR
  worker is running, it also re-indexes automatically about once a minute when something changed.
- **Find similar** on the Goal bank page ranks active goals by similarity to any text, such as a
  finding.

Endpoints:
- `GET /api/goal-taxonomy`
- `POST/PATCH /api/goal-taxonomy/domains|skills`
- `GET/POST /api/goals`, `GET/PATCH/DELETE /api/goals/{id}`
- `POST /api/goals/{id}/activate|archive`
- `GET /api/goals/index-status`, `POST /api/goals/reindex`
- `GET /api/goals/search?q=`

## Semantic goal matching

**Goal suggestions** (a button on the learner profile) matches each **approved need** of the
learner against the **active** goal bank.

**How a run works:**
- Each need is embedded with the same model as the goals (see
  `docs/decisions/0001-embedding-model.md`).
- PostgreSQL finds the closest goals with **pgvector**: cosine distance, HNSW index.
- Filters: only goals in the need's **domain**, and only goals for the learner's **grade band**.
  Both are on by default and can be switched off per run.
- Goals below a **minimum similarity** are left out (`MATCH_MIN_SCORE`, default 0.35). The top
  `MATCH_TOP_K` (default 5) are kept.
- Each suggestion is saved with its **score, rank and model version**.

**What staff can do:**
- **Accept**, **Edit & accept** (learner-specific wording; the goal bank is not changed),
  **Reject** (with an optional reason), **Undo**, or **add a goal manually** from the bank.
- Accepting a goal locks its goal-bank version, so later bank edits create a new version.
- Running matching again keeps earlier decisions. **Selected goals** (the accepted ones) are what
  the IEP stage will use.
- The Coordinator and assigned Teachers can run matching and decide; the School Head can only
  view.

### Install pgvector (Windows, PostgreSQL 18)

pgvector has no official Windows installer. Use one of these:

1. **Prebuilt (community build):** download the PostgreSQL 18 zip of release **0.8.7** from
   https://github.com/andreiramani/pgvector_pgsql_windows/releases. Then, **as Administrator**:
   - copy `vector.dll` into `C:\Program Files\PostgreSQL\18\lib`;
   - copy `vector.control` and all `vector--*.sql` files into
     `C:\Program Files\PostgreSQL\18\share\extension`.

   This build is not made by the pgvector project.
2. **Build from source** (official). In the *x64 Native Tools Command Prompt for VS*, run as
   Administrator:
   ```bat
   set "PGROOT=C:\Program Files\PostgreSQL\18"
   cd %TEMP%
   git clone --branch v0.8.7 https://github.com/pgvector/pgvector.git
   cd pgvector
   nmake /F Makefile.win
   nmake /F Makefile.win install
   ```

Then, from `Backend/`, run `alembic upgrade head`. Migration 0008 runs `CREATE EXTENSION vector`
and moves the goal vectors into a `vector(384)` column. `GET /api/config/status` should then show
`"pgvector": "0.8.7"`.

Other setups:
- Docker: use the `pgvector/pgvector:pg18` image.
- Supabase: enable the `vector` extension under Database → Extensions.

The automated tests use SQLite, where the same search runs in numpy.

### Benchmark

```powershell
cd Backend
python -m app.scripts.benchmark_matching --out ..\docs\benchmarks
```

The benchmark has 68 synthetic needs: English, Filipino and OCR-style errors. Latest results with
the chosen model: **top-5 accuracy 97.1%**, top-1 79.4%, MRR 0.858 (domain filter on). With the
domain filter off, top-5 is also 97.1% against a random-ranking baseline of 15%. Filipino-only
needs score lowest, at 80% top-5. Full reports are in `docs/benchmarks/`.

Endpoints:
- `POST/GET /api/learners/{id}/matching-runs`, `GET /api/matching-runs/{id}`
- `GET /api/learners/{id}/recommendations/latest`, `GET /api/learners/{id}/selected-goals`
- `POST /api/recommendations/{id}/accept|reject|reset`, `PATCH /api/recommendations/{id}`
- `POST /api/learners/{id}/recommendations` (manual add), `DELETE /api/recommendations/{id}`
  (manual goals only)

## IEP builder

The **IEP** tab on the learner profile lists every IEP version.

**Creating a draft:** **Create IEP** makes a draft for the learner's school year and imports:
- every **approved finding** (present levels, strengths, needs, diagnosis, recommendations);
- every **accepted goal** from Goal suggestions, with its edited wording and target.

Both are saved as copies, so later re-extraction or goal-bank edits never change a saved IEP.
**Re-import** adds anything approved or accepted since; it never adds duplicates.

**What each goal holds:** statement, the need it addresses, baseline, target value, unit and
criterion, measurement method, responsible staff, start and target dates, and progress-review
dates. Default dates follow a June–May school year, with quarterly reviews.

**Before finalizing**, the checklist must be empty:
- **IEP:** valid dates, an annual review inside the period, at least one present level or need,
  at least one goal, and a team member with a name and role.
- **Each goal:** statement, measurement, baseline, target and unit, responsible staff, a target
  date inside the period, and review dates inside the period and on or before the target date.
- **Amendments:** a reason.

**Rules:**
- Only the SNED Coordinator finalizes. The Coordinator and assigned Teachers edit drafts; the
  School Head can view and download.
- A **finalized IEP is read-only in the API**: every change returns 409 `iep_read_only`.
- **Amend** (Coordinator, with a reason) copies the finalized version into a new draft version.
  Finalizing that version marks the previous one **Superseded**.
- **Download DOCX** generates a Word document from the saved record each time. Drafts carry a
  "DRAFT – NOT FINAL" banner. `SCHOOL_NAME` in `Backend/.env` sets the school name printed on it.

Endpoints:
- `GET/POST /api/learners/{id}/ieps`
- `GET/PATCH/DELETE /api/ieps/{id}`, `POST /api/ieps/{id}/import`
- `POST/PATCH/DELETE /api/ieps/{id}/findings[/{fid}]`
- `POST/PATCH/DELETE /api/ieps/{id}/goals[/{gid}]`, `PUT /api/ieps/{id}/goals/order`
- `GET /api/ieps/{id}/validation`, `POST /api/ieps/{id}/finalize`, `POST /api/ieps/{id}/amend`
- `GET /api/ieps/{id}/document` (DOCX)

## ILAW (daily learning activity log)

The **ILAW** tab on the learner profile is a log of activities done with the learner. Each
entry has a date, an activity title, a description, and optionally materials, the learner's
response, duration and notes.

**Rules:**
- An entry can only be logged when the learner has an **active IEP**: the *finalized* IEP for
  their current school year. Drafts and superseded versions are never used.
- The date can't be in the future and must fall inside the IEP period.
- **No duplicates:** the same learner, date and activity title is refused (409), even if the
  title's upper/lower case or spacing differs. The database enforces the same rule.

**Alignment with IEP goals:**
- When an entry is saved, GABAY suggests which goals of the active IEP the activity worked on.
  It uses the same local embedding model as goal matching, and keeps the top `ILAW_TOP_K`
  (default 3) goals with similarity ≥ `ILAW_MIN_SCORE` (default 0.35).
- Each suggestion is saved with its **score, rank and model version**
  (`<model>|ilaw-text-v1`).
- The teacher **confirms**, **rejects** or **changes** each link, or links another goal by hand.
  Each decision records who made it and when.
- **Re-suggest** keeps every decision and never creates duplicate links.
- After an IEP amendment is finalized, re-suggesting moves the entry to the new version.
  Decided links on the old version are kept as history.
- If the model is unavailable, the entry is still saved and goals can be linked by hand.

**Who can do what:** the SNED Coordinator and assigned Teachers log entries and decide links;
the School Head can only view.

Endpoints:
- `GET /api/learners/{id}/ilaw/active-iep`
- `GET/POST /api/learners/{id}/ilaw`
- `GET/PATCH/DELETE /api/ilaw/{id}`, `POST /api/ilaw/{id}/suggest`
- `POST /api/ilaw/{id}/links`
- `POST /api/ilaw-links/{id}/confirm|reject|reset|change`

## Progress monitoring

The **Progress** tab on the learner profile shows one card per goal of the active (finalized)
IEP. Each card has a chart, a status, and **Add data point**.

**Evidence types:**

| Type | Needs |
|---|---|
| Data probe, work sample, test | a goal and a measured value |
| Observation | a note; a goal and value are optional |
| Grade | subject, grading period (Q1–Q4 or final) and a grade from 0 to 100; a goal is optional |

**Value rules, taken from the goal's measurement method.** The unit always comes from the goal.

| Method | Allowed value |
|---|---|
| Percent accuracy, checklist | 0–100 %, or *correct / total*, saved as a percent |
| Trials | successes plus *out of*, with successes ≤ out of |
| Frequency | a whole number |
| Duration | minutes > 0 (at most 480) |
| Rate | per minute > 0 |
| Rubric | a whole number from 0 to 10 |

The date must be inside the IEP period and not in the future. Invalid entries return 422 with
the problem fields.

**Chart:** data points, a dashed **aim line** from the baseline (at the goal's start date) to
the target (at the target date), the target line, and faint review-date marks. Hover shows a
tooltip, and a table view is available. Grades aren't plotted on goal charts; they are listed
under the card and in the timeline.

**Status:**
- **Below aim line** when the median of the last 3 points is behind the aim line. A goal whose
  target is lower than its baseline (fewer call-outs, for example) counts as behind when it is
  *above* the line.
- **Target met** when the latest point reaches the target.
- **No recent data** when nothing has been recorded for more than 30 days, and **No data yet**
  when nothing has been recorded more than 30 days after the goal started.
- **No numeric baseline** when the IEP goal has no baseline value.

**Timeline:** ILAW activities, data points, observations and grades in one list, filterable by
type and date.

**Progress alerts** (sidebar and dashboard; Coordinator and School Head) lists goals of
finalized IEPs that are below the aim line or missing data. Teachers who call the endpoint see
only their assigned learners.

Endpoints:
- `GET /api/learners/{id}/progress/goals`, `GET /api/iep-goals/{id}/progress`
- `GET/POST /api/learners/{id}/progress`, `PATCH/DELETE /api/progress/{id}`
- `GET /api/learners/{id}/timeline?types=&from=&to=`
- `GET /api/progress/attention?status=`

## Year-end evaluation

The **Evaluations** tab on the learner profile holds one year-end evaluation per school year:
- an overall summary;
- a rating and narrative for each goal of the active IEP;
- strengths;
- recommendations for next year.

**Write manually** is always available. It starts from a skeleton built from the year's
evidence: per goal, the baseline, number of data points, first and last values, target and
linked activities, plus a suggested rating from the progress status.

**Generate with AI…** (optional, uses OpenAI):
1. **Turn it on** in `Backend/.env` with `EVALUATION_AI_ENABLED=true`, `OPENAI_API_KEY=…` and
   `OPENAI_MODEL=<model id>`. There is no default model, and the key stays on the server.
2. **Preview:** staff see the **exact de-identified evidence package** first.
   - Names, learner code, birth date, staff and team names, school name, emails, phone numbers
     and calendar dates are removed. Dates become "week N" of the IEP.
   - Every item has an evidence ID: `G1` goals, `F` findings, `P` data points, `A` activities,
     `O` observations, `R` grades.
   - If a known identifier slips through, sending is blocked.
3. **Generate draft** sends the package with the versioned prompt
   (`app/prompts/year_end_evaluation/v1.md`, version `year-end-v1`). The prompt's grounding
   rules: use only the package, cite evidence IDs for every statement, invent nothing, and
   keep each rating consistent with the computed goal status.
4. **Validation:** the response must match a JSON schema, contain one entry per goal, cite only
   known IDs, keep ratings consistent, and contain no identifiers.
   - If it fails, the model is asked once more with the errors listed.
   - If that also fails, or the API is unavailable, a **manual draft** is saved instead and the
     reason is shown.
5. **Saved provenance:** each AI draft stores the model id, prompt version, evidence IDs, the
   evidence hash, the exact package sent and the raw (de-identified) response.

**Who can do what:** the SNED Coordinator and assigned Teachers create and edit drafts; only the
Coordinator **finalizes**, after which the evaluation is read-only. The School Head can view.

To test the AI path once, set the three settings, open **Generate with AI…** on a learner with
a finalized IEP and progress data, check the preview and generate. Then set a wrong key and
confirm it falls back to a manual draft.

Endpoints:
- `GET /api/learners/{id}/evaluations`, `GET /api/learners/{id}/evaluations/preview`
- `POST /api/learners/{id}/evaluations/generate` `{evidence_hash}`,
  `POST /api/learners/{id}/evaluations/manual`
- `GET/PATCH/DELETE /api/evaluations/{id}`, `POST /api/evaluations/{id}/finalize`

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