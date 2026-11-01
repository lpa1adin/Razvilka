"""Тренажёр архитектуры: 10 заданий на реальных проектах, проверка выбора и схем, авто-диаграммы, оценка описаний."""

from sqlalchemy import select

from app.core.db import SessionLocal
from app.modules.agent import claude
from app.modules.arch import diagrams, service
from app.modules.arch.exercises import BY_SLUG, EXERCISES
from app.modules.auth.models import Role
from app.modules.jobs.models import Job
from tests.conftest import login_as, make_user


def test_ten_exercises_on_real_projects_in_rising_order():
    assert len(EXERCISES) == 10
    assert [e["kind"] for e in EXERCISES] == ["choice"] * 5 + ["diagram"] * 3 + ["describe"] * 2
    assert {e["level"] for e in EXERCISES} == {"high", "low"}
    for ex in EXERCISES:
        for m in ex["materials"]:
            assert m["text"].strip() and m["license"]
            assert m["url"].startswith("https://github.com/") or m["project"].startswith("Развилка")
            if "github.com" in m["url"]:
                assert "/blob/" in m["url"] and len(m["url"].split("/blob/")[1].split("/")[0]) == 40  # закреплено на коммите


def test_answer_keys_agree_with_the_code():
    """Ключи схем по коду совпадают с тем, что генератор находит в самом файле — ответ не выдуман."""
    crud = BY_SLUG["fastapi-crud-calls"]
    auto = diagrams.build("python-calls", crud["materials"][0]["text"])
    found = {(e["from"], e["to"]) for e in auto["edges"]}
    assert {tuple(e) for e in crud["expected"]} == found
    models = diagrams.build("python", BY_SLUG["fastapi-models-relations"]["materials"][0]["text"])
    assert ("UserCreate", "UserBase", "inherits") in {(e["from"], e["to"], e["kind"]) for e in models["edges"]}
    # В compose Sock Shop связи почти не объявлены — генератор честно видит только две
    sock = diagrams.build("compose", BY_SLUG["sockshop-diagram"]["materials"][0]["text"])
    assert {(e["from"], e["to"]) for e in sock["edges"]} == {("user", "user-db"), ("user-sim", "edge-router")}
    # В Развилке depends_on ведёт воркеры к api, а за данными они ходят в postgres — урок задания 7
    rz = diagrams.build("compose", BY_SLUG["razvilka-dataflow"]["materials"][0]["text"])
    assert ("runner", "api") in {(e["from"], e["to"]) for e in rz["edges"]}
    assert ["runner", "postgres"] in BY_SLUG["razvilka-dataflow"]["expected"]
    k8s = diagrams.build("k8s", BY_SLUG["boutique-k8s-discovery"]["materials"][0]["text"])
    assert ("frontend", "cartservice") in {(e["from"], e["to"]) for e in k8s["edges"]}


def test_public_view_hides_answers():
    for ex in EXERCISES:
        view = service.public(ex)
        assert not {"correct", "expected", "keypoints", "explanation"} & set(view)


def test_grading_choice_and_diagram():
    single = BY_SLUG["razvilka-compose-type"]
    assert service.grade_choice(single, ["b"])[0] == 5 and service.grade_choice(single, ["a"])[0] == 0
    multi = BY_SLUG["fastapi-compose-services"]
    assert service.grade_choice(multi, ["a", "b", "d"])[0] == 5
    assert service.grade_choice(multi, ["a", "c"])[0] == 0  # одно верное, одно неверное — ноль
    crud = BY_SLUG["fastapi-crud-calls"]
    score, result = service.grade_diagram(crud, [
        ["create_user", "get_password_hash"], ["update_user", "get_password_hash"], ["get_user_by_email", "select"],
        ["get_user_by_email", "authenticate"],  # перепутано направление
        ["create_item", "select"],  # лишняя
    ])
    assert result["reversed"] == [["get_user_by_email", "authenticate"]] and result["extra"] == [["create_item", "select"]]
    assert result["missed"] == [["authenticate", "verify_password"]]
    assert score == round((3 + 0.5 - 0.5) / 5 * 5, 2)


def test_api_flow_and_describe_evaluation(client, monkeypatch):
    make_user("learner", Role.user)
    login_as(client, "learner")
    assert len(client.get("/api/arch").json()) == 10
    detail = client.get("/api/arch/sockshop-diagram").json()
    assert "expected" not in detail["exercise"] and len(detail["exercise"]["nodes"]) == 14

    done = client.post("/api/arch/sockshop-diagram/attempts", json={"edges": [["edge-router", "front-end"], ["front-end", "catalogue"]]}).json()
    assert done["status"] == "done" and done["score"] == round(2 / 15 * 5, 2)
    assert done["reveal"]["auto_diagram"]["edges"] and done["reveal"]["expected"]  # после ответа — ключ и авто-схема

    monkeypatch.setattr(claude, "configured", lambda: True)
    text = ("Это микросервисы: у каждого сервиса своя папка в src. Сервисы общаются по gRPC через общий контракт demo.proto. "
            "Написаны на Go, Java, Python и Node.js.")
    sent = client.post("/api/arch/boutique-describe/attempts", json={"text": text}).json()
    assert sent["status"] == "evaluating"

    from app.modules.arch.service import DescribeReport

    def fake(purpose, prompt, system, schema, **kwargs):
        assert kwargs["library"] is False and text in prompt
        return DescribeReport.model_validate({"points": [
            {"id": "k1", "covered": True, "quote": "у каждого сервиса своя папка в src"},
            {"id": "k2", "covered": True, "quote": "общаются по gRPC через общий контракт demo.proto"},
            {"id": "k4", "covered": True, "quote": "на Go, Java, Python и Node.js, потому что gRPC"},  # «цитаты» нет в ответе
            {"id": "k5", "covered": False, "quote": ""},
        ], "feedback": "Не раскрыто развёртывание и цена."})

    monkeypatch.setattr(claude, "run_structured", fake)
    with SessionLocal() as db:
        job = db.scalar(select(Job).where(Job.kind == "review"))
        service.evaluate_describe(db, int(job.payload["attempt_id"]))
    out = client.get(f"/api/arch/attempts/{sent['id']}").json()
    assert out["result"]["covered"] == 2 and out["score"] == round(2 / 6 * 5, 2)  # k4 не засчитан: цитата не из ответа
    assert [p["covered"] for p in out["result"]["points"]] == [True, True, False, False, False, False]

    make_user("other", Role.user)
    login_as(client, "other")
    assert client.get(f"/api/arch/attempts/{sent['id']}").status_code == 404
    assert client.post("/api/arch/boutique-describe/attempts", json={"text": "коротко"}).status_code == 409


def test_only_first_answer_counts(client):
    """Правильный ответ виден после первой попытки — значит, засчитывается только она."""
    make_user("learner", Role.user)
    login_as(client, "learner")
    first = client.post("/api/arch/razvilka-compose-type/attempts", json={"picked": ["a"]}).json()
    assert first["counted"] is True and first["score"] == 0 and first["reveal"]["correct"] == ["b"]
    again = client.post("/api/arch/razvilka-compose-type/attempts", json={"picked": ["b"]})
    assert again.status_code == 409 and "уже засчитан" in again.json()["detail"]

    edges = {"edges": [["edge-router", "front-end"]]}
    assert client.post("/api/arch/sockshop-diagram/attempts", json=edges).json()["counted"] is True
    full = {"edges": BY_SLUG["sockshop-diagram"]["expected"]}
    practice = client.post("/api/arch/sockshop-diagram/attempts", json=full).json()
    assert practice["counted"] is False and practice["score"] == 5  # тренировка после разбора — на балл не влияет

    cards = {c["slug"]: c for c in client.get("/api/arch").json()}
    assert cards["sockshop-diagram"]["score"] == round(1 / 15 * 5, 2) and cards["sockshop-diagram"]["attempts"] == 2
    assert cards["razvilka-compose-type"]["score"] == 0
    detail = client.get("/api/arch/sockshop-diagram").json()
    assert detail["counted"]["score"] == round(1 / 15 * 5, 2) and detail["next"] == "razvilka-dataflow"


def test_own_material_has_no_answer_in_comments():
    text = BY_SLUG["razvilka-compose-type"]["materials"][0]["text"]
    assert "монолит" not in text and "ADR" not in text and "#" not in text
    assert BY_SLUG["razvilka-compose-type"]["materials"][0]["note"]
    # Чужие файлы показываются как есть — лицензия
    assert "Licensed under the Apache License" in BY_SLUG["boutique-email-pattern"]["materials"][0]["text"]
