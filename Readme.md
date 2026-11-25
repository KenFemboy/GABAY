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
Uploaded happens automatically on upload and on remove. The allowed transitions are defined in
one place, `Backend/app/services/assessment_status.py`, and Finalized can be reopened to
Needs Review.
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