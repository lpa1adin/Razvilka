from app.modules.auth.models import Role
from app.modules.library.models import FragmentStatus
from tests.conftest import login_as, make_fragment, make_user


def content(fragment_id: int, lesson_title: str = "Зачем нужен flex") -> dict:
    return {"modules": [{"id": "mod-1", "title": "Вёрстка", "lessons": [
        {"id": "les-1", "title": lesson_title, "goal": "Понять оси", "blocks": [
            {"id": "blk-1", "type": "theory", "fragment_id": fragment_id, "why": "Основа раскладки"}
        ]},
        {"id": "les-2", "title": "Ещё урок", "blocks": [{"id": "blk-2", "type": "theory", "fragment_id": fragment_id}]},
    ]}]}


def create_and_publish(client, fragment_id: int) -> dict:
    course = client.post("/api/workshop/courses", json={"title": "Вёрстка сайта про Фишт"}).json()
    client.put(f"/api/workshop/courses/{course['id']}/draft", json={
        "number": course["draft_version"], "title": "Вёрстка сайта про Фишт", "description": "", "content": content(fragment_id),
    })
    published = client.post(f"/api/workshop/courses/{course['id']}/publish", json={})
    assert published.status_code == 200, published.text
    return published.json()


def test_slug_is_transliterated_and_unique(admin_client):
    a = admin_client.post("/api/workshop/courses", json={"title": "Гора Фишт"}).json()
    b = admin_client.post("/api/workshop/courses", json={"title": "Гора Фишт"}).json()
    assert (a["slug"], b["slug"]) == ("gora-fisht", "gora-fisht-2")


def test_publish_explains_what_is_missing(admin_client):
    course = admin_client.post("/api/workshop/courses", json={"title": "Пустой"}).json()
    response = admin_client.post(f"/api/workshop/courses/{course['id']}/publish", json={})
    assert response.status_code == 422
    assert "В курсе нет ни одного модуля." in response.json()["problems"]

    gone = make_fragment("Удалённая", "текст", status=FragmentStatus.removed)
    admin_client.put(f"/api/workshop/courses/{course['id']}/draft", json={
        "number": 1, "title": "Пустой", "content": content(gone),
    })
    problems = admin_client.post(f"/api/workshop/courses/{course['id']}/publish", json={}).json()["problems"]
    assert any("удалена из источника" in p for p in problems)


def test_user_sees_only_published_and_draft_is_admin_only(client):
    fragment = make_fragment("Flexbox", "оси")
    make_user("boss", Role.admin)
    login_as(client, "boss")
    draft_only = client.post("/api/workshop/courses", json={"title": "Черновик"}).json()
    course = create_and_publish(client, fragment)

    make_user("anna", Role.user)
    login_as(client, "anna")
    assert [c["slug"] for c in client.get("/api/courses").json()] == [course["slug"]]
    assert client.get(f"/api/courses/{draft_only['slug']}").status_code == 404
    assert client.get(f"/api/courses/{course['slug']}", params={"version": 1}).status_code == 403
    assert client.get("/api/workshop/courses").status_code == 403

    lesson = client.get(f"/api/courses/{course['slug']}/lessons/les-1").json()
    block = lesson["blocks"][0]
    assert block["why"] == "Основа раскладки"
    assert block["fragment"]["source"]["license_name"] == "CC BY-SA 2.5"
    assert lesson["next_lesson"]["id"] == "les-2" and lesson["prev_lesson"] is None


def test_editing_published_creates_new_version_and_learner_stays_on_old(client):
    fragment = make_fragment("Flexbox", "оси")
    make_user("boss", Role.admin)
    make_user("anna", Role.user)
    login_as(client, "boss")
    course = create_and_publish(client, fragment)
    cid, slug = course["id"], course["slug"]

    login_as(client, "anna")
    assert client.put(f"/api/courses/{slug}/lessons/les-1/done").status_code == 204

    login_as(client, "boss")
    draft = client.post(f"/api/workshop/courses/{cid}/draft").json()
    assert (draft["published_version"], draft["draft_version"]) == (1, 2)
    client.put(f"/api/workshop/courses/{cid}/draft", json={
        "number": 2, "title": "Вёрстка сайта про Фишт", "content": content(fragment, "Оси flex — новая редакция"),
    })
    # пока не опубликовано, пользователь видит старое
    login_as(client, "anna")
    assert client.get(f"/api/courses/{slug}/lessons/les-1").json()["title"] == "Зачем нужен flex"

    login_as(client, "boss")
    assert client.post(f"/api/workshop/courses/{cid}/publish", json={"change_note": "Переписан урок"}).status_code == 200
    versions = client.get(f"/api/workshop/courses/{cid}/versions").json()
    assert [(v["number"], v["status"]) for v in versions] == [(2, "published"), (1, "superseded")]

    login_as(client, "anna")
    detail = client.get(f"/api/courses/{slug}").json()
    assert detail["version"] == 1 and detail["has_update"] is True and detail["lessons_done"] == 1
    client.post(f"/api/courses/{slug}/upgrade")
    detail = client.get(f"/api/courses/{slug}").json()
    # id уроков стабильны: пройденное переехало в новую версию
    assert detail["version"] == 2 and detail["has_update"] is False and detail["lessons_done"] == 1


def test_stale_draft_save_is_rejected(admin_client):
    course = admin_client.post("/api/workshop/courses", json={"title": "Курс"}).json()
    response = admin_client.put(f"/api/workshop/courses/{course['id']}/draft", json={"number": 7, "title": "Курс", "content": {"modules": []}})
    assert response.status_code == 409


def test_published_course_cannot_be_deleted_but_can_be_archived(client):
    fragment = make_fragment("Flexbox", "оси")
    make_user("boss", Role.admin)
    login_as(client, "boss")
    course = create_and_publish(client, fragment)
    assert client.delete(f"/api/workshop/courses/{course['id']}").status_code == 409
    client.post(f"/api/workshop/courses/{course['id']}/archive")
    make_user("anna", Role.user)
    login_as(client, "anna")
    assert client.get("/api/courses").json() == []


def test_changed_fragment_shows_where_it_is_used(client):
    fragment = make_fragment("Flexbox", "оси", needs_review=True)
    make_user("boss", Role.admin)
    login_as(client, "boss")
    create_and_publish(client, fragment)
    review = client.get("/api/workshop/fragments/review").json()
    assert review[0]["id"] == fragment
    assert {u["lesson_title"] for u in review[0]["used_in"]} == {"Зачем нужен flex", "Ещё урок"}
    client.post(f"/api/workshop/fragments/{fragment}/reviewed")
    assert client.get("/api/workshop/fragments/review").json() == []
