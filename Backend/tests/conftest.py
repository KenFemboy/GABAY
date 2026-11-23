"""Test fixtures: an isolated in-memory SQLite database per test.

No real learner data is used; all accounts are synthetic.
"""

import os

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-that-is-long-enough-1234567890")

from collections.abc import Callable, Generator  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import app.models  # noqa: E402,F401
from app.core.security import hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.user import Role, User, UserStatus  # noqa: E402

DEFAULT_PASSWORD = "correct-horse-battery"


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def make_user(db_session: Session) -> Callable[..., User]:
    counter = {"n": 0}

    def _make(
        role: Role = Role.TEACHER,
        status: UserStatus = UserStatus.ACTIVE,
        email: str | None = None,
        password: str = DEFAULT_PASSWORD,
    ) -> User:
        counter["n"] += 1
        user = User(
            name=f"Test {role.value} {counter['n']}",
            email=email or f"{role.value}{counter['n']}@example.test",
            password_hash=hash_password(password),
            role=role.value,
            status=status.value,
            token_version=0,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        return user

    return _make


@pytest.fixture
def login(client: TestClient) -> Callable[[User], dict[str, str]]:
    def _login(user: User, password: str = DEFAULT_PASSWORD) -> dict[str, str]:
        response = client.post("/api/auth/login", json={"email": user.email, "password": password})
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return _login
