import json
from pathlib import Path

import pytest

from app.core.db import SessionLocal
from app.modules.auth.models import Role
from app.modules.jobs.models import Job
from app.modules.practice import runner
from app.modules.practice.models import TaskVersion
from app.modules.practice.webpage import build_page
from tests.conftest import login_as, make_fragment, make_user

SEED = Path(__file__).parents[1] / "app" / "modules" / "practice" / "seed"


def seed(name: str) -> dict:
    data = json.loads((SEED / name).read_text(encoding="utf-8"))
    data.pop("fragment_titles")
    return data


def test_build_page_inlines_files_in_the_right_order():
    files = {
        "index.html": '<html><head><link rel="stylesheet" href="style.css"></head><body><p>x</p><script src="script.js"></script></body></html>',
        "style.css": "p { color: red }",
        "script.js": "console.log('</script>')",
    }
    page = build_page(files, "test('a', () => {})", 375, "check", harness="/*H*/")
    assert 'href="style.css"' not in page and 'src="script.js"' not in page
    assert page.index("<style>p { color: red }</style>") < page.index("/*H*/") < page.index("test('a'") < page.index("console.log")
    assert "window.__rzWidth=375" in page and '__rzMode="check"' in page
    assert "<\\/script>" in page  # строка в коде ученика не закрывает тег раньше времени
    assert "test('a'" not in build_page(files, "test('a', () => {})", 1280, "preview", harness="")


def create_task(client, name: str) -> dict:
    data = seed(name)
    task = client.post("/api/workshop/tasks", json={"title": data["title"], "kind": data["kind"]}).json()
    saved = client.put(f"/api/workshop/tasks/{task['id']}/draft", json={"number": 1, "spec": data})
    assert saved.status_code == 200, saved.text
    return saved.json()


def run_queued_check(task_id: int) -> None:
    """Вместо воркера runner: выполняем поставленную в очередь проверку прямо в тесте."""
    with SessionLocal() as db:
        version = db.query(TaskVersion).filter_by(task_id=task_id).order_by(TaskVersion.number.desc()).first()
        runner.verify_task(db, version.id)


@pytest.mark.parametrize("name", ["slug.json", "routes_sql.json"])
def test_verify_publish_and_solve(client, name):
    make_user("boss", Role.admin)
    login_as(client, "boss")
    task = create_task(client, name)
    tid = task["id"]

    blocked = client.post(f"/api/workshop/tasks/{tid}/publish", json={})
    assert blocked.status_code == 422 and any("Автопроверка" in p for p in blocked.json()["problems"])

    assert client.post(f"/api/workshop/tasks/{tid}/check").json()["editing"]["check_status"] == "queued"
    with SessionLocal() as db:
        assert db.query(Job).one().payload["type"] == "verify_task"
    run_queued_check(tid)
    checked = client.get(f"/api/workshop/tasks/{tid}").json()["editing"]
    assert checked["check_status"] == "passed", checked["check_report"]
    assert checked["check_is_current"] is True
    assert client.post(f"/api/workshop/tasks/{tid}/publish", json={}).status_code == 200

    make_user("anna", Role.user)
    login_as(client, "anna")
    slug = task["slug"]
    learner = client.get(f"/api/practice/tasks/{slug}").json()
    raw = json.dumps(learner, ensure_ascii=False)
    solution_text = next(iter(seed(name)["solution"].values()))
    assert solution_text not in raw  # эталон ученику не уходит
    assert learner["hints"] == [] and learner["hints_total"] == 3
    if name == "routes_sql.json":
        assert learner["sql_expected"][0]["columns"] == ["name", "length_km"]

    client.put(f"/api/practice/tasks/{slug}/work", json={"files": {**learner["files"], "evil.py": "x"}})
    assert client.post(f"/api/practice/tasks/{slug}/hint").json()["hint"].startswith(seed(name)["hints"][0][:10])
    client.post(f"/api/practice/tasks/{slug}/attempts", json={"passed": True, "results": [{"name": "x", "passed": True}]})
    again = client.get(f"/api/practice/tasks/{slug}").json()
    assert again["solved"] is True and len(again["hints"]) == 1 and "evil.py" not in again["files"]
    assert client.get("/api/practice/tasks").json()[0]["solved"] is True


def test_editing_after_check_requires_new_check(admin_client):
    task = create_task(admin_client, "slug.json")
    admin_client.post(f"/api/workshop/tasks/{task['id']}/check")
    run_queued_check(task["id"])
    spec = admin_client.get(f"/api/workshop/tasks/{task['id']}").json()["editing"]["spec"]
    spec["statement"] += "\nДополнение."
    edited = admin_client.put(f"/api/workshop/tasks/{task['id']}/draft", json={"number": 1, "spec": spec}).json()
    assert edited["editing"]["check_is_current"] is False
    problems = admin_client.post(f"/api/workshop/tasks/{task['id']}/publish", json={}).json()["problems"]
    assert any("изменилось после автопроверки" in p for p in problems)


def test_verify_reports_empty_task(admin_client):
    data = seed("slug.json")
    data["starter"] = data["solution"]  # стартовый код уже решает задачу
    task = admin_client.post("/api/workshop/tasks", json={"title": "Пустое", "kind": "python"}).json()
    admin_client.put(f"/api/workshop/tasks/{task['id']}/draft", json={"number": 1, "spec": data})
    admin_client.post(f"/api/workshop/tasks/{task['id']}/check")
    run_queued_check(task["id"])
    report = admin_client.get(f"/api/workshop/tasks/{task['id']}").json()["editing"]
    assert report["check_status"] == "failed"
    assert any("Стартовый код уже проходит" in p for p in report["check_report"]["problems"])


def test_kind_cannot_change_and_files_are_whitelisted(admin_client):
    task = admin_client.post("/api/workshop/tasks", json={"title": "Т", "kind": "python"}).json()
    other = {**seed("routes_sql.json")}
    assert admin_client.put(f"/api/workshop/tasks/{task['id']}/draft", json={"number": 1, "spec": other}).status_code == 409
    bad = {**seed("slug.json"), "starter": {"hack.sh": "rm -rf /"}}
    assert admin_client.put(f"/api/workshop/tasks/{task['id']}/draft", json={"number": 1, "spec": bad}).status_code == 422


def test_course_cannot_publish_with_unpublished_task(admin_client):
    task = create_task(admin_client, "slug.json")
    fragment = make_fragment("Flexbox", "оси")
    course = admin_client.post("/api/workshop/courses", json={"title": "Курс"}).json()
    content = {"modules": [{"id": "mod-1", "title": "М", "lessons": [{"id": "les-1", "title": "У", "blocks": [
        {"id": "blk-1", "type": "theory", "fragment_id": fragment},
        {"id": "blk-2", "type": "practice", "task_id": task["id"]},
    ]}]}]}
    saved = admin_client.put(f"/api/workshop/courses/{course['id']}/draft", json={"number": 1, "title": "Курс", "content": content})
    assert saved.json()["tasks"][str(task["id"])]["published"] is False
    problems = admin_client.post(f"/api/workshop/courses/{course['id']}/publish", json={}).json()["problems"]
    assert any("не опубликовано" in p for p in problems)


def test_harness_is_served_and_user_cannot_touch_workshop_tasks(client):
    make_user("anna", Role.user)
    login_as(client, "anna")
    assert "def dispatch" in client.get("/api/practice/harness/python").text
    assert "window.test" in client.get("/api/practice/harness/web").text
    assert client.get("/api/practice/harness/../../etc/passwd").status_code == 404
    assert client.get("/api/workshop/tasks").status_code == 403


def test_web_task_in_real_browser(admin_client):
    pytest.importorskip("playwright", reason="Chromium есть только в образе runner")
    report = runner.verify(runner.TaskSpec.model_validate(seed("header.json")))
    assert report["problems"] == [], report
    names = [r["name"] for r in report["solution"]["results"]]
    assert "На телефоне ссылки меню друг под другом" in names
    assert len(names) == len(set(names)) == 8  # каждая проверка — ровно один раз, на своей ширине
    starter_failed = [r["name"] for r in report["starter"]["results"] if not r["passed"]]
    assert "Шапка размечена тегом <header>" in starter_failed


def test_worker_process_knows_all_models():
    """Регрессия: процесс воркера не импортировал модели auth — внешний ключ на users не находился."""
    import subprocess
    import sys

    code = "import app.workers.__main__; from app.core.db import Base; print('users' in Base.metadata.tables)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=Path(__file__).parents[1])
    assert out.stdout.strip() == "True", out.stderr
