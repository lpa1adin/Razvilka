"""py_harness.py — тот же файл, что выполняется в браузере (Pyodide). Проверяем его поведение здесь."""

import importlib.util
import json
from pathlib import Path

import pytest

SEED = Path(__file__).parents[1] / "app" / "modules" / "practice" / "seed"
spec = importlib.util.spec_from_file_location(
    "py_harness", Path(__file__).parents[1] / "app" / "modules" / "practice" / "harness" / "py_harness.py"
)
harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)


def seed(name: str) -> dict:
    return json.loads((SEED / name).read_text(encoding="utf-8"))


def test_python_solution_passes_and_starter_fails():
    task = seed("slug.json")
    good = harness.check_python(task["solution"], task["tests"])
    bad = harness.check_python(task["starter"], task["tests"])
    assert good["error"] is None and all(r["passed"] for r in good["results"])
    assert good["results"][0]["name"] == "«Гора Фишт» → gora-fisht"  # имя проверки из docstring
    assert not all(r["passed"] for r in bad["results"])
    assert "gora-fisht" in good["stdout"]


def test_python_errors_are_explained():
    syntax = harness.check_python({"main.py": "def f(:\n  pass"}, "def test_x():\n    pass")
    assert syntax["error"].startswith("Синтаксическая ошибка в строке 1")
    crash = harness.check_python({"main.py": "x = 1\n1 / 0\n"}, "")
    assert "ZeroDivisionError" in crash["error"] and "строка 2" in crash["error"]
    runtime = harness.check_python({"main.py": "def f():\n    return [][1]\n"}, "from main import f\ndef test_f():\n    f()\n")
    assert "IndexError" in runtime["results"][0]["message"] and "строка 2" in runtime["results"][0]["message"]


def test_sql_expected_then_check():
    task = seed("routes_sql.json")
    checks = task["sql_checks"]
    expected = harness.expected_sql(task["sql_setup"], task["solution"]["query.sql"], checks)
    assert expected[0]["rows"][0] == ["Оштен — Фишт", 67.0] and expected[1] is None

    good = harness.check_sql(task["sql_setup"], task["solution"]["query.sql"], checks, expected)
    assert all(r["passed"] for r in good["results"])

    starter = harness.check_sql(task["sql_setup"], task["starter"]["query.sql"], checks, expected)
    assert "Столбцов: ожидалось 2" in starter["results"][0]["message"]

    unordered = harness.check_sql(task["sql_setup"], "SELECT name, length_km FROM routes WHERE difficulty >= 4", checks, expected)
    assert "строка 1" in unordered["results"][0]["message"]

    vandal = harness.check_sql(task["sql_setup"], "DELETE FROM routes WHERE id = 1; SELECT name, length_km FROM routes WHERE difficulty >= 4 ORDER BY length_km DESC;", checks, expected)
    assert vandal["results"][1]["message"] == "Запрос изменил таблицу routes — нужен только SELECT"


def test_sql_runaway_query_is_stopped(monkeypatch):
    monkeypatch.setattr(harness, "SQL_SECONDS", 1)
    result = harness.run_sql("", "WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM n) SELECT count(*) FROM n;")
    assert "дольше 1 с" in result["error"]


def test_sql_syntax_error():
    result = harness.run_sql("CREATE TABLE t (a);", "SELEC * FROM t;")
    assert result["error"].startswith("Ошибка SQL:")


@pytest.mark.parametrize("op", ["nope"])
def test_unknown_op(op):
    with pytest.raises(ValueError):
        harness.dispatch({"op": op})
