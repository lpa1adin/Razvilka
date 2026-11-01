"""Сервис runner: выполняет код заданий вне браузера (ADR-006).

Сейчас — автопроверка задания перед публикацией: эталон обязан пройти все проверки, стартовый код — нет.
На этапе 6 сюда же придут сдачи проектов. Контейнер runner без интернета; Python-код выполняется
в отдельном процессе с лимитами, веб-задания — в Chromium с запретом любых сетевых запросов.
"""

import hashlib
import json
import resource
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.practice.models import CheckStatus, TaskVersion
from app.modules.practice.schemas import TaskSpec
from app.modules.practice.webpage import WIDTHS, build_page

PY_HARNESS = Path(__file__).parent / "harness" / "py_harness.py"
TIMEOUT = 15


def spec_hash(spec: dict) -> str:
    return hashlib.sha256(json.dumps(spec, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _limits() -> None:
    # Выполняется в дочернем процессе перед запуском кода ученика
    resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
    resource.setrlimit(resource.RLIMIT_AS, (1024 * 1024 * 1024, 1024 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_FSIZE, (10 * 1024 * 1024, 10 * 1024 * 1024))


def run_py_harness(payload: dict) -> dict:
    """Тот же py_harness.py, что и в браузере, — в отдельном процессе без переменных окружения приложения."""
    with tempfile.TemporaryDirectory() as tmp:
        try:
            proc = subprocess.run(
                [sys.executable, "-I", str(PY_HARNESS)],
                input=json.dumps(payload, ensure_ascii=False),
                capture_output=True,
                text=True,
                timeout=TIMEOUT,
                cwd=tmp,
                env={"PATH": "/usr/bin:/bin", "HOME": tmp, "LANG": "C.UTF-8"},
                preexec_fn=_limits,
            )
        except subprocess.TimeoutExpired:
            return {"results": [], "error": f"Код выполнялся дольше {TIMEOUT} с — возможно, бесконечный цикл"}
    if proc.returncode != 0 or not proc.stdout:
        return {"results": [], "error": f"Проверка не запустилась: {proc.stderr.strip()[-500:] or 'процесс завершился без ответа'}"}
    return json.loads(proc.stdout)


def check_web(files: dict, tests: str) -> dict:
    from playwright.sync_api import sync_playwright  # есть только в образе runner

    results, errors = [], []
    with sync_playwright() as p:
        # /dev/shm в контейнере маленький — без этого флага Chromium падает на тяжёлых страницах
        browser = p.chromium.launch(args=["--disable-dev-shm-usage"])
        try:
            context = browser.new_context()
            context.route("**/*", lambda route: route.abort())  # никаких запросов наружу
            for width in WIDTHS:
                # Новая страница на каждую ширину: set_content переписывает документ в том же окне,
                # и window.__rzResults от прошлой ширины иначе остался бы на месте
                page = context.new_page()
                page.set_viewport_size({"width": width, "height": 900})
                page.set_content(build_page(files, tests, width, "check"), wait_until="load", timeout=10_000)
                page.wait_for_function("window.__rzResults", timeout=TIMEOUT * 1000)
                data = page.evaluate("window.__rzResults")
                page.close()
                results += data["results"]
                errors += [e for e in data["errors"] if e not in errors]
        finally:
            browser.close()
    return {"results": results, "error": f"Ошибки в скрипте страницы: {'; '.join(errors)}" if errors else None}


def run_checks(spec: TaskSpec, files: dict, expected: list | None = None) -> dict:
    if spec.kind == "web":
        return check_web(files, spec.tests)
    if spec.kind == "python":
        return run_py_harness({"op": "check_python", "files": files, "tests": spec.tests})
    checks = [c.model_dump() for c in spec.sql_checks]
    return run_py_harness({"op": "check_sql", "setup": spec.sql_setup, "script": files.get("query.sql", ""), "checks": checks, "expected": expected or []})


def _all_passed(outcome: dict) -> bool:
    return not outcome.get("error") and bool(outcome.get("results")) and all(r["passed"] for r in outcome["results"])


def verify(spec: TaskSpec) -> dict:
    report: dict = {"problems": [], "checked_at": datetime.now(UTC).isoformat()}
    has_checks = bool(spec.sql_checks) if spec.kind == "sql" else "test" in spec.tests
    if not has_checks:
        report["problems"].append("В задании нет ни одной проверки.")
        return report

    expected = None
    if spec.kind == "sql":
        computed = run_py_harness({
            "op": "expected_sql", "setup": spec.sql_setup, "script": spec.solution.get("query.sql", ""),
            "checks": [c.model_dump() for c in spec.sql_checks],
        })
        if computed.get("error") or "expected" not in computed:
            report["problems"].append(f"Эталонный запрос не выполнился: {computed.get('error')}")
            return report
        expected = report["sql_expected"] = computed["expected"]

    solution = report["solution"] = run_checks(spec, spec.solution, expected)
    starter = report["starter"] = run_checks(spec, spec.starter, expected)

    if solution.get("error"):
        report["problems"].append(f"Эталонное решение: {solution['error']}")
    failed = [r["name"] for r in solution.get("results", []) if not r["passed"]]
    if failed:
        report["problems"].append(f"Эталонное решение не проходит: {', '.join(failed)}.")
    if not solution.get("results") and not solution.get("error"):
        report["problems"].append("Проверки не нашлись — убедитесь, что тесты объявлены через test(...) / def test_...")
    if _all_passed(starter):
        report["problems"].append("Стартовый код уже проходит все проверки — задание получится пустым.")
    return report


def verify_task(db: Session, version_id: int) -> dict:
    version = db.scalar(select(TaskVersion).where(TaskVersion.id == version_id))
    if version is None:
        raise ValueError("Версия задания не найдена")
    checked = spec_hash(version.spec)
    try:
        report = verify(TaskSpec.model_validate(version.spec))
    except Exception as exc:
        # Статус не должен навсегда остаться «в очереди» — админ увидит причину
        report = {"problems": [f"Проверка не запустилась: {type(exc).__name__}: {exc}"], "checked_at": datetime.now(UTC).isoformat()}
    version.check_report = report
    version.checked_hash = checked
    version.check_status = CheckStatus.failed if report["problems"] else CheckStatus.passed
    db.commit()
    return {"passed": not report["problems"], "problems": report["problems"]}
