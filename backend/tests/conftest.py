import os

# Тесты работают с отдельной БД (создаётся скриптом ops/postgres/init.sql), а не с рабочей.
os.environ["RZ_DATABASE_URL"] = os.environ.get(
    "RZ_TEST_DATABASE_URL", "postgresql+psycopg://razvilka:razvilka@postgres:5432/razvilka_test"
)
for key in ("RZ_ADMIN_LOGIN", "RZ_ADMIN_PASSWORD", "RZ_USER_LOGIN", "RZ_USER_PASSWORD"):
    os.environ.pop(key, None)

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.db import SessionLocal, engine
from app.main import app
from app.models import Base
from app.modules.auth.models import Role
from app.modules.auth.service import create_user

PASSWORD = "test-password-123"


@pytest.fixture(autouse=True)
def no_reviewer_gate(request, monkeypatch):
    """Публикация задания требует ревью эталона (этап 5). В тестах других модулей этот шаг считаем пройденным;
    тесты Ревьюера помечены @pytest.mark.reviewer и проверяют его по-настоящему."""
    if request.node.get_closest_marker("reviewer") is None:
        from app.modules.review import service as review_service

        monkeypatch.setattr(review_service, "reference_problems", lambda db, task: [])


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.create_all(engine)
    yield
    with engine.begin() as conn:
        tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def make_user(login: str, role: Role) -> None:
    with SessionLocal() as db:
        create_user(db, login, PASSWORD, role)


def login_as(client: TestClient, login: str) -> None:
    response = client.post("/api/auth/login", json={"login": login, "password": PASSWORD})
    assert response.status_code == 200, response.text


@pytest.fixture
def admin_client(client):
    make_user("boss", Role.admin)
    login_as(client, "boss")
    return client


def make_fragment(title: str, text: str, source_slug: str = "mdn-ru", **extra) -> int:
    """Фрагмент в библиотеке без настоящего импорта."""
    from sqlalchemy import select

    from app.modules.library.importer import ensure_source
    from app.modules.library.models import Fragment, Source
    from app.modules.library.sources import SOURCES

    with SessionLocal() as db:
        source = db.scalar(select(Source).where(Source.slug == source_slug)) or ensure_source(db, SOURCES[source_slug])
        fragment = Fragment(
            source_id=source.id, external_id=extra.pop("external_id", f"files/{title}.md"), title=title,
            url="https://example.org/" + title, content_html=f"<p>{text}</p>", plain_text=text, excerpt=text,
            content_hash="x", source_commit="abc", **extra,
        )
        db.add(fragment)
        db.commit()
        return fragment.id
