"""Автотесты сданного проекта — шаг 1 конвейера, выполняется в runner (без интернета, с лимитами)."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from app.modules.practice.runner import TIMEOUT, _limits
from app.modules.practice.webpage import BASE_WEB_TESTS, WIDTHS, build_project_page

PROJECT_HARNESS = Path(__file__).resolve().parent.parent / "practice" / "harness" / "project_harness.py"


def run_python(files: dict[str, str], tests: str) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        for path, text in files.items():
            target = Path(tmp, path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        try:
            proc = subprocess.run(
                [sys.executable, "-I", str(PROJECT_HARNESS), tmp],
                input=tests, capture_output=True, text=True, timeout=TIMEOUT * 2, cwd=tmp,
                env={"PATH": "/usr/bin:/bin", "HOME": tmp, "LANG": "C.UTF-8"}, preexec_fn=_limits,
            )
        except subprocess.TimeoutExpired:
            return {"results": [], "error": f"Тесты выполнялись дольше {TIMEOUT * 2} с — возможно, бесконечный цикл"}
    if not proc.stdout.strip():
        return {"results": [], "error": f"Тесты не запустились: {proc.stderr.strip()[-500:] or 'нет ответа'}"}
    return json.loads(proc.stdout.strip().splitlines()[-1])


def entry_page(files: dict[str, str]) -> str | None:
    if "index.html" in files:
        return "index.html"
    pages = sorted((p for p in files if p.endswith(".html")), key=lambda p: (p.count("/"), p))
    return pages[0] if pages else None


def run_web(files: dict[str, str], tests: str) -> dict:
    from playwright.sync_api import sync_playwright  # есть только в образе runner

    entry = entry_page(files)
    if entry is None:
        return {"results": [], "error": "В сдаче нет HTML-страницы — открывать нечего."}
    results, errors = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--disable-dev-shm-usage"])
        try:
            context = browser.new_context()
            context.route("**/*", lambda route: route.abort())  # картинки и CDN не грузятся — runner без сети
            for width in WIDTHS:
                page = context.new_page()
                page.set_viewport_size({"width": width, "height": 900})
                page.set_content(build_project_page(files, entry, BASE_WEB_TESTS + "\n" + tests, width), wait_until="load", timeout=15_000)
                page.wait_for_function("window.__rzResults", timeout=TIMEOUT * 1000)
                data = page.evaluate("window.__rzResults")
                page.close()
                results += data["results"]
                errors += [e for e in data["errors"] if e not in errors]
        finally:
            browser.close()
    return {"results": results, "error": f"Ошибки в скриптах страницы: {'; '.join(errors[:5])}" if errors else None, "entry": entry}


def run(kind: str, files: dict[str, str], tests: str) -> dict:
    outcome = run_python(files, tests) if kind == "python" else run_web(files, tests)
    outcome["passed"] = not outcome.get("error") and bool(outcome.get("results")) and all(r["passed"] for r in outcome["results"])
    return outcome
