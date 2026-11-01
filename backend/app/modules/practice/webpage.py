"""Сборка страницы веб-задания для проверки. Та же логика есть в интерфейсе
(frontend/src/features/practice/webPage.ts) — менять оба места вместе; тест test_practice проверяет пример."""

import json
import re
from pathlib import Path

HARNESS = (Path(__file__).parent / "harness" / "web_harness.js").read_text(encoding="utf-8")
WIDTHS = (1280, 768, 375)

# Ссылки на собственные файлы задания убираем: их содержимое встраивается прямо в страницу
_OWN_CSS = re.compile(r"<link\b[^>]*href=[\"']\.?/?style\.css[\"'][^>]*>", re.I)
_OWN_JS = re.compile(r"<script\b[^>]*src=[\"']\.?/?script\.js[\"'][^>]*>\s*</script>", re.I)


def _inline(code: str, tag: str) -> str:
    return re.sub(f"</{tag}", f"<\\\\/{tag}", code, flags=re.I)


def build_page(files: dict[str, str], tests: str, width: int, mode: str, harness: str = HARNESS) -> str:
    html = _OWN_JS.sub("", _OWN_CSS.sub("", files.get("index.html", "")))
    head = (
        f"<style>{_inline(files.get('style.css', ''), 'style')}</style>"
        f"<script>window.__rzMode={json.dumps(mode)};window.__rzWidth={int(width)};\n{harness}\n"
        f"{_inline(tests, 'script') if mode == 'check' else ''}</script>"
    )
    tail = f"<script>{_inline(files.get('script.js', ''), 'script')}</script>"

    match = re.search(r"</head>", html, re.I)
    html = html[: match.start()] + head + html[match.start():] if match else head + html
    matches = list(re.finditer(r"</body>", html, re.I))
    return html[: matches[-1].start()] + tail + html[matches[-1].start():] if matches else html + tail


# ---------- Сдача проекта (этап 6): страница из файлов проекта по их настоящим путям ----------

_LINK = re.compile(r"<link\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>", re.I)
_SCRIPT = re.compile(r"<script\b([^>]*)src=[\"']([^\"']+)[\"']([^>]*)>\s*</script>", re.I)


def _resolve(entry: str, href: str) -> str:
    """Относительная ссылка из entry → путь файла в сдаче."""
    if re.match(r"^(https?:)?//|^data:", href):
        return ""
    href = href.split("?")[0].split("#")[0]
    parts = [] if href.startswith("/") else entry.split("/")[:-1]
    for piece in href.lstrip("/").split("/"):
        if piece in ("", "."):
            continue
        if piece == "..":
            parts = parts[:-1]
        else:
            parts.append(piece)
    return "/".join(parts)


def build_project_page(files: dict[str, str], entry: str, tests: str, width: int) -> str:
    """Свои стили и скрипты встраиваются по ссылкам из HTML (в том числе библиотеки из vendor), внешние —
    вырезаются: у runner нет сети. Харнесс и тесты практикума — перед скриптами страницы."""
    html = files.get(entry, "")

    def css(match: re.Match) -> str:
        tag = match.group(0)
        path = _resolve(entry, match.group(1))
        if "stylesheet" not in tag.lower() or path not in files:
            return "" if "stylesheet" in tag.lower() else tag
        return f"<style>{_inline(files[path], 'style')}</style>"

    def js(match: re.Match) -> str:
        path = _resolve(entry, match.group(2))
        if path not in files:
            return ""
        module = ' type="module"' if "module" in (match.group(1) + match.group(3)) else ""
        return f"<script{module}>{_inline(files[path], 'script')}</script>"

    html = _SCRIPT.sub(js, _LINK.sub(css, html))
    head = f"<script>window.__rzMode=\"check\";window.__rzWidth={int(width)};\n{HARNESS}\n{_inline(tests, 'script')}</script>"
    match = re.search(r"<head[^>]*>", html, re.I)
    return html[: match.end()] + head + html[match.end():] if match else head + html


# Проверки, которые есть у любой сданной страницы — как правило WEB-03 Ревьюера
BASE_WEB_TESTS = """
test('Страница открывается без горизонтальной прокрутки на телефоне', { width: 375 }, () => {
  expect(document.documentElement.scrollWidth <= 376, `Ширина страницы ${document.documentElement.scrollWidth} px при экране 375 px`)
})
test('У страницы есть заголовок <title> и мета viewport', () => {
  expect(document.title.trim(), 'Нет <title>')
  expect(document.querySelector('meta[name="viewport"]'), 'Нет <meta name="viewport"> — на телефоне страница будет мелкой')
})
"""
