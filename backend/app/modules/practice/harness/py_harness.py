"""Проверка Python- и SQL-заданий. ОДИН файл для двух мест:
- в браузере (Pyodide, в Web Worker): интерфейс вызывает dispatch(json);
- в runner (обычный Python, отдельный процесс с лимитами): `python -I py_harness.py < запрос.json`.

Поэтому здесь только стандартная библиотека и никаких импортов из приложения.
"""

import contextlib
import io
import json
import sqlite3
import sys
import time
import traceback
import types

SQL_SECONDS = 5


# ---------- Python ----------


def _where(exc: BaseException) -> str:
    """Строка кода ученика, где случилась ошибка, — чтобы сообщение было полезным."""
    frames = [f for f in traceback.extract_tb(exc.__traceback__) if f.filename == "main.py"]
    return f" (main.py, строка {frames[-1].lineno})" if frames else ""


def _load_main(files: dict, out: io.StringIO):
    module = types.ModuleType("main")
    sys.modules["main"] = module
    try:
        with contextlib.redirect_stdout(out):
            exec(compile(files.get("main.py", ""), "main.py", "exec"), module.__dict__)
    except SyntaxError as exc:
        return None, f"Синтаксическая ошибка в строке {exc.lineno}: {exc.msg}"
    except Exception as exc:
        return None, f"Код упал при запуске: {type(exc).__name__}: {exc}{_where(exc)}"
    return module, None


def run_python(files: dict) -> dict:
    out = io.StringIO()
    _, error = _load_main(files, out)
    return {"stdout": out.getvalue()[-20000:], "error": error}


def check_python(files: dict, tests: str) -> dict:
    out = io.StringIO()
    module, error = _load_main(files, out)
    if error:
        return {"results": [], "error": error, "stdout": out.getvalue()[-20000:]}

    namespace: dict = {"__name__": "rz_tests"}
    exec(compile(tests, "tests.py", "exec"), namespace)
    results = []
    for name, fn in list(namespace.items()):
        if not (name.startswith("test_") and callable(fn)):
            continue
        # Название проверки — первая строка docstring: так ученик видит человеческий текст, а не test_xxx
        title = (fn.__doc__ or name).strip().splitlines()[0]
        try:
            with contextlib.redirect_stdout(out):
                fn()
            results.append({"name": title, "passed": True, "message": ""})
        except AssertionError as exc:
            results.append({"name": title, "passed": False, "message": str(exc) or "Проверка не прошла"})
        except Exception as exc:
            results.append({"name": title, "passed": False, "message": f"{type(exc).__name__}: {exc}{_where(exc)}"})
    return {"results": results, "error": None, "stdout": out.getvalue()[-20000:]}


# ---------- SQL ----------


def _statements(script: str) -> list[str]:
    statements, buffer = [], ""
    for piece in script.split(";"):
        buffer += piece + ";"
        if sqlite3.complete_statement(buffer):
            if buffer.strip(" \n\t;"):
                statements.append(buffer)
            buffer = ""
    if buffer.strip(" \n\t;"):
        statements.append(buffer)
    return statements


def _value(v):
    if isinstance(v, float):
        return round(v, 9)
    if isinstance(v, bytes):
        return v.hex()
    return v


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    deadline = time.monotonic() + SQL_SECONDS
    # Бесконечный рекурсивный запрос не должен повесить проверку
    conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10_000)
    return conn


def _execute(conn: sqlite3.Connection, script: str) -> dict | None:
    """Выполняет скрипт по одному оператору; возвращает результат последнего, который вернул строки."""
    last = None
    for statement in _statements(script):
        cursor = conn.execute(statement)
        if cursor.description is not None:
            last = {"columns": [d[0] for d in cursor.description], "rows": [[_value(v) for v in row] for row in cursor.fetchall()]}
    return last


def _sql_error(exc: Exception) -> str:
    if isinstance(exc, sqlite3.OperationalError) and "interrupted" in str(exc):
        return f"Запрос выполнялся дольше {SQL_SECONDS} с и был остановлен"
    return f"Ошибка SQL: {exc}"


def _prepared(setup: str) -> sqlite3.Connection:
    conn = _connect()
    conn.executescript(setup)
    return conn


def run_sql(setup: str, script: str) -> dict:
    conn = _prepared(setup)
    try:
        result = _execute(conn, script)
    except Exception as exc:
        return {"result": None, "error": _sql_error(exc)}
    return {"result": result, "error": None}


def _compare(expected: dict, actual: dict | None, order_matters: bool) -> str | None:
    if actual is None:
        return "Запрос не вернул ни одной таблицы — нужен SELECT"
    if len(actual["columns"]) != len(expected["columns"]):
        return f"Столбцов: ожидалось {len(expected['columns'])} ({', '.join(expected['columns'])}), у вас {len(actual['columns'])}"
    if len(actual["rows"]) != len(expected["rows"]):
        return f"Строк: ожидалось {len(expected['rows'])}, у вас {len(actual['rows'])}"
    exp_rows, act_rows = expected["rows"], actual["rows"]
    if not order_matters:
        exp_rows, act_rows = sorted(exp_rows, key=repr), sorted(act_rows, key=repr)
    for i, (e, a) in enumerate(zip(exp_rows, act_rows), 1):
        if e != a:
            where = f"строка {i}" if order_matters else "одна из строк"
            return f"Данные отличаются: {where} — ожидалось {e}, у вас {a}"
    return None


def expected_sql(setup: str, solution: str, checks: list) -> list:
    """Для runner: ожидаемые результаты по эталону. Ученику отдаются они, а не эталонный запрос."""
    conn = _prepared(setup)
    result = _execute(conn, solution)
    return [result if check.get("type", "same_result") == "same_result" else None for check in checks]


def check_sql(setup: str, script: str, checks: list, expected: list) -> dict:
    conn = _prepared(setup)
    try:
        actual = _execute(conn, script)
    except Exception as exc:
        return {"results": [], "error": _sql_error(exc)}

    results = []
    for check, exp in zip(checks, expected):
        message = None
        if check.get("type", "same_result") == "same_result":
            message = _compare(exp, actual, check.get("order_matters", False)) if exp else "Нет эталонного результата — задание не прошло автопроверку"
        else:
            try:
                row = conn.execute(check["sql"]).fetchone()
                if not (row and row[0]):
                    message = check.get("message") or "Проверка не прошла"
            except Exception as exc:
                message = _sql_error(exc)
        if message and check.get("message") and check.get("type", "same_result") == "same_result":
            message = f"{check['message']} ({message})"
        results.append({"name": check["name"], "passed": message is None, "message": message or ""})
    return {"results": results, "error": None, "preview": actual}


# ---------- вход ----------


def dispatch(payload: dict) -> dict:
    op = payload["op"]
    if op == "run_python":
        return run_python(payload["files"])
    if op == "check_python":
        return check_python(payload["files"], payload["tests"])
    if op == "run_sql":
        return run_sql(payload["setup"], payload["script"])
    if op == "check_sql":
        return check_sql(payload["setup"], payload["script"], payload["checks"], payload["expected"])
    if op == "expected_sql":
        return {"expected": expected_sql(payload["setup"], payload["script"], payload["checks"])}
    raise ValueError(f"Неизвестная операция {op!r}")


def dispatch_json(raw: str) -> str:
    return json.dumps(dispatch(json.loads(raw)), ensure_ascii=False)


if __name__ == "__main__":
    real_stdout = sys.stdout
    sys.stdout = io.StringIO()  # print из кода ученика не должен испортить JSON-ответ
    answer = dispatch_json(sys.stdin.read())
    real_stdout.write(answer)
