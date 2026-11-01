"""Сдачи и Оценщик: файлы сдачи, конвейер автотесты → Ревьюер → Оценщик, «сказал ≠ сделал», журнал развилок."""

import base64
import io
import zipfile

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.modules.agent import claude
from app.modules.assess import service
from app.modules.assess.models import Submission
from app.modules.assess.schemas import EvaluatorReport
from app.modules.auth.models import Role
from app.modules.jobs.models import Job
from app.modules.review.schemas import ModelReport
from tests.conftest import login_as, make_user

# Ученик пишет «PostgreSQL», а в коде — SQLite (критерий приёмки этапа 6)
STORAGE = '''import sqlite3
from pathlib import Path

DB = Path(__file__).with_name("hikes.db")


def _conn():
    conn = sqlite3.connect(DB)
    conn.execute("CREATE TABLE IF NOT EXISTS hikes (id INTEGER PRIMARY KEY, name TEXT, km REAL)")
    return conn


def add_hike(name, km):
    with _conn() as conn:
        return conn.execute("INSERT INTO hikes (name, km) VALUES (?, ?)", (name, km)).lastrowid


def list_hikes():
    with _conn() as conn:
        return [{"id": i, "name": n, "km": k} for i, n, k in conn.execute("SELECT id, name, km FROM hikes ORDER BY id")]


def total_km():
    with _conn() as conn:
        return conn.execute("SELECT COALESCE(SUM(km), 0) FROM hikes").fetchone()[0]
'''

ANSWERS = {
    "storage": {"choice": "PostgreSQL с миграциями Alembic", "alternatives": "SQLite, JSON-файл",
                "reasons": "Нужна надёжность при одновременной записи двух администраторов, Postgres это умеет.",
                "risks": "Нужно держать сервер базы", "revisit": "Если записей станет больше миллиона"},
    "schema": {"choice": "Миграции Alembic", "reasons": "Каждое изменение схемы — отдельная миграция, её можно повторить и откатить."},
}


def make_zip(files: dict[str, str | bytes]) -> str:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return base64.b64encode(buf.getvalue()).decode()


@pytest.fixture
def seeded():
    with SessionLocal() as db:
        return service.seed_all(db)


@pytest.fixture
def fake(monkeypatch):
    seen = {}

    def run_structured(purpose, prompt, system, schema, **kwargs):
        seen[purpose] = {"prompt": prompt, "system": system, "kwargs": kwargs}
        return seen["answers"][purpose]

    monkeypatch.setattr(claude, "configured", lambda: True)
    monkeypatch.setattr(claude, "run_structured", run_structured)
    seen["answers"] = {"review": ModelReport(findings=[])}
    return seen


def evaluator_answer(**extra) -> EvaluatorReport:
    criteria = [{"id": f"R{i}", "score": s, "explanation": "…", "evidence": [{"file": "storage.py", "line": 8, "note": "sqlite3"}]}
                for i, s in zip(range(1, 8), [4, 3, 2, 2, 1, 4, 2])]
    return EvaluatorReport.model_validate({
        "criteria": criteria,
        "mismatches": [
            {"fork_id": "storage", "claim": "PostgreSQL с миграциями Alembic", "file": "storage.py", "line": 8,
             "code_says": "sqlite3.connect — локальный файл SQLite", "why": "Заявленные свойства Postgres в коде отсутствуют"},
            {"fork_id": "schema", "claim": "Миграции Alembic", "file": "storage.py", "line": 999, "code_says": "…", "why": "…"},  # нет строки
            {"fork_id": "storage", "claim": "Используем Redis для кэша", "file": "storage.py", "line": 9, "code_says": "…", "why": "…"},  # не цитата
        ],
        "contradictions": [],
        "reference_view": [{"fork_id": "storage", "reference": "Для одного сервера хватило бы SQLite — но тогда так и надо было написать."}],
        "summary": "Выбор не совпадает с реализацией.",
        **extra,
    })


def run_pipeline():
    """Очереди runner и review по порядку, как это делают воркеры."""
    with SessionLocal() as db:
        for _ in range(4):
            job = db.scalar(select(Job).where(Job.status == "queued", Job.kind.in_(["runner", "review"])).order_by(Job.id))
            if job is None:
                return
            job.status = "done"
            db.commit()
            if job.payload["type"] == "test_submission":
                service.run_tests(db, int(job.payload["submission_id"]))
            else:
                service.run_assessment(db, int(job.payload["submission_id"]))


def test_seed_is_idempotent(seeded):
    assert seeded["assignments_created"] == 2
    with SessionLocal() as db:
        assert service.seed_all(db)["assignments_created"] == 0
        assert [c["id"] for c in service.active_rubric(db).criteria] == [f"R{i}" for i in range(1, 8)]


def test_zip_is_filtered_and_root_folder_stripped():
    from app.modules.assess.sources import from_zip

    data = base64.b64decode(make_zip({
        "hikes/storage.py": STORAGE, "hikes/.env": "SECRET=1", "hikes/node_modules/x/index.js": "x",
        "hikes/logo.png": b"\x89PNG\x00\x01", "hikes/static/vendor/lib.min.js": "var a=1;",
    }))
    files, vendor, warnings = from_zip(data)
    assert set(files) == {"storage.py", "static/vendor/lib.min.js"} and vendor == ["static/vendor/lib.min.js"]
    assert any(".env" in w for w in warnings) and any("бинарных" in w for w in warnings) and any("служебных" in w for w in warnings)


def test_said_vs_did_with_line(client, seeded, fake):
    """Ответ «Postgres» при SQLite в коде даёт расхождение со ссылкой на строку."""
    make_user("learner", Role.user)
    login_as(client, "learner")
    fake["answers"]["evaluate"] = evaluator_answer()

    incomplete = client.post("/api/assignments/hike-journal-storage/submissions", json={
        "answers": {"storage": ANSWERS["storage"]}, "source": "zip", "archive": make_zip({"storage.py": STORAGE}),
    })
    assert incomplete.status_code == 409 and "Ответьте на все развилки" in incomplete.json()["detail"]

    sent = client.post("/api/assignments/hike-journal-storage/submissions", json={
        "answers": ANSWERS, "summary": "Сделал модуль хранения", "source": "zip", "archive": make_zip({"storage.py": STORAGE}),
        "archive_name": "hikes.zip",
    })
    assert sent.status_code == 202, sent.text
    assert sent.json()["status"] == "testing" and sent.json()["forks"][0]["reference"] == ""  # эталон скрыт до оценки
    run_pipeline()

    out = client.get(f"/api/submissions/{sent.json()['id']}").json()
    assert out["status"] == "done", out["error"]
    assert out["tests"]["passed"] is True and len(out["tests"]["results"]) == 3  # настоящие автотесты в отдельном процессе
    ev = out["evaluation"]
    [real, fake_claim] = ev["mismatches"]  # строка 999 отброшена
    assert (real["file"], real["line"], real["claim_verified"]) == ("storage.py", 8, True)
    assert "sqlite3.connect" in real["code_line"]
    assert fake_claim["claim_verified"] is False  # Оценщик «процитировал» то, чего ученик не писал
    assert any("Отброшено расхождений" in n for n in ev["notes"])
    # Итог считает код: среднее блоков минус штраф за подтверждённое расхождение
    assert ev["reasoning"] == 2.75 and ev["implementation"] == 2.33 and ev["penalty"] == 0.75
    assert out["score"] == round((2.75 + 2.33) / 2 - 0.75, 2) and out["passed"] is False
    assert out["forks"][0]["reference"].startswith("Для одного сервера")  # после оценки эталон открыт

    # Оценщик и Ревьюер — без инструментов; Оценщик видит ответы, код с номерами строк и отчёт Ревьюера
    prompt = fake["evaluate"]["prompt"]
    assert "PostgreSQL с миграциями Alembic" in prompt and "   8 |     conn = sqlite3.connect(DB)" in prompt
    assert "Отчёт Ревьюера" in prompt and "✓ add_hike возвращает новый id" in prompt
    assert fake["evaluate"]["kwargs"]["library"] is False and fake["review"]["kwargs"]["library"] is False
    assert "Для одного сервера" not in prompt  # ответ эталона по развилке Оценщику не подсказываем

    journal = client.get("/api/forks").json()
    entry = next(e for e in journal if e["fork_id"] == "storage")
    assert entry["mismatches"][0]["line"] == 8
    md = client.get("/api/forks/export.md").text
    assert "## ADR-001. Где хранить журнал и почему? — `PostgreSQL с миграциями Alembic`" in md
    assert "**Расхождение с кодом.** «PostgreSQL с миграциями Alembic» — storage.py:8" in md

    make_user("other", Role.user)
    login_as(client, "other")
    assert client.get(f"/api/submissions/{out['id']}").status_code == 404


def test_second_attempt_sees_history_and_waits_for_previous(client, seeded, fake):
    make_user("learner", Role.user)
    login_as(client, "learner")
    fake["answers"]["evaluate"] = evaluator_answer(mismatches=[])
    body = {"answers": ANSWERS, "source": "zip", "archive": make_zip({"storage.py": STORAGE})}
    first = client.post("/api/assignments/hike-journal-storage/submissions", json=body).json()
    assert client.post("/api/assignments/hike-journal-storage/submissions", json=body).status_code == 409  # первая ещё идёт
    run_pipeline()
    assert client.get(f"/api/submissions/{first['id']}").json()["passed"] is False  # 2.79 < 3, но расхождений нет

    second = client.post("/api/assignments/hike-journal-storage/submissions", json={**body, "answers": {**ANSWERS, "storage": {**ANSWERS["storage"], "choice": "SQLite"}}}).json()
    run_pipeline()
    assert second["attempt"] == 2
    assert "попытка 1" in fake["evaluate"]["prompt"] and "storage: PostgreSQL с миграциями Alembic" in fake["evaluate"]["prompt"]


def test_unavailable_without_claude(client, seeded, monkeypatch):
    monkeypatch.setattr(claude, "configured", lambda: False)
    make_user("learner", Role.user)
    login_as(client, "learner")
    r = client.post("/api/assignments/hike-journal-storage/submissions", json={"answers": ANSWERS, "source": "zip", "archive": make_zip({"storage.py": STORAGE})})
    assert r.status_code == 409 and "Claude не подключён" in r.json()["detail"]
    with SessionLocal() as db:
        assert db.scalar(select(Submission.id)) is None


def test_admin_rubric_and_assignments(admin_client, seeded):
    rubric = admin_client.get("/api/workshop/rubric").json()
    rubric["criteria"][0]["title"] = "Названы реальные и уместные альтернативы"
    saved = admin_client.put("/api/workshop/rubric", json={**rubric, "note": "уточнил R1"}).json()
    assert saved["version"] == 2
    only_reasoning = [c for c in rubric["criteria"] if c["block"] == "reasoning"]
    assert admin_client.put("/api/workshop/rubric", json={**rubric, "criteria": only_reasoning}).status_code == 409
    items = admin_client.get("/api/workshop/assignments").json()
    assert {a["slug"] for a in items} == {"hike-journal-storage", "own-aggregator"}
    assert admin_client.get("/api/workshop/references").json()[0]["name"].startswith("Развилка")
