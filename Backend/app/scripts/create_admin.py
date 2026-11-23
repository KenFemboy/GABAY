"""Create the initial System Administrator account.

GABAY has no open registration; run this once per environment:

    python -m app.scripts.create_admin --email admin@school.edu.ph --name "System Admin"

The password is prompted for (not passed on the command line, so it does not
end up in shell history). Set GABAY_ADMIN_PASSWORD to run non-interactively.
"""

import argparse
import getpass
import os
import sys

from pydantic import ValidationError

from app.core.errors import APIError
from app.db.session import SessionLocal
from app.models.user import Role
from app.schemas.user import UserCreate


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a GABAY System Administrator.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", default="System Administrator")
    args = parser.parse_args()

    password = os.environ.get("GABAY_ADMIN_PASSWORD")
    if not password:
        password = getpass.getpass("Password: ")
        if password != getpass.getpass("Confirm password: "):
            print("Passwords do not match.", file=sys.stderr)
            return 1

    try:
        data = UserCreate(name=args.name, email=args.email, password=password, role=Role.SYSTEM_ADMIN)
    except ValidationError as exc:
        for err in exc.errors():
            print(f"{'.'.join(map(str, err['loc']))}: {err['msg']}", file=sys.stderr)
        return 1

    # Imported here so --help works without a database.
    from app.services.user_service import create_user

    with SessionLocal() as db:
        try:
            user = create_user(db, data)
        except APIError as exc:
            print(exc.message, file=sys.stderr)
            return 1
    print(f"Created System Administrator {user.email} (id {user.id}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
