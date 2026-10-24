from datetime import UTC, datetime, timedelta

import jwt

from app.config import settings
from tests.conftest import TEST_PASSWORD

REGISTER_URL = "/api/v1/users/register"
LOGIN_URL = "/api/v1/users/token"
ME_URL = "/api/v1/users/me"


# ---------- Register ----------


def test_register(client):
    data = {"email": "nora@example.com", "full_name": "Nora Keller", "password": "nora-password"}

    response = client.post(REGISTER_URL, json=data)

    assert response.status_code == 201
    assert response.json()["email"] == "nora@example.com"
    assert "hashed_password" not in response.json()


def test_register_with_existing_email_fails(client, user):
    data = {"email": user.email, "full_name": "Copy", "password": "another-password"}

    response = client.post(REGISTER_URL, json=data)

    assert response.status_code == 409


def test_register_with_short_password_fails(client):
    data = {"email": "nora@example.com", "full_name": "Nora", "password": "short"}

    response = client.post(REGISTER_URL, json=data)

    assert response.status_code == 422


# ---------- Login ----------


def test_login(client, user):
    response = client.post(LOGIN_URL, data={"username": user.email, "password": TEST_PASSWORD})

    assert response.status_code == 200
    assert "access_token" in response.json()


def test_login_with_wrong_password_fails(client, user):
    response = client.post(LOGIN_URL, data={"username": user.email, "password": "wrong-pass"})

    assert response.status_code == 401


# ---------- Read profile ----------


def test_read_profile(client, user, user_headers):
    response = client.get(ME_URL, headers=user_headers)

    assert response.status_code == 200
    assert response.json()["email"] == user.email


def test_read_profile_without_token_fails(client):
    response = client.get(ME_URL)

    assert response.status_code == 401


def test_read_profile_with_invalid_token_fails(client):
    response = client.get(ME_URL, headers={"Authorization": "Bearer not-a-token"})

    assert response.status_code == 401


def test_read_profile_with_expired_token_fails(client, user):
    # Build by hand a token that expired one minute ago
    expired = datetime.now(UTC) - timedelta(minutes=1)
    token = jwt.encode({"sub": str(user.id), "exp": expired}, settings.secret_key, "HS256")

    response = client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


# ---------- Update profile ----------


def test_update_name(client, user_headers):
    response = client.patch(ME_URL, json={"full_name": "Anna Keller"}, headers=user_headers)

    assert response.status_code == 200
    assert response.json()["full_name"] == "Anna Keller"


def test_update_password(client, user, user_headers):
    client.patch(ME_URL, json={"password": "new-password"}, headers=user_headers)

    old_login = client.post(LOGIN_URL, data={"username": user.email, "password": TEST_PASSWORD})
    new_login = client.post(LOGIN_URL, data={"username": user.email, "password": "new-password"})

    assert old_login.status_code == 401
    assert new_login.status_code == 200


def test_update_email(client, user_headers):
    response = client.patch(ME_URL, json={"email": "anna@new-company.ch"}, headers=user_headers)

    assert response.status_code == 200
    assert response.json()["email"] == "anna@new-company.ch"


def test_update_email_already_used_fails(client, user_headers):
    luca = {"email": "luca@example.com", "full_name": "Luca Rossi", "password": "luca-password"}
    client.post(REGISTER_URL, json=luca)

    response = client.patch(ME_URL, json={"email": "luca@example.com"}, headers=user_headers)

    assert response.status_code == 409


def test_update_ignores_null_values(client, user, user_headers):
    response = client.patch(ME_URL, json={"full_name": None}, headers=user_headers)

    assert response.status_code == 200
    assert response.json()["full_name"] == user.full_name


def test_update_cannot_make_yourself_admin(client, user_headers):
    response = client.patch(ME_URL, json={"is_admin": True}, headers=user_headers)

    assert response.status_code == 200
    assert response.json()["is_admin"] is False


def test_update_with_short_password_fails(client, user_headers):
    response = client.patch(ME_URL, json={"password": "short"}, headers=user_headers)

    assert response.status_code == 422


# ---------- Health ----------


def test_health(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert "X-Process-Time" in response.headers  # added by the middleware
