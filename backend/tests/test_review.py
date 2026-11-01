"""Независимый Ревьюер: правила версиями, строгая проверка ответа модели, шлюз публикации эталона, экспорт агента."""

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.modules.agent import claude
from app.modules.auth.models import Role
from app.modules.jobs.models import Job
from app.modules.practice.models import CheckStatus, TaskVersion
from app.modules.practice.runner import spec_hash
from app.modules.review import service
from app.modules.review.schemas import ModelReport
from tests.conftest import login_as, make_user

SOLUTION = "def make_slug(s):\n    return s.lower()  # ЭТАЛОН\n"
SPEC = {
    "title": "Функция slug", "kind": "python", "statement": "Напишите make_slug", "starter": {"main.py": "def make_slug(s):\n    pass\n"},
    "solution": {"main.py": SOLUTION}, "tests": "from main import make_slug\n", "hints": ["str.lower"],
}


def report(*findings) -> ModelReport:
    base = {"problem": "плохо", "scenario": "make_slug(None) → AttributeError", "fix_hint": "проверьте вход", "source": "PEP 8"}
    return ModelReport.model_validate({"findings": [{**base, **f} for f in findings]})


@pytest.fixture
def fake(monkeypatch):
    seen = {}

    def run_structured(purpose, prompt, system, schema, **kwargs):
        seen.update(purpose=purpose, prompt=prompt, system=system, kwargs=kwargs)
        return seen["answer"]

    monkeypatch.setattr(claude, "configured", lambda: True)
    monkeypatch.setattr(claude, "run_structured", run_structured)
    seen["answer"] = report()
    return seen


def make_task(client, publish: bool = True) -> dict:
    task = client.post("/api/workshop/tasks", json={"title": SPEC["title"], "kind": "python"}).json()
    client.put(f"/api/workshop/tasks/{task['id']}/draft", json={"number": 1, "spec": SPEC})
    with SessionLocal() as db:
        version = db.scalar(select(TaskVersion).where(TaskVersion.task_id == task["id"]))
        version.check_status, version.checked_hash = CheckStatus.passed, spec_hash(version.spec)
        db.commit()
    if publish:
        assert client.post(f"/api/workshop/tasks/{task['id']}/publish", json={}).status_code == 200
    return task


def run_queue():
    with SessionLocal() as db:
        for job in db.scalars(select(Job).where(Job.kind == "review", Job.status == "queued")):
            service.run(db, int(job.payload["review_id"]))
            job.status = "done"
            db.commit()


def test_default_rules_come_from_reviewer_md(admin_client):
    rules = admin_client.get("/api/workshop/review-rules").json()
    ids = [r["id"] for r in rules["rules"]]
    assert rules["version"] == 1 and len(ids) == 23 and ids[0] == "TASK-01" and "SEC-03" in ids
    assert {r["group"] for r in rules["rules"]} >= {"SEC — безопасность", "WEB — фронтенд (для HTML/CSS/JS)"}


def test_rules_are_versioned_and_admin_only(admin_client):
    rules = admin_client.get("/api/workshop/review-rules").json()["rules"]
    rules[0]["enabled"] = False
    rules.append({"id": "WEB-05", "group": "WEB — фронтенд (для HTML/CSS/JS)", "text": "Шрифты подключены с font-display: swap."})
    saved = admin_client.put("/api/workshop/review-rules", json={"rules": rules, "note": "добавил шрифты"}).json()
    assert saved["version"] == 2 and saved["author"] == "boss"
    assert admin_client.put("/api/workshop/review-rules", json={"rules": rules}).json()["version"] == 2  # без изменений — без версии
    dup = admin_client.put("/api/workshop/review-rules", json={"rules": rules + [rules[-1]]})
    assert dup.status_code == 409
    assert [v["version"] for v in admin_client.get("/api/workshop/review-rules/versions").json()] == [2, 1]
    md = service.rules_markdown(saved["rules"])
    assert "TASK-01" not in md and "WEB-05" in md  # выключенное правило Ревьюеру не показываем

    make_user("learner", Role.user)
    login_as(admin_client, "learner")
    assert admin_client.get("/api/workshop/review-rules").status_code == 403


def test_learner_review_is_blind_and_validated(admin_client, fake, client):
    task = make_task(admin_client)
    make_user("learner", Role.user)
    login_as(admin_client, "learner")
    fake["answer"] = report(
        {"rule": "COR-01", "severity": "major", "file": "main.py", "line": 2},
        {"rule": "READ-01", "severity": "minor", "file": "main.py", "line": 999},  # строки нет — адрес сбросится
        {"rule": "XYZ-01", "severity": "blocker", "file": "main.py", "line": 1},  # выдуманное правило
        {"rule": "SEC-01", "severity": "blocker", "file": "secret.py", "line": 1},  # файла не было
    )
    code = {"main.py": "def make_slug(s):\n    return s.strip()\n", "evil.py": "print(1)"}
    queued = admin_client.post("/api/reviews", json={"task_slug": task["slug"], "files": code})
    assert queued.status_code == 202 and queued.json()["status"] == "queued"
    assert admin_client.post("/api/reviews", json={"task_slug": task["slug"], "files": code}).status_code == 409  # одно за раз
    run_queue()

    out = admin_client.get(f"/api/reviews/{queued.json()['id']}").json()
    assert out["status"] == "done" and out["verdict"] == "changes_requested"
    assert [(f["rule"], f["line"]) for f in out["findings"]] == [("COR-01", 2), ("READ-01", None)]
    assert out["dropped"] == 2 and out["counts"] == {"blocker": 0, "major": 1, "minor": 1}
    assert set(out["files"]) == {"main.py"}  # лишний файл в ревью не попал
    # Ревьюер видит условие и код с номерами строк — но не эталон, не подсказки и не имя автора
    assert "   2 |     return s.strip()" in fake["prompt"] and "Напишите make_slug" in fake["prompt"]
    assert "ЭТАЛОН" not in fake["prompt"] and "str.lower" not in fake["prompt"] and "learner" not in fake["prompt"]
    assert fake["kwargs"]["library"] is False and fake["kwargs"].get("cwd") is None  # без инструментов
    assert [c["id"] for c in admin_client.get("/api/reviews").json()] == [out["id"]]

    make_user("other", Role.user)
    login_as(client, "other")
    assert client.get(f"/api/reviews/{out['id']}").status_code == 404


def test_reviewer_unavailable_without_claude(admin_client, monkeypatch):
    task = make_task(admin_client)
    monkeypatch.setattr(claude, "configured", lambda: False)
    response = admin_client.post("/api/reviews", json={"task_slug": task["slug"], "files": {"main.py": "x = 1"}})
    assert response.status_code == 409 and "Claude не подключён" in response.json()["detail"]


@pytest.mark.reviewer
def test_reference_review_gates_publishing(admin_client, fake):
    task = make_task(admin_client, publish=False)
    blocked = admin_client.post(f"/api/workshop/tasks/{task['id']}/publish", json={})
    assert blocked.status_code == 422 and any("Ревьюер не проверял эталон" in p for p in blocked.json()["problems"])

    fake["answer"] = report({"rule": "COR-01", "severity": "major", "file": "main.py", "line": 2})
    review = admin_client.post(f"/api/workshop/tasks/{task['id']}/review").json()
    run_queue()
    assert "ЭТАЛОН" in fake["prompt"] and "ЭТАЛОННОЕ решение" in fake["system"]  # проверяется именно эталон
    blocked = admin_client.post(f"/api/workshop/tasks/{task['id']}/publish", json={})
    assert any("замечания Ревьюера" in p for p in blocked.json()["problems"])

    accepted = admin_client.post(f"/api/workshop/reviews/{review['id']}/accept", json={"note": "None сюда не приходит"})
    assert accepted.json()["accepted"] is True
    assert admin_client.post(f"/api/workshop/tasks/{task['id']}/publish", json={}).status_code == 200

    # Новая редакция эталона — нужно новое ревью
    admin_client.post(f"/api/workshop/tasks/{task['id']}/draft")
    changed = {**SPEC, "solution": {"main.py": SOLUTION + "\n# v2\n"}}
    draft = admin_client.get(f"/api/workshop/tasks/{task['id']}").json()["editing"]["number"]
    admin_client.put(f"/api/workshop/tasks/{task['id']}/draft", json={"number": draft, "spec": changed})
    with SessionLocal() as db:
        assert any("не проверял" in p for p in service.reference_problems(db, db.get(__import__("app.modules.practice.models", fromlist=["Task"]).Task, task["id"])))


def test_agent_export(admin_client):
    md = admin_client.get("/api/workshop/review-rules/agent.md")
    assert md.status_code == 200 and "attachment" in md.headers["content-disposition"]
    text = md.text
    assert text.startswith("---\nname: reviewer\n") and "tools: Read, Grep, Glob" in text
    assert "**SEC-03**" in text and '"verdict": "pass | changes_requested"' in text
