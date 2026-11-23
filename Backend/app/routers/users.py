from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.errors import not_found
from app.core.permissions import require_admin
from app.db.session import get_db
from app.models.user import Role, User, UserStatus
from app.schemas.user import UserCreate, UserList, UserRead, UserUpdate
from app.services import user_service

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("", response_model=UserList)
def list_users(
    search: str | None = Query(default=None, max_length=100),
    role: Role | None = None,
    status_filter: UserStatus | None = Query(default=None, alias="status"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> UserList:
    items, total = user_service.list_users(
        db, search=search, role=role, status=status_filter, offset=offset, limit=limit
    )
    return UserList(items=[UserRead.model_validate(u) for u in items], total=total)


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> User:
    return user_service.create_user(db, payload)


@router.get("/{user_id}", response_model=UserRead)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise not_found("User not found.")
    return user


@router.patch("/{user_id}", response_model=UserRead)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise not_found("User not found.")
    return user_service.update_user(db, user, payload, acting_user=admin)
