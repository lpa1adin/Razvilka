import json
import random
from pathlib import Path

import pytest

from app.core.db import SessionLocal
from app.modules.auth.models import Role, User
from app.modules.quiz import service
from app.modules.quiz.models import Question, QuestionStatus, QuizTopic
from app.modules.quiz.schemas import QuestionIn
from tests.conftest import login_as, make_fragment, make_user

SEED = Path(__file__).parents[1] / "app" / "modules" / "quiz" / "seed"


def single(prompt: str, subtopic: str = "", difficulty: int = 2, fragment_id: int | None = None) -> dict:
    return {
        "type": "single", "prompt": prompt, "subtopic": subtopic, "difficulty": difficulty,
        "options": {"items": [{"id": "a", "text": "верно"}, {"id": "b", "text": "неверно"}]},
        "answer": {"correct": ["a"]}, "explanation": "Потому что так.", "fragment_id": fragment_id,
        "status": "published" if fragment_id else "draft",
    }


def make_topic(n: int, size: int = 10, subtopics: int = 1) -> QuizTopic:
    fragment = make_fragment("Источник", "текст")
    with SessionLocal() as db:
        topic = QuizTopic(slug=f"topic-{n}-{size}", title="Тема", size=size, published=True)
        db.add(topic)
        db.flush()
        for i in range(n):
            # уникальные слова, чтобы проверка дублей не мешала
            data = QuestionIn.model_validate(single(f"Вопрос номер {i} слово{i}x{i}", f"подтема {i % subtopics}", 1 + i % 3, fragment))
            db.add(Question(topic_id=topic.id, **data.model_dump()))
        db.commit()
        return topic


def user(login: str = "anna") -> User:
    make_user(login, Role.user)
    with SessionLocal() as db:
        return db.query(User).filter_by(login=login).one()


def run_attempt(db, u, topic, wrong: set[int] = frozenset(), mistakes: bool = False) -> list[int]:
    attempt = service.start(db, u, db.get(QuizTopic, topic.id), mistakes, random.Random(len(wrong)))
    ids = []
    for item in service.last_items(db, attempt):
        ids.append(item.question_id)
        service.save_answer(db, attempt, item.position, {"selected": ["b" if item.question_id in wrong else "a"]})
    service.finish(db, attempt)
    return ids


def test_two_tests_in_a_row_have_no_repeats():
    topic, u = make_topic(50), user()
    with SessionLocal() as db:
        first, second = run_attempt(db, u, topic), run_attempt(db, u, topic)
    assert len(first) == len(second) == 10
    assert not set(first) & set(second)


def test_when_unseen_run_out_mistakes_come_first():
    topic, u = make_topic(12), user()
    with SessionLocal() as db:
        first = run_attempt(db, u, topic, wrong=set())
        wrong = set(first[:3])
        # переписываем ответы: три ошибки в первом тесте
        db.query(service.QuizAttemptItem).filter(service.QuizAttemptItem.question_id.in_(wrong)).update({"correct": False}, synchronize_session=False)
        db.commit()
        second = run_attempt(db, u, topic)
    unseen = {q for q in range(1, 13)} - set(first)
    assert unseen <= set(second)  # сначала все невиданные (их 2)
    assert wrong <= set(second)  # потом — те, где ошибся


def test_questions_are_spread_across_subtopics():
    topic, u = make_topic(30, size=9, subtopics=3), user()
    with SessionLocal() as db:
        ids = run_attempt(db, u, topic)
        subs = [db.get(Question, i).subtopic for i in ids]
    assert sorted(subs.count(s) for s in set(subs)) == [3, 3, 3]


def test_interrupted_attempt_resumes_and_answers_hidden_until_finish(client):
    topic = make_topic(5, size=10)
    make_user("anna", Role.user)
    login_as(client, "anna")
    started = client.post(f"/api/quiz/topics/{topic.slug}/attempts", json={}).json()
    assert started["note"].startswith("В теме пока 5")
    assert all(i["answer"] is None and i["correct"] is None and i["explanation_html"] is None for i in started["items"])
    again = client.post(f"/api/quiz/topics/{topic.slug}/attempts", json={}).json()
    assert again["id"] == started["id"]  # продолжаем тот же тест

    assert client.put(f"/api/quiz/attempts/{started['id']}/items/1", json={"response": {"selected": ["a"]}}).status_code == 204
    assert client.put(f"/api/quiz/attempts/{started['id']}/items/1", json={"response": {"selected": ["zzz"]}}).status_code == 409
    done = client.post(f"/api/quiz/attempts/{started['id']}/finish").json()
    assert done["score"] == 1 and done["total"] == 5  # без ответа — ошибка
    assert done["items"][0]["answer"] == {"correct": ["a"]} and done["items"][0]["source"]["title"] == "Источник"
    assert client.put(f"/api/quiz/attempts/{started['id']}/items/2", json={"response": {"selected": ["a"]}}).status_code == 409

    mistakes = client.post(f"/api/quiz/topics/{topic.slug}/attempts", json={"mistakes_only": True}).json()
    assert mistakes["total"] == 4 and mistakes["mistakes_only"] is True

    make_user("boris", Role.user)
    login_as(client, "boris")
    assert client.get(f"/api/quiz/attempts/{started['id']}").status_code == 404


@pytest.mark.parametrize(
    "kind,options,answer,good,bad",
    [
        ("multiple", {"items": [{"id": "a", "text": "1"}, {"id": "b", "text": "2"}, {"id": "c", "text": "3"}]}, {"correct": ["a", "c"]},
         {"selected": ["c", "a"]}, {"selected": ["a"]}),
        ("order", {"items": [{"id": "a", "text": "1"}, {"id": "b", "text": "2"}]}, {"order": ["a", "b"]}, {"order": ["a", "b"]}, {"order": ["b", "a"]}),
        ("match", {"left": [{"id": "l0", "text": "x"}, {"id": "l1", "text": "y"}], "right": [{"id": "r0", "text": "1"}, {"id": "r1", "text": "2"}]},
         {"pairs": {"l0": "r0", "l1": "r1"}}, {"pairs": {"l1": "r1", "l0": "r0"}}, {"pairs": {"l0": "r1", "l1": "r0"}}),
    ],
)
def test_grading(kind, options, answer, good, bad):
    snapshot = {"type": kind, "options": options, "answer": answer}
    assert service.grade(snapshot, good) is True
    assert service.grade(snapshot, bad) is False


def test_admin_duplicate_warning_and_source_rule(admin_client):
    topic = admin_client.post("/api/workshop/quiz/topics", json={"title": "Flexbox", "published": True}).json()
    fragment = make_fragment("Flexbox", "оси")
    q = single("Какое свойство выравнивает элементы вдоль главной оси flex-контейнера?", fragment_id=fragment)
    assert admin_client.post(f"/api/workshop/quiz/topics/{topic['id']}/questions", json=q).status_code == 201
    dup = admin_client.post(f"/api/workshop/quiz/topics/{topic['id']}/questions", json={**q, "prompt": "Какое свойство выравнивает элементы вдоль главной оси у flex-контейнера?"})
    assert dup.status_code == 409 and dup.json()["similar"][0]["similarity"] >= 0.6
    forced = admin_client.post(f"/api/workshop/quiz/topics/{topic['id']}/questions?force=true", json={**q, "prompt": "Какое свойство выравнивает элементы вдоль главной оси у flex-контейнера?"})
    assert forced.status_code == 201
    no_source = admin_client.post(f"/api/workshop/quiz/topics/{topic['id']}/questions", json={**single("Совсем другой вопрос про отступы"), "status": "published"})
    assert no_source.status_code == 422
    bad_single = admin_client.post(f"/api/workshop/quiz/topics/{topic['id']}/questions", json={**single("Вопрос с двумя ответами"), "answer": {"correct": ["a", "b"]}})
    assert bad_single.status_code == 422


def test_used_question_is_archived_not_deleted(client):
    topic = make_topic(3)
    make_user("anna", Role.user)
    login_as(client, "anna")
    client.post(f"/api/quiz/topics/{topic.slug}/attempts", json={})
    make_user("boss", Role.admin)
    login_as(client, "boss")
    questions = client.get(f"/api/workshop/quiz/topics/{topic.id}/questions").json()
    client.delete(f"/api/workshop/quiz/questions/{questions[0]['id']}")
    with SessionLocal() as db:
        assert db.get(Question, questions[0]["id"]).status is QuestionStatus.archived


def test_user_cannot_edit_banks(client):
    make_user("anna", Role.user)
    login_as(client, "anna")
    assert client.get("/api/workshop/quiz/topics").status_code == 403


@pytest.mark.parametrize("name", ["layout.json", "js_compare.json"])
def test_seed_banks_are_valid(name):
    data = json.loads((SEED / name).read_text(encoding="utf-8"))
    for raw in data["questions"]:
        assert raw.pop("source") and raw.pop("fragment")
        QuestionIn.model_validate({**raw, "fragment_id": 1, "status": "published"})
    if name == "layout.json":
        assert len(data["questions"]) >= 50


def test_quiz_block_in_lesson(client):
    topic = make_topic(12)
    fragment = make_fragment("Flexbox", "оси")
    make_user("boss", Role.admin)
    login_as(client, "boss")
    course = client.post("/api/workshop/courses", json={"title": "Курс"}).json()
    content = {"modules": [{"id": "mod-1", "title": "М", "lessons": [{"id": "les-1", "title": "У", "blocks": [
        {"id": "blk-1", "type": "theory", "fragment_id": fragment},
        {"id": "blk-2", "type": "quiz", "topic_id": topic.id},
    ]}]}]}
    saved = client.put(f"/api/workshop/courses/{course['id']}/draft", json={"number": 1, "title": "Курс", "content": content}).json()
    assert saved["quiz_topics"][str(topic.id)]["published"] is True
    assert client.post(f"/api/workshop/courses/{course['id']}/publish", json={}).status_code == 200
    make_user("anna", Role.user)
    login_as(client, "anna")
    lesson = client.get(f"/api/courses/{course['slug']}/lessons/les-1").json()
    assert lesson["quizzes"][0]["topic"] == {"slug": topic.slug, "title": "Тема", "questions": 12, "size": 10}

