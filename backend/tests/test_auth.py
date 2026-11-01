from datetime import UTC, datetime, timedelta

from app.core.db import SessionLocal
from app.modules.auth.models import Role, UserSession
from tests.conftest import PASSWORD, login_as, make_user


def test_login_sets_httponly_cookie_and_me_returns_user(client):
    make_user("anna", Role.user)
    response = client.post("/api/auth/login", json={"login": "Anna ", "password": PASSWORD})
    assert response.status_code == 200
    assert "httponly" in response.headers["set-cookie"].lower()
    assert client.get("/api/auth/me").json()["login"] == "anna"


def test_wrong_password_and_unknown_login_give_same_answer(client):
    make_user("anna", Role.user)
    wrong = client.post("/api/auth/login", json={"login": "anna", "password": "nope"})
    unknown = client.post("/api/auth/login", json={"login": "ghost", "password": "nope"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_session_token_is_stored_hashed(client):
    make_user("anna", Role.user)
    login_as(client, "anna")
    token = client.cookies.get("rz_session")
    with SessionLocal() as db:
        stored = db.query(UserSession).one()
    assert stored.token_hash != token and len(stored.token_hash) == 64


def test_logout_kills_session(client):
    make_user("anna", Role.user)
    login_as(client, "anna")
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401


def test_expired_session_is_rejected(client):
    make_user("anna", Role.user)
    login_as(client, "anna")
    with SessionLocal() as db:
        db.query(UserSession).update({"expires_at": datetime.now(UTC) - timedelta(minutes=1)})
        db.commit()
    assert client.get("/api/auth/me").status_code == 401


def test_workshop_requires_admin_on_server(client):
    assert client.get("/api/workshop/overview").status_code == 401

    make_user("anna", Role.user)
    login_as(client, "anna")
    assert client.get("/api/workshop/overview").status_code == 403

    make_user("boss", Role.admin)
    login_as(client, "boss")
    overview = client.get("/api/workshop/overview")
    assert overview.status_code == 200
    assert overview.json()["users"] == {"user": 1, "admin": 1}


def test_session_endpoint_never_401(client):
    assert client.get("/api/auth/session").json() == {"user": None}
    make_user("anna", Role.user)
    login_as(client, "anna")
    assert client.get("/api/auth/session").json()["user"]["login"] == "anna"

