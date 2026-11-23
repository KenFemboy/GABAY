from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import APIError, conflict
from app.core.security import hash_password, password_needs_rehash, verify_password
from app.models.user import Role, User, UserStatus
from app.schemas.user import UserCreate, UserUpdate


def get_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email.strip().lower()))


def authenticate(db: Session, email: str, password: str) -> User:
    """Return the user for valid, active credentials; raise otherwise.

    Wrong email and wrong password return the same error so the response does
    not reveal which accounts exist.
    """
    user = get_by_email(db, email)
    # Always run a hash verification, even for unknown emails (constant-ish timing).
    password_ok = verify_password(password, user.password_hash if user else None)
    if user is None or not password_ok:
        raise APIError(401, "invalid_credentials", "Incorrect email or password.")
    if not user.is_active:
        raise APIError(403, "account_inactive", "This account is inactive. Contact your administrator.")

    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    user.last_login_at = datetime.now(UTC)
    db.commit()
    db.refresh(user)
    return user


def change_password(db: Session, user: User, current_password: str, new_password: str) -> None:
    if not verify_password(current_password, user.password_hash):
        raise APIError(400, "invalid_current_password", "The current password is incorrect.")
    if current_password == new_password:
        raise APIError(400, "password_unchanged", "Choose a password different from the current one.")
    user.password_hash = hash_password(new_password)
    user.token_version += 1  # sign out other sessions
    db.commit()


def list_users(
    db: Session,
    *,
    search: str | None = None,
    role: Role | None = None,
    status: UserStatus | None = None,
    offset: int = 0,
    limit: int = 50,
) -> tuple[list[User], int]:
    query = select(User)
    if search:
        pattern = f"%{search.strip().lower()}%"
        query = query.where(func.lower(User.name).like(pattern) | User.email.like(pattern))
    if role:
        query = query.where(User.role == role.value)
    if status:
        query = query.where(User.status == status.value)

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(query.order_by(User.name, User.id).offset(offset).limit(limit)).all()
    return list(items), total


def create_user(db: Session, data: UserCreate) -> User:
    if get_by_email(db, data.email):
        raise conflict("email_taken", "A user with this email already exists.")
    user = User(
        name=data.name,
        email=data.email,
        password_hash=hash_password(data.password),
        role=data.role.value,
        status=UserStatus.ACTIVE.value,
        token_version=0,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise conflict("email_taken", "A user with this email already exists.") from exc
    db.refresh(user)
    return user


def update_user(db: Session, user: User, data: UserUpdate, acting_user: User) -> User:
    changes = data.model_dump(exclude_unset=True)

    if user.id == acting_user.id:
        # Prevent administrators from locking themselves (and possibly everyone) out.
        if "role" in changes and changes["role"] != user.role:
            raise APIError(400, "cannot_change_own_role", "You cannot change your own role.")
        if changes.get("status") == UserStatus.INACTIVE:
            raise APIError(400, "cannot_deactivate_self", "You cannot deactivate your own account.")

    if "email" in changes and changes["email"] != user.email:
        if get_by_email(db, changes["email"]):
            raise conflict("email_taken", "A user with this email already exists.")
        user.email = changes["email"]
    if changes.get("name") is not None:
        user.name = changes["name"]
    if changes.get("role") is not None:
        user.role = Role(changes["role"]).value
    if changes.get("status") is not None:
        new_status = UserStatus(changes["status"]).value
        if new_status != user.status and new_status == UserStatus.INACTIVE.value:
            user.token_version += 1
        user.status = new_status
    if changes.get("password") is not None:
        user.password_hash = hash_password(changes["password"])
        user.token_version += 1

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise conflict("email_taken", "A user with this email already exists.") from exc
    db.refresh(user)
    return user
