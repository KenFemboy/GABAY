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