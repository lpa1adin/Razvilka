"""Инструменты агента для библиотеки: найти статью и посмотреть, о чём она.

Теорию Claude не пишет (BRIEF §3.1) — он выбирает существующие фрагменты по id. Поэтому инструменты отдают
название, источник, оглавление и начало текста, а не предлагают «пересказать своими словами».
"""

from claude_agent_sdk import create_sdk_mcp_server, tool

from app.core.db import SessionLocal
from app.modules.library.models import FragmentStatus, LicenseMode
from app.modules.library.service import get_fragment, search
from app.modules.projectmap import cache
from app.modules.projectmap.graph import outline

LIBRARY_TOOLS = ["mcp__library__library_search", "mcp__library__library_fragment"]
PROJECT_TOOLS = ["mcp__project__project_map", "mcp__project__project_file"]


def _text(value: str) -> dict:
    return {"content": [{"type": "text", "text": value}]}


@tool(
    "library_search",
    "Поиск статей в библиотеке теории платформы (MDN, learn.javascript.ru). Запрос на русском, 1–4 слова. "
    "Возвращает id, название, источник и короткую выдержку. Используй id в ответе — других статей не бывает.",
    {"query": str},
)
async def library_search(args: dict) -> dict:
    with SessionLocal() as db:
        found = search(db, str(args.get("query", "")), None, 8, 0)
    if not found.items:
        return _text("Ничего не нашлось. Попробуйте другие слова: короче или синоним.")
    lines = [
        f"#{f.id} «{f.title}» — {f.source.title}{f' / {f.section}' if f.section else ''}. {f.excerpt[:220]}"
        for f in found.items
    ]
    return _text("\n".join(lines))


@tool(
    "library_fragment",
    "Оглавление и начало статьи из библиотеки по id — чтобы понять, что в ней разобрано.",
    {"id": int},
)
async def library_fragment(args: dict) -> dict:
    with SessionLocal() as db:
        fragment = get_fragment(db, int(args.get("id", 0)))
        if fragment is None or fragment.status is not FragmentStatus.active:
            return _text("Такой статьи нет в библиотеке.")
        headings = "; ".join(h.get("title", "") for h in fragment.outline[:30]) or "—"
        # Для источников, которые разрешают только ссылку, полного текста нет и здесь
        body = fragment.plain_text[:3000] if fragment.source.license_mode is LicenseMode.full_text else fragment.excerpt
        return _text(
            f"#{fragment.id} «{fragment.title}» — {fragment.source.title}\nРазделы: {headings}\n\n{body}"
        )


def library_server():
    return create_sdk_mcp_server("library", tools=[library_search, library_fragment])


def project_server(root: str):
    """Граф проекта для агента (скилл project-graph): карта целиком и оглавление одного файла."""

    @tool("project_map", "Граф проекта: файлы, связи, каркас страниц, классы, функции. Начинать работу с проектом с него.", {})
    async def project_map(_args: dict) -> dict:
        return _text(cache.render_map(root))

    @tool(
        "project_file",
        "Подробное оглавление одного файла проекта (все функции, классы, селекторы, медиазапросы) — дешевле, чем Read.",
        {"path": str},
    )
    async def project_file(args: dict) -> dict:
        return _text(outline(root, str(args.get("path", ""))))

    return create_sdk_mcp_server("project", tools=[project_map, project_file])
