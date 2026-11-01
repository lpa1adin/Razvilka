"""Автотесты сданного Python-проекта. Запускается в runner отдельным процессом с лимитами:
    python -I project_harness.py <папка-сдачи> < tests.py
Тесты практикума — функции test_*; первая строка docstring — название проверки. Код ученика импортируется
из папки сдачи как обычные модули. Только стандартная библиотека.
"""

import contextlib
import io
import json
import os
import sys
import traceback


def _where(exc: BaseException, root: str) -> str:
    frames = [f for f in traceback.extract_tb(exc.__traceback__) if f.filename.startswith(root)]
    if not frames:
        return ""
    f = frames[-1]
    return f" ({os.path.relpath(f.filename, root)}, строка {f.lineno})"


def main() -> None:
    root = os.path.abspath(sys.argv[1])
    tests = sys.stdin.read()
    sys.path.insert(0, root)
    os.chdir(root)
    out = io.StringIO()
    namespace: dict = {"__name__": "rz_project_tests"}
    try:
        with contextlib.redirect_stdout(out):
            exec(compile(tests, "tests.py", "exec"), namespace)
    except Exception as exc:
        print(json.dumps({"results": [], "error": f"Тесты не загрузились: {type(exc).__name__}: {exc}{_where(exc, root)}"}, ensure_ascii=False))
        return
    results = []
    for name, fn in list(namespace.items()):
        if not (name.startswith("test_") and callable(fn)):
            continue
        title = (fn.__doc__ or name).strip().splitlines()[0]
        try:
            with contextlib.redirect_stdout(out):
                fn()
            results.append({"name": title, "passed": True, "message": ""})
        except AssertionError as exc:
            results.append({"name": title, "passed": False, "message": str(exc) or "Проверка не прошла"})
        except Exception as exc:
            results.append({"name": title, "passed": False, "message": f"{type(exc).__name__}: {exc}{_where(exc, root)}"})
    print(json.dumps({"results": results, "error": None, "stdout": out.getvalue()[-5000:]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
