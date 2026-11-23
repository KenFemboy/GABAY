from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import get_settings
from app.models.user import Role, UserStatus
DEFAULT_PASSWORD = "correct-horse-battery"  # matches conftest


def test_login_returns_token_and_safe_user(client, make_user):
    user = make_user(Role.SNED_COORDINATOR)

    response = client.post(
        "/api/auth/login", json={"email": user.email.upper(), "password": DEFAULT_PASSWORD}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["user"]["email"] == user.email
    assert body["user"]["role"] == "sned_coordinator"
    assert "password_hash" not in body["user"]
    assert "password" not in response.text


def test_password_is_stored_hashed(make_user):
    user = make_user()
    assert user.password_hash != DEFAULT_PASSWORD
    assert user.password_hash.startswith("$argon2id$")


def test_wrong_password_is_rejected(client, make_user):
    user = make_user()
    response = client.post("/api/auth/login", json={"email": user.email, "password": "wrong-password"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


def test_unknown_email_gets_same_error_as_wrong_password(client):
    response = client.post(
        "/api/auth/login", json={"email": "nobody@example.test", "password": "whatever-123"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


def test_inactive_user_cannot_log_in(client, make_user):
    user = make_user(status=UserStatus.INACTIVE)
    response = client.post("/api/auth/login", json={"email": user.email, "password": DEFAULT_PASSWORD})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "account_inactive"


def test_me_requires_token(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


def test_me_rejects_invalid_token(client):
    response = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_token"


def test_me_rejects_token_signed_with_other_key(client, make_user):
    user = make_user()
    now = datetime.now(UTC)
    forged = jwt.encode(
        {"sub": str(user.id), "ver": 0, "type": "access", "iat": now, "exp": now + timedelta(minutes=5)},
        "some-other-secret-key-that-is-long-enough",
        algorithm="HS256",
    )
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_token"


def test_me_reports_expired_token(client, make_user):
    user = make_user()
    settings = get_settings()
    past = datetime.now(UTC) - timedelta(hours=2)
    expired = jwt.encode(
        {"sub": str(user.id), "ver": 0, "type": "access", "iat": past, "exp": past + timedelta(minutes=1)},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "token_expired"


def test_me_returns_current_user(client, make_user, login):
    user = make_user(Role.SCHOOL_HEAD)
    response = client.get("/api/auth/me", headers=login(user))
    assert response.status_code == 200
    assert response.json()["id"] == user.id
    assert response.json()["role"] == "school_head"


def test_deactivated_user_token_stops_working(client, make_user, login, db_session):
    user = make_user()
    headers = login(user)
    user.status = UserStatus.INACTIVE.value
    db_session.commit()

    response = client.get("/api/auth/me", headers=headers)
    assert response.status_code == 401


def test_change_password_flow(client, make_user, login):
    user = make_user()
    headers = login(user)

    bad = client.post(
        "/api/auth/change-password",
        headers=headers,
        json={"current_password": "wrong-password", "new_password": "a-brand-new-password"},
    )
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "invalid_current_password"

    short = client.post(
        "/api/auth/change-password",
        headers=headers,
        json={"current_password": DEFAULT_PASSWORD, "new_password": "short"},
    )
    assert short.status_code == 422
    assert short.json()["error"]["details"][0]["field"] == "new_password"

    ok = client.post(
        "/api/auth/change-password",
        headers=headers,
        json={"current_password": DEFAULT_PASSWORD, "new_password": "a-brand-new-password"},
    )
    assert ok.status_code == 204

    # Old token is invalidated, old password no longer works, new one does.
    assert client.get("/api/auth/me", headers=headers).status_code == 401
    old = client.post("/api/auth/login", json={"email": user.email, "password": DEFAULT_PASSWORD})
    assert old.status_code == 401
    new = client.post("/api/auth/login", json={"email": user.email, "password": "a-brand-new-password"})
    assert new.status_code == 200


def test_logout_requires_auth_and_succeeds(client, make_user, login):
    user = make_user()
    assert client.post("/api/auth/logout").status_code == 401
    assert client.post("/api/auth/logout", headers=login(user)).status_code == 204
