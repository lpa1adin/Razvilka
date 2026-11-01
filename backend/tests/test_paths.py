"""Пути «напиши заново сам»: генерация этапов с автопроверкой на оригинале, рабочая папка, порядок этапов,
сдача этапа конвейером этапа 6 и превью рабочей папки."""

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.db import SessionLocal
from app.modules.agent import claude
from app.modules.assess import service as assess
from app.modules.assess.schemas import EvaluatorReport
from app.modules.auth.models import Role
from app.modules.generation import path_pipeline, pipeline
from app.modules.generation.schemas import Plan, StageDraft
from app.modules.jobs.models import Job
from app.modules.review.schemas import ModelReport
from tests.conftest import login_as, make_user

ORIGINAL = {
    "storage.py": "import json\n\nDATA = []\n\n\ndef add_hike(name, km):\n    DATA.append({'name': name, 'km': km})\n    return len(DATA)\n",
    "report.py": "from storage import DATA\n\n\ndef total():\n    return sum(h['km'] for h in DATA)\n",
}
STAGE1_TESTS = 'def test_add():\n    """Есть add_hike, она возвращает номер записи"""\n    import storage\n    assert storage.add_hike("Фишт", 10) == 1\n'
STAGE2_TESTS = 'def test_total():\n    """report.total складывает километры"""\n    import storage, report\n    storage.add_hike("a", 2)\n    assert report.total() >= 2\n'


@pytest.fixture
def env(tmp_path, monkeypatch):
    project = tmp_path / "projects" / "hikes"
    project.mkdir(parents=True)
    for name, text in ORIGINAL.items():
        (project / name).write_text(text)
    (project / ".env").write_text("SECRET=1")
    monkeypatch.setattr(settings, "projects_root", str(tmp_path / "projects"))
    monkeypatch.setattr(settings, "workspace_root", str(tmp_path / "workspace"))
    return tmp_path


@pytest.fixture
def fake(monkeypatch):
    plan = Plan.model_validate({
        "title": "Журнал походов с нуля", "description": "Пишем модуль хранения и отчёт", "summary": "…",
        "roles": [{"path": "storage.py", "role": "Хранит походы в памяти"}, {"path": "report.py", "role": "Считает итоги"}],
        "modules": [{"title": "Путь", "lessons": [
            {"title": "Хранилище", "goal": "Добавлять походы", "files": ["storage.py"], "practice": {"kind": "python", "idea": "x"}, "quiz": 3,
             "forks": [{"question": "Где хранить записи?", "context": "Пока без диска"}]},
            {"title": "Отчёт", "goal": "Считать километры", "files": ["report.py"], "forks": [{"question": "Как связать модули?"}]},
        ]}],
    })
    stages = iter([
        StageDraft(statement="Сделайте storage.add_hike", tests=STAGE1_TESTS,
                   forks=[{"question": "Где хранить записи?", "reference": "Автор хранит список в памяти: storage.py:3"}]),
        StageDraft(statement="Сделайте report.total", tests=STAGE2_TESTS, forks=[{"question": "Как связать модули?", "reference": "Импорт DATA"}]),
    ])
    answers = {"plan": plan, "review": ModelReport(findings=[]),
               "evaluate": EvaluatorReport.model_validate({"criteria": [{"id": f"R{i}", "score": 4, "explanation": "…"} for i in range(1, 8)], "summary": "Хорошо"})}

    def run_structured(purpose, prompt, system, schema, **kwargs):
        return next(stages) if purpose == "draft" else answers[purpose]

    monkeypatch.setattr(claude, "configured", lambda: True)
    monkeypatch.setattr(claude, "run_structured", run_structured)

    def wait_inline(db, ids):
        """Вместо воркера runner: проверяем этапы прямо здесь — тем же verify_stage."""
        for job in db.scalars(select(Job).where(Job.kind == "runner", Job.status == "queued")).all():
            path_pipeline.verify_stage(db, int(job.payload["assignment_id"]), job.payload["files"])
            job.status = "done"
        db.commit()

    monkeypatch.setattr(path_pipeline, "_wait", wait_inline)


def run_agent_jobs():
    with SessionLocal() as db:
        for job in db.scalars(select(Job).where(Job.kind == "agent", Job.status == "queued").order_by(Job.id)).all():
            job.status = "done"
            db.commit()
            pipeline.handle(db, job.payload)


def run_submission_jobs():
    with SessionLocal() as db:
        for _ in range(4):
            job = db.scalar(select(Job).where(Job.status == "queued", Job.kind.in_(["runner", "review"])).order_by(Job.id))
            if job is None:
                return
            job.status = "done"
            db.commit()
            if job.payload["type"] == "test_submission":
                assess.run_tests(db, int(job.payload["submission_id"]))
            else:
                assess.run_assessment(db, int(job.payload["submission_id"]))


def test_path_generation_publish_and_first_stage(client, env, fake):
    make_user("boss", Role.admin)
    login_as(client, "boss")
    req = client.post("/api/workshop/generate/requests", json={"what": "path", "project": "hikes"}).json()
    client.post(f"/api/workshop/generate/requests/{req['id']}/plan")
    run_agent_jobs()
    plan = client.get(f"/api/workshop/generate/requests/{req['id']}").json()["plan"]
    lesson = plan["modules"][0]["lessons"][0]
    assert (lesson["practice"], lesson["quiz"], len(lesson["forks"])) == (None, 0, 1) and len(plan["roles"]) == 2

    client.post(f"/api/workshop/generate/requests/{req['id']}/draft")
    run_agent_jobs()
    out = client.get(f"/api/workshop/generate/requests/{req['id']}").json()
    assert out["status"] == "draft_ready", out["error"]
    assert [l["stage"]["check_status"] for l in out["lessons"]] == ["passed", "passed"]  # проходят на оригинале, падают на пустой
    assert "на пустой папке — нет" in out["lessons"][0]["stage"]["check_summary"]

    # До публикации пользователь пути не видит
    make_user("learner", Role.user)
    login_as(client, "learner")
    assert client.get("/api/paths").json() == []
    login_as(client, "boss")
    assert client.post(f"/api/workshop/generate/requests/{req['id']}/publish").json()["problems"] == []

    login_as(client, "learner")
    [card] = client.get("/api/paths").json()
    assert (card["stages"], card["passed"], card["workspace"]) == (2, 0, False)
    detail = client.get(f"/api/paths/{card['slug']}").json()
    assert [s["state"] for s in detail["stages"]] == ["open", "locked"]
    assert {n["id"] for n in detail["map"]["nodes"]} == {"storage.py", "report.py"}  # .env в карту не попал
    assert ("report.py", "storage.py") in {(e["from"], e["to"]) for e in detail["map"]["edges"]}
    assert detail["map"]["roles"][0]["role"] == "Хранит походы в памяти"
    assert all(a["slug"] != detail["stages"][0]["slug"] for a in client.get("/api/assignments").json())  # этапы — не в общем списке

    ws = client.post(f"/api/paths/{card['slug']}/workspace").json()
    assert ws["exists"] and ws["list"] == ["README.md"]  # оригинал не копируется — пишем с нуля
    folder = env / "workspace" / "learner" / card["slug"]
    stage1, stage2 = detail["stages"][0]["slug"], detail["stages"][1]["slug"]
    early = client.post(f"/api/assignments/{stage2}/submissions", json={"answers": {"f1": {"choice": "импорт", "reasons": "так проще всего связать"}}, "source": "workspace"})
    assert early.status_code == 409 and "предыдущий этап" in early.json()["detail"]

    (folder / "storage.py").write_text("DATA = []\n\n\ndef add_hike(name, km):\n    DATA.append((name, km))\n    return len(DATA)\n")
    sent = client.post(f"/api/assignments/{stage1}/submissions", json={
        "answers": {"f1": {"choice": "Список в памяти", "reasons": "Записей мало, диск пока не нужен по условию этапа"}}, "source": "workspace",
    })
    assert sent.status_code == 202, sent.text
    assert sent.json()["source_name"].endswith(f"workspace/learner/{card['slug']}")
    run_submission_jobs()
    result = client.get(f"/api/submissions/{sent.json()['id']}").json()
    assert result["tests"]["passed"] and result["passed"] is True and result["score"] == 4.0
    assert result["forks"][0]["reference"].startswith("Автор хранит")  # ответ автора — после оценки
    assert [s["state"] for s in client.get(f"/api/paths/{card['slug']}").json()["stages"]] == ["passed", "open"]


def test_preview_is_signed_and_sandboxed(client, env, fake):
    from app.modules.paths.models import ProjectPath

    with SessionLocal() as db:
        path = ProjectPath(slug="demo", title="Демо", project="hikes", kind="web", published=True, roles=[])
        db.add(path)
        db.commit()
    make_user("learner", Role.user)
    login_as(client, "learner")
    client.post("/api/paths/demo/workspace")
    (env / "workspace" / "learner" / "demo" / "index.html").write_text("<h1>Привет</h1>")
    (env / "workspace" / "learner" / "demo" / ".env").write_text("SECRET=1")
    url = client.get("/api/paths/demo/preview").json()["url"]
    page = client.get(url)
    assert page.status_code == 200 and "Привет" in page.text
    assert page.headers["content-security-policy"].startswith("sandbox allow-scripts")
    base = url.rsplit("/", 1)[0]
    assert client.get(f"{base}/.env").status_code == 404
    assert client.get(f"{base}/../../../etc/passwd").status_code in (404, 403)
    forged = url.replace(url.split("/")[3], url.split("/")[3][:-4] + "beef")
    assert client.get(forged).status_code == 403
