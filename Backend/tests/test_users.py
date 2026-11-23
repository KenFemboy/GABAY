import pytest

from app.models.user import Role, UserStatus


@pytest.mark.parametrize("role", [Role.TEACHER, Role.SNED_COORDINATOR, Role.SCHOOL_HEAD])
def test_non_admin_roles_cannot_manage_users(client, make_user, login, role):
    headers = login(make_user(role))

    assert client.get("/api/users", headers=headers).status_code == 403
    response = client.post(
        "/api/users",
        headers=headers,
        json={"name": "X", "email": "x@example.test", "password": "long-enough-pw", "role": "teacher"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_users_endpoints_require_authentication(client):
    assert client.get("/api/users").status_code == 401


def test_admin_can_create_list_and_update_users(client, make_user, login):
    admin = make_user(Role.SYSTEM_ADMIN)
    headers = login(admin)

    created = client.post(
        "/api/users",
        headers=headers,
        json={
            "name": "  Maria Santos ",
            "email": "Maria.Santos@Example.test",
            "password": "initial-password",
            "role": "teacher",
        },
    )
    assert created.status_code == 201, created.text
    new_user = created.json()
    assert new_user["name"] == "Maria Santos"
    assert new_user["email"] == "maria.santos@example.test"
    assert new_user["status"] == "active"
    assert "password_hash" not in new_user

    listing = client.get("/api/users", headers=headers, params={"search": "maria"})
    assert listing.status_code == 200
    assert listing.json()["total"] == 1

    by_role = client.get("/api/users", headers=headers, params={"role": "system_admin"})
    assert [u["id"] for u in by_role.json()["items"]] == [admin.id]

    updated = client.patch(
        f"/api/users/{new_user['id']}",
        headers=headers,
        json={"role": "sned_coordinator", "status": "inactive"},
    )
    assert updated.status_code == 200
    assert updated.json()["role"] == "sned_coordinator"
    assert updated.json()["status"] == "inactive"


def test_duplicate_email_is_rejected(client, make_user, login):
    admin = make_user(Role.SYSTEM_ADMIN)
    existing = make_user(Role.TEACHER)
    response = client.post(
        "/api/users",
        headers=login(admin),
        json={"name": "Dup", "email": existing.email.upper(), "password": "long-enough-pw", "role": "teacher"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_taken"


def test_invalid_role_is_rejected(client, make_user, login):
    admin = make_user(Role.SYSTEM_ADMIN)
    response = client.post(
        "/api/users",
        headers=login(admin),
        json={"name": "Bad", "email": "bad@example.test", "password": "long-enough-pw", "role": "superuser"},
    )
    assert response.status_code == 422


def test_admin_cannot_demote_or_deactivate_self(client, make_user, login):
    admin = make_user(Role.SYSTEM_ADMIN)
    headers = login(admin)

    demote = client.patch(f"/api/users/{admin.id}", headers=headers, json={"role": "teacher"})
    assert demote.status_code == 400
    assert demote.json()["error"]["code"] == "cannot_change_own_role"

    deactivate = client.patch(f"/api/users/{admin.id}", headers=headers, json={"status": "inactive"})
    assert deactivate.status_code == 400


def test_admin_password_reset_invalidates_user_sessions(client, make_user, login):
    admin = make_user(Role.SYSTEM_ADMIN)
    teacher = make_user(Role.TEACHER)
    teacher_headers = login(teacher)

    response = client.patch(
        f"/api/users/{teacher.id}", headers=login(admin), json={"password": "reset-password-123"}
    )
    assert response.status_code == 200
    assert client.get("/api/auth/me", headers=teacher_headers).status_code == 401


def test_deactivated_user_cannot_log_in_after_admin_change(client, make_user, login):
    admin = make_user(Role.SYSTEM_ADMIN)
    teacher = make_user(Role.TEACHER)
    client.patch(f"/api/users/{teacher.id}", headers=login(admin), json={"status": UserStatus.INACTIVE})
    response = client.post(
        "/api/auth/login", json={"email": teacher.email, "password": "correct-horse-battery"}
    )
    assert response.status_code == 403


def test_get_missing_user_returns_404(client, make_user, login):
    admin = make_user(Role.SYSTEM_ADMIN)
    response = client.get("/api/users/99999", headers=login(admin))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
