import pytest

from app.core.db import SessionLocal
from app.modules.jobs.models import Job
from app.modules.system import cells
from tests.conftest import make_fragment
from tests.test_courses import create_and_publish
from tests.test_practice import create_task


def call(fn, *args, **kwargs):
    with SessionLocal() as db:
        return fn(db, *args, **kwargs)


def test_map_and_show_course_cells(admin_client):
    fragment = make_fragment("Flexbox", "оси и выравнивание")
    course = create_and_publish(admin_client, fragment)
    cid = course["id"]

    assert f"{cid} «Вёрстка сайта про Фишт» [опубл.]" in call(cells.course_list)
    text = call(cells.course_map, cid)
    assert f"{cid}/1.1 Урок «Зачем нужен flex»" in text
    assert f"{cid}/1.1/1 теория fragment:{fragment} «Flexbox»" in text

    assert call(cells.show, f"{cid}/1.1/goal") == "Понять оси"
    assert call(cells.show, f"{cid}/1.1/1/why") == "Основа раскладки"
    assert "оси и выравнивание" in call(cells.show, f"{cid}/1.1/1")  # блок теории ведёт к статье


def test_set_lesson_field_goes_to_new_draft(admin_client):
    course = create_and_publish(admin_client, make_fragment("Flexbox", "оси"))
    cid = course["id"]

    result = call(cells.set_cell, f"{cid}/1.2/goal", "Закрепить оси\n")
    assert "создан черновик" in result
    assert call(cells.show, f"{cid}/1.2/goal") == "Закрепить оси"
    # Опубликованная версия осталась прежней
    published = admin_client.get(f"/api/courses/{course['slug']}/lessons/les-2").json()
    assert published["goal"] == ""


def test_task_cells_and_free_check(admin_client):
    task = create_task(admin_client, "slug.json")
    address = f"task:{task['id']}"

    summary = call(cells.show, address)
    assert f"{address}/tests" in summary and "Стоит в уроках: нигде" in summary

    result = call(cells.set_cell, f"{address}/hints/1", "Начните с малого")
    assert "автопроверка поставлена в очередь" in result
    assert call(cells.show, f"{address}/hints/1") == "Начните с малого"
    with SessionLocal() as db:
        assert [j.kind for j in db.query(Job).all()] == ["runner"]  # ничего платного

    tests = call(cells.show, f"{address}/tests")
    call(cells.set_cell, f"{address}/tests", tests + "\n# правка\n", check=False)
    assert call(cells.show, f"{address}/tests").endswith("# правка\n")


@pytest.mark.parametrize("address, message", [
    ("99", "Курс #99 не найдено"),
    ("task:99/tests", "Задание #99 не найдено"),
    ("page:1", "Не знаю «page:»"),
])
def test_bad_address_is_explained(admin_client, address, message):
    with pytest.raises(cells.CellError, match=message):
        call(cells.show, address)


def test_bad_value_is_not_saved(admin_client):
    task = create_task(admin_client, "slug.json")
    with pytest.raises(cells.CellError, match="Не сохранено"):
        call(cells.set_cell, f"task:{task['id']}/solution/hack.sh", "rm -rf /")
