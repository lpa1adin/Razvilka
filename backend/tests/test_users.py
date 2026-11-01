from app.modules.auth.models import Role
from tests.conftest import PASSWORD, login_as, make_user


def test_admin_creates_user_and_reset_kills_sessions(admin_client):
    created = admin_client.post("/api/workshop/users", json={
        "login": "Masha", "display_name": "Маша", "role": "user", "password": "secret-123",
    })
    assert created.status_code == 201 and created.json()["login"] == "masha"
    assert admin_client.post("/api/workshop/users", json={
        "login": "masha", "display_name": "Дубль", "password": "secret-123",
    }).status_code == 409

    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as masha:
        assert masha.post("/api/auth/login", json={"login": "masha", "password": "secret-123"}).status_code == 200
        admin_client.post(f"/api/workshop/users/{created.json()['id']}/password", json={"password": "another-456"})
        assert masha.get("/api/auth/me").status_code == 401


def test_short_password_rejected(admin_client):
    response = admin_client.post("/api/workshop/users", json={"login": "kid", "display_name": "К", "password": "123"})
    assert response.status_code == 422


def test_user_cannot_list_users(client):
    make_user("anna", Role.user)
    login_as(client, "anna")
    assert client.get("/api/workshop/users").status_code == 403
    assert PASSWORD  # учётка из conftest
