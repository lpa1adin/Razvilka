"""Мастерская → Генерация. Claude подменён: проверяем конвейер платформы, а не ответы модели."""

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.db import SessionLocal
from app.modules.agent import claude
from app.modules.auth.models import Role
from app.modules.generation import pipeline
from app.modules.generation.models import GenRequest
from app.modules.generation.schemas import LessonDraft, Plan
from app.modules.jobs.models import Job
from app.modules.practice.models import CheckStatus, Task, TaskVersion
from app.modules.practice.runner import spec_hash
from app.modules.review.schemas import ModelReport
from tests.conftest import login_as, make_fragment, make_user

STARTER = {"index.html": "<p>пусто</p>", "style.css": "", "script.js": ""}
SOLUTION = {"index.html": "<header class='logo'>Фишт</header>", "style.css": "", "script.js": ""}


@pytest.fixture
def projects(tmp_path, monkeypatch):
    (tmp_path / "fisht-trails").mkdir()
    (tmp_path / "fisht-trails" / "index.html").write_text("<header>Фишт</header>")
    (tmp_path / "fisht-trails" / ".env").write_text("SECRET=1")
    monkeypatch.setattr(settings, "projects_root", str(tmp_path))
    return tmp_path


def fake_plan(fragment_id: int) -> Plan:
    return Plan.model_validate({
        "title": "Сайт про Фишт с нуля", "description": "Шапка и меню", "summary": "Лендинг клуба",
        "modules": [{"title": "Каркас", "lessons": [
            {"title": "Шапка", "goal": "Разметить шапку", "files": ["index.html"], "fragment_ids": [fragment_id, 999999],
             "practice": {"kind": "web", "idea": "Сверстать шапку"}, "quiz": 2},
        ]}],
    })


def fake_lesson(fragment_id: int) -> LessonDraft:
    return LessonDraft.model_validate({
        "theory": [{"fragment_id": fragment_id, "why": "Без семантики шапка — просто div"}, {"fragment_id": 424242, "why": "нет такой"}],
        "task": {
            "kind": "web", "title": "Шапка клуба", "statement": "Сделайте шапку с логотипом", "starter": STARTER, "solution": SOLUTION,
            "tests": "test('Есть логотип', () => { expect($('.logo'), 'Нет логотипа') })", "hints": ["Нужен header", "Класс logo"],
        },
        "questions": [
            {"type": "single", "prompt": "Какой тег размечает шапку страницы?", "options": {"items": [{"id": "a", "text": "`<header>`"}, {"id": "b", "text": "`<head>`"}]},
             "answer": {"correct": ["a"]}, "explanation": "head — служебная часть документа", "fragment_id": fragment_id},
            {"type": "single", "prompt": "Сломанный вопрос", "options": {"items": [{"id": "a", "text": "один"}]},
             "answer": {"correct": ["a"]}, "explanation": "", "fragment_id": fragment_id},
        ],
    })


class Calls(list):
    """Вызовы подменённого Claude; answers — что он «ответит» на каждую цель (plan, draft, fix)."""

    answers: dict


@pytest.fixture
def fake_claude(monkeypatch):
    calls = Calls()
    calls.answers = {}

    def run_structured(purpose, prompt, system, schema, **kwargs):
        calls.append({"purpose": purpose, "prompt": prompt, "cwd": kwargs.get("cwd")})
        return calls.answers[purpose]

    monkeypatch.setattr(claude, "run_structured", run_structured)
    # Ревьюер эталонов (этап 5): по умолчанию замечаний нет
    monkeypatch.setattr(claude, "configured", lambda: True)
    calls.answers["review"] = ModelReport(findings=[])
    return calls


def pass_checks(*_args, **_kwargs):
    """Вместо runner: отмечаем проверку пройденной, как это сделал бы verify_task."""
    with SessionLocal() as db:
        for version in db.scalars(select(TaskVersion).where(TaskVersion.check_status == CheckStatus.queued)):
            version.check_status = CheckStatus.passed
            version.checked_hash = spec_hash(version.spec)
        db.commit()


def run_jobs():
    with SessionLocal() as db:
        for job in db.scalars(select(Job).where(Job.kind == "agent", Job.status == "queued").order_by(Job.id)):
            pipeline.handle(db, job.payload)
            job.status = "done"
            db.commit()


def test_full_pipeline_course_is_hidden_until_published(admin_client, projects, fake_claude, monkeypatch):
    monkeypatch.setattr(pipeline, "_wait_checks", pass_checks)
    fragment = make_fragment("Семантика HTML", "header nav main")
    fake_claude.answers.update(plan=fake_plan(fragment), draft=fake_lesson(fragment))

    assert [p["name"] for p in admin_client.get("/api/workshop/generate/projects").json()] == ["fisht-trails"]
    req = admin_client.post("/api/workshop/generate/requests", json={"what": "course", "project": "fisht-trails", "level": 1}).json()
    assert req["status"] == "new"

    # Без утверждённого плана черновик не создаётся
    assert admin_client.post(f"/api/workshop/generate/requests/{req['id']}/draft").status_code == 409

    assert admin_client.post(f"/api/workshop/generate/requests/{req['id']}/plan").json()["status"] == "planning"
    run_jobs()
    assert fake_claude[0]["cwd"] == str(projects / "fisht-trails")
    req = admin_client.get(f"/api/workshop/generate/requests/{req['id']}").json()
    assert req["status"] == "plan_ready"
    lesson = req["plan"]["modules"][0]["lessons"][0]
    assert lesson["fragment_ids"] == [fragment]  # несуществующая статья убрана из плана
    assert lesson["id"].startswith("l")

    # Админ правит план руками
    req["plan"]["modules"][0]["lessons"][0]["title"] = "Шапка сайта"
    saved = admin_client.put(f"/api/workshop/generate/requests/{req['id']}/plan", json=req["plan"])
    assert saved.json()["plan"]["modules"][0]["lessons"][0]["title"] == "Шапка сайта"

    assert admin_client.post(f"/api/workshop/generate/requests/{req['id']}/draft").json()["status"] == "drafting"
    run_jobs()
    req = admin_client.get(f"/api/workshop/generate/requests/{req['id']}").json()
    assert req["status"] == "draft_ready", req["error"]
    created = req["lessons"][0]
    assert created["task"]["check_status"] == "passed"
    assert created["questions"] == 1  # сломанный вопрос не прошёл проверку формата
    assert any("Вопрос 2 пропущен" in n for n in created["notes"])
    assert any("не нашлась" in n for n in created["notes"])
    review_step = next(s for s in req["steps"] if s["key"] == "review")
    assert review_step["state"] == "done" and "без серьёзных замечаний: 1 из 1" in review_step["detail"]
    assert created["task"]["review_verdict"] == "pass"
    review_call = next(c for c in fake_claude if c["purpose"] == "review")
    assert review_call["cwd"] is None  # Ревьюер без доступа к проекту и без контекста генерации
    assert req["course"]["draft_version"] == 1 and req["published"] is False

    # Пользователь черновик не видит
    make_user("learner", Role.user)
    login_as(admin_client, "learner")
    assert admin_client.get("/api/courses").json() == []
    assert admin_client.get("/api/workshop/generate/requests").status_code == 403

    login_as(admin_client, "boss")
    published = admin_client.post(f"/api/workshop/generate/requests/{req['id']}/publish").json()
    assert published["problems"] == []
    assert any("курс" in p for p in published["published"])

    login_as(admin_client, "learner")
    courses = admin_client.get("/api/courses").json()
    assert [c["title"] for c in courses] == ["Сайт про Фишт с нуля"]
    lesson = admin_client.get(f"/api/courses/{courses[0]['slug']}/lessons/{created['id']}").json()
    assert [b["type"] for b in lesson["blocks"]] == ["theory"]
    assert lesson["practice"][0]["task"]["title"] == "Шапка клуба"
    assert lesson["quizzes"][0]["topic"]["questions"] == 1


def test_publish_is_all_or_nothing(admin_client, projects, fake_claude, monkeypatch):
    monkeypatch.setattr(pipeline, "_wait_checks", lambda *a, **k: None)  # runner не ответил
    fragment = make_fragment("Семантика HTML", "header nav main")
    fake_claude.answers.update(plan=fake_plan(fragment), draft=fake_lesson(fragment))
    req = admin_client.post("/api/workshop/generate/requests", json={"project": "fisht-trails"}).json()
    admin_client.post(f"/api/workshop/generate/requests/{req['id']}/plan")
    run_jobs()
    admin_client.post(f"/api/workshop/generate/requests/{req['id']}/draft")
    run_jobs()

    result = admin_client.post(f"/api/workshop/generate/requests/{req['id']}/publish").json()
    assert any("Автопроверка не пройдена" in p for p in result["problems"])
    assert result["published"] == []
    with SessionLocal() as db:
        assert all(t.published_version is None for t in db.scalars(select(Task)))


def test_redo_lesson_replaces_its_drafts(admin_client, projects, fake_claude, monkeypatch):
    monkeypatch.setattr(pipeline, "_wait_checks", pass_checks)
    fragment = make_fragment("Семантика HTML", "header nav main")
    fake_claude.answers.update(plan=fake_plan(fragment), draft=fake_lesson(fragment))
    req = admin_client.post("/api/workshop/generate/requests", json={"project": "fisht-trails"}).json()
    admin_client.post(f"/api/workshop/generate/requests/{req['id']}/plan")
    run_jobs()
    admin_client.post(f"/api/workshop/generate/requests/{req['id']}/draft")
    run_jobs()
    lesson_id = admin_client.get(f"/api/workshop/generate/requests/{req['id']}").json()["lessons"][0]["id"]

    redo = fake_lesson(fragment)
    redo.task.title = "Шапка посложнее"
    redo.questions[0].prompt = "Чем header отличается от head?"
    fake_claude.answers["draft"] = redo
    response = admin_client.post(f"/api/workshop/generate/requests/{req['id']}/lessons/{lesson_id}/redo", json={"instruction": "усложни задание"})
    assert response.status_code == 200, response.text
    run_jobs()
    assert "усложни задание" in [c for c in fake_claude if c["purpose"] == "draft"][-1]["prompt"]
    out = admin_client.get(f"/api/workshop/generate/requests/{req['id']}").json()
    assert out["lessons"][0]["task"]["title"] == "Шапка посложнее"
    with SessionLocal() as db:
        assert db.scalar(select(Task).where(Task.slug.like("shapka-kluba%"))) is None  # старый черновик удалён


def test_failed_step_is_reported(admin_client, projects, monkeypatch):
    def unavailable(*_a, **_k):
        raise claude.AgentUnavailable("Исчерпан лимит подписки Claude. Попробуйте позже.")

    monkeypatch.setattr(claude, "run_structured", unavailable)
    req = admin_client.post("/api/workshop/generate/requests", json={"topic": "Flexbox"}).json()
    admin_client.post(f"/api/workshop/generate/requests/{req['id']}/plan")
    with pytest.raises(claude.AgentUnavailable):
        run_jobs()
    out = admin_client.get(f"/api/workshop/generate/requests/{req['id']}").json()
    assert out["status"] == "failed"
    assert out["error"].startswith("Исчерпан лимит")
    assert out["steps"][0]["state"] == "failed"


def test_bad_project_paths_are_rejected(admin_client, projects):
    for payload in ({"project": "../etc"}, {"project": "fisht-trails", "focus": "../../"}, {"project": "nope"}, {}):
        assert admin_client.post("/api/workshop/generate/requests", json=payload).status_code == 409, payload


def test_user_proposal_goes_to_admin(client):
    make_user("learner", Role.user)
    login_as(client, "learner")
    assert client.post("/api/proposals", json={"topic": "Grid-раскладка"}).status_code == 201
    assert client.post("/api/workshop/generate/requests", json={"topic": "x"}).status_code == 403

    make_user("boss", Role.admin)
    login_as(client, "boss")
    cards = client.get("/api/workshop/generate/requests").json()
    assert [(c["origin"], c["status"], c["title"], c["author"]) for c in cards] == [("user", "proposed", "Grid-раскладка", "learner")]
    # Пока заявку не приняли, план не строится
    assert client.post(f"/api/workshop/generate/requests/{cards[0]['id']}/plan").status_code == 409
    assert client.post(f"/api/workshop/generate/requests/{cards[0]['id']}/reject").json()["status"] == "rejected"


def test_path_guard_blocks_secrets_and_escape(projects):
    import asyncio

    guard = claude._path_guard(str(projects / "fisht-trails"))

    def decision(tool_input):
        out = asyncio.run(guard({"tool_input": tool_input}, None, None))
        return out.get("hookSpecificOutput", {}).get("permissionDecision", "allow")

    assert decision({"file_path": "index.html"}) == "allow"
    assert decision({"file_path": ".env"}) == "deny"
    assert decision({"file_path": "/etc/passwd"}) == "deny"
    assert decision({"file_path": "../other/index.html"}) == "deny"
    assert decision({"pattern": "../**/*"}) == "deny"
    with SessionLocal() as db:
        assert db.scalar(select(GenRequest.id)) is None


def two_lessons(fragment_id: int) -> Plan:
    plan = fake_plan(fragment_id).model_dump()
    second = {**plan["modules"][0]["lessons"][0], "id": "", "title": "Меню"}
    plan["modules"][0]["lessons"].append(second)
    return Plan.model_validate(plan)


def drafted_plan(client, fake_claude, fragment) -> int:
    fake_claude.answers.update(plan=two_lessons(fragment))
    req = client.post("/api/workshop/generate/requests", json={"what": "course", "project": "fisht-trails"}).json()
    client.post(f"/api/workshop/generate/requests/{req['id']}/plan")
    run_jobs()
    assert client.post(f"/api/workshop/generate/requests/{req['id']}/draft").json()["status"] == "drafting"
    return req["id"]


def test_pause_after_lesson_and_resume(admin_client, projects, fake_claude, monkeypatch):
    """Пауза «после урока»: урок дописан и сохранён, следующий не начат; продолжение не повторяет готовое."""
    monkeypatch.setattr(pipeline, "_wait_checks", pass_checks)
    fragment = make_fragment("Семантика HTML", "header nav main")
    rid = drafted_plan(admin_client, fake_claude, fragment)
    lesson = fake_lesson(fragment)
    drafts = []

    def draft_then_pause(purpose, prompt, system, schema, **kwargs):
        if purpose == "draft":
            drafts.append(1)
            if len(drafts) == 1:  # админ жмёт «Пауза» посреди первого урока
                assert admin_client.post(f"/api/workshop/generate/requests/{rid}/pause", json={"mode": "after"}).json()["pause"] == "after"
            return lesson
        return fake_claude.answers[purpose]

    monkeypatch.setattr(claude, "run_structured", draft_then_pause)
    run_jobs()
    req = admin_client.get(f"/api/workshop/generate/requests/{rid}").json()
    assert (req["status"], req["busy"], req["pause"]) == ("paused", False, "")
    states = [s["state"] for s in req["steps"] if s["key"].startswith("lesson:")]
    assert states == ["done", "pending"] and len(req["lessons"]) == 1
    # На паузе черновик не перезапускается обычной кнопкой и не ставится на паузу повторно
    assert admin_client.post(f"/api/workshop/generate/requests/{rid}/pause", json={"mode": "now"}).status_code == 409

    assert admin_client.post(f"/api/workshop/generate/requests/{rid}/resume").json()["status"] == "drafting"
    run_jobs()
    req = admin_client.get(f"/api/workshop/generate/requests/{rid}").json()
    assert req["status"] == "draft_ready", req["error"]
    assert len(drafts) == 2 and len(req["lessons"]) == 2  # первый урок второй раз не писали


def test_stop_now_interrupts_claude(admin_client, projects, fake_claude, monkeypatch):
    """«Остановить сейчас»: вызов Claude прерывается, недописанный урок начнётся заново."""
    monkeypatch.setattr(pipeline, "_wait_checks", pass_checks)
    fragment = make_fragment("Семантика HTML", "header nav main")
    rid = drafted_plan(admin_client, fake_claude, fragment)
    stopped = []

    def interrupted(purpose, prompt, system, schema, **kwargs):
        if purpose == "draft" and not stopped:
            admin_client.post(f"/api/workshop/generate/requests/{rid}/pause", json={"mode": "now"})
            assert kwargs["should_stop"]()  # так run_structured проверяет флаг на каждом сообщении агента
            stopped.append(1)
            raise claude.Stopped()
        return fake_lesson(fragment) if purpose == "draft" else fake_claude.answers[purpose]

    monkeypatch.setattr(claude, "run_structured", interrupted)
    run_jobs()
    req = admin_client.get(f"/api/workshop/generate/requests/{rid}").json()
    assert req["status"] == "paused" and req["lessons"] == []
    first = next(s for s in req["steps"] if s["key"].startswith("lesson:"))
    assert first["state"] == "pending" and "на паузе" in first["detail"]

    admin_client.post(f"/api/workshop/generate/requests/{rid}/resume")
    run_jobs()
    req = admin_client.get(f"/api/workshop/generate/requests/{rid}").json()
    assert req["status"] == "draft_ready" and len(req["lessons"]) == 2


def test_redo_keeps_lesson_number(admin_client, projects, fake_claude, monkeypatch):
    """«Переделать урок» второго урока — в ходе работы он по-прежнему «Урок 2», а не «Урок 1»."""
    monkeypatch.setattr(pipeline, "_wait_checks", pass_checks)
    fragment = make_fragment("Семантика HTML", "header nav main")
    fake_claude.answers["draft"] = fake_lesson(fragment)
    rid = drafted_plan(admin_client, fake_claude, fragment)
    run_jobs()
    req = admin_client.get(f"/api/workshop/generate/requests/{rid}").json()
    second = req["plan"]["modules"][0]["lessons"][1]["id"]
    admin_client.post(f"/api/workshop/generate/requests/{rid}/lessons/{second}/redo", json={"instruction": "попроще"})
    run_jobs()
    step = next(s for s in admin_client.get(f"/api/workshop/generate/requests/{rid}").json()["steps"] if s["key"] == f"lesson:{second}")
    assert step["label"] == "Урок 2. Меню"
