"""Чат-помощник: очередь, поток ответа, подсказки и границы того, что видит наставник."""

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.modules.agent import claude
from app.modules.auth.models import Role
from app.modules.jobs.models import Job
from app.modules.mentor import service as mentor
from app.modules.mentor.models import MentorMessage
from app.modules.practice.models import TaskWork
from tests.conftest import login_as, make_user

SOLUTION_MARK = "SECRET_SOLUTION_LINE"


@pytest.fixture
def task_slug(admin_client):
    """Опубликованное задание (проверка отмечена пройденной вручную, без runner)."""
    from app.modules.practice.models import CheckStatus, TaskVersion
    from app.modules.practice.runner import spec_hash

    created = admin_client.post("/api/workshop/tasks", json={"title": "Функция slug", "kind": "python"}).json()
    spec = {
        "title": "Функция slug", "kind": "python", "statement": "Напишите make_slug", "starter": {"main.py": "def make_slug(s):\n    pass\n"},
        "solution": {"main.py": f"def make_slug(s):\n    return s  # {SOLUTION_MARK}\n"}, "tests": "from main import make_slug\n",
        "hints": ["Посмотрите на str.lower"],
    }
    admin_client.put(f"/api/workshop/tasks/{created['id']}/draft", json={"number": 1, "spec": spec})
    with SessionLocal() as db:
        version = db.scalar(select(TaskVersion).where(TaskVersion.task_id == created["id"]))
        version.check_status, version.checked_hash = CheckStatus.passed, spec_hash(version.spec)
        db.commit()
    assert admin_client.post(f"/api/workshop/tasks/{created['id']}/publish", json={}).status_code == 200
    return created["slug"]


@pytest.fixture
def learner(client, task_slug):
    make_user("learner", Role.user)
    login_as(client, "learner")
    return client


def test_unavailable_without_token(learner, task_slug, monkeypatch):
    monkeypatch.setattr(claude, "configured", lambda: False)
    response = learner.post("/api/mentor/messages", json={"context_kind": "task", "context_ref": task_slug, "text": "Как начать?"})
    assert response.status_code == 503
    assert "песочница работают без него" in response.json()["detail"]
    assert learner.get("/api/mentor/status").json()["available"] is False


def test_reply_streams_into_message_and_hides_solution(learner, task_slug, monkeypatch):
    monkeypatch.setattr(claude, "configured", lambda: True)
    seen = {}

    def stream_reply(prompt, system, on_delta):
        seen["prompt"], seen["system"] = prompt, system
        for part in ("Посмотрите ", "на ", "[статью](/library/1)."):
            on_delta(part)
        return "Посмотрите на [статью](/library/1)."

    monkeypatch.setattr(claude, "stream_reply", stream_reply)
    response = learner.post("/api/mentor/messages", json={
        "context_kind": "task", "context_ref": task_slug, "text": "Почему не работает?", "files": {"main.py": "def make_slug(s):\n    return 1\n"},
    })
    assert response.status_code == 202, response.text
    # Второй вопрос, пока наставник отвечает, — отклоняется
    busy = learner.post("/api/mentor/messages", json={"context_kind": "task", "context_ref": task_slug, "text": "Ещё?"})
    assert busy.status_code == 409

    with SessionLocal() as db:
        job = db.scalar(select(Job).where(Job.kind == "chat"))
        mentor.reply(db, int(job.payload["message_id"]), job.payload["files"])

    assert "return 1" in seen["prompt"]  # код из редактора, ещё не сохранённый
    assert SOLUTION_MARK not in seen["prompt"]  # эталон наставнику не показываем
    assert "НЕ ВЫДАВАЙ" in seen["system"]
    thread = learner.get("/api/mentor/thread", params={"kind": "task", "ref": task_slug}).json()["messages"]
    assert [(m["role"], m["status"]) for m in thread] == [("user", "done"), ("assistant", "done")]
    assert thread[1]["content"] == "Посмотрите на [статью](/library/1)."

    events = learner.get(f"/api/mentor/messages/{thread[1]['id']}/stream").text
    assert '"status": "done"' in events


def test_hints_are_counted_and_escalate(learner, task_slug, monkeypatch):
    monkeypatch.setattr(claude, "configured", lambda: True)
    prompts = []
    monkeypatch.setattr(claude, "stream_reply", lambda p, s, d: prompts.append(p) or "ок")
    for _ in range(2):
        assert learner.post("/api/mentor/messages", json={"context_kind": "task", "context_ref": task_slug, "hint": True}).status_code == 202
        with SessionLocal() as db:
            job = db.scalar(select(Job).where(Job.kind == "chat", Job.status == "queued"))
            mentor.reply(db, int(job.payload["message_id"]), None)
            job.status = "done"
            db.commit()
    assert "[Подсказка №1]" in prompts[0] and "[Подсказка №2]" in prompts[1]
    with SessionLocal() as db:
        assert db.scalar(select(TaskWork.mentor_hints)) == 2

    # Попытка помнит, сколько подсказок наставника было до неё
    learner.post(f"/api/practice/tasks/{task_slug}/attempts", json={"passed": False, "results": []})
    from app.modules.practice.models import TaskAttempt

    with SessionLocal() as db:
        assert db.scalar(select(TaskAttempt.mentor_hints)) == 2


def test_failure_is_shown_in_chat(learner, task_slug, monkeypatch):
    monkeypatch.setattr(claude, "configured", lambda: True)

    def broken(prompt, system, on_delta):
        on_delta("Начинаю…")
        raise claude.AgentUnavailable("Исчерпан лимит подписки Claude. Попробуйте позже.")

    monkeypatch.setattr(claude, "stream_reply", broken)
    learner.post("/api/mentor/messages", json={"context_kind": "general", "text": "Привет"})
    with SessionLocal() as db:
        job = db.scalar(select(Job).where(Job.kind == "chat"))
        mentor.reply(db, int(job.payload["message_id"]), None)
        answer = db.scalar(select(MentorMessage).where(MentorMessage.role == "assistant"))
        assert (answer.status.value, answer.error.startswith("Исчерпан")) == ("failed", True)


def test_hint_only_in_tasks_and_threads_are_private(learner, task_slug, monkeypatch, client):
    monkeypatch.setattr(claude, "configured", lambda: True)
    assert learner.post("/api/mentor/messages", json={"context_kind": "general", "hint": True}).status_code == 409
    learner.post("/api/mentor/messages", json={"context_kind": "general", "text": "Привет"})
    with SessionLocal() as db:
        answer_id = db.scalar(select(MentorMessage.id).where(MentorMessage.role == "assistant"))
    make_user("other", Role.user)
    login_as(client, "other")
    assert client.get(f"/api/mentor/messages/{answer_id}").status_code == 404
    assert client.get("/api/mentor/thread", params={"kind": "general"}).json()["messages"] == []
