"""Разбор статей конкретных источников. Каждый парсер получает путь и текст файла, отдаёт Article."""

import re
from dataclasses import dataclass, field

import yaml

from app.modules.library.render import first_paragraph, html_to_text, markdown_outline, render_markdown

MDN_BASE = "https://developer.mozilla.org/ru/docs/"


@dataclass
class Article:
    external_id: str
    title: str
    url: str
    parent_key: str  # по нему потом находим название раздела
    section: str = ""
    content_html: str | None = None
    outline: list[dict] = field(default_factory=list)
    excerpt: str = ""
    plain_text: str = ""


# ---------- MDN ----------

# \{{ … }} — экранирование в MDN: так пишут шаблоны Django/Jinja в примерах, это не макрос
_MACRO = re.compile(r"(?<!\\)\{\{\s*([A-Za-z_][\w-]*)\s*(?:\((.*?)\))?\s*\}\}", re.S)
_ARG = re.compile(r"\"([^\"]*)\"|'([^']*)'|(-?\d+)")

# Навигация, сайдбары, живые примеры и таблицы совместимости — в платформе они не работают
_DROP = {
    "previousmenunext", "previousnext", "previousmenu", "nextmenu", "previous", "next", "embedlivesample",
    "embedghlivesample", "embedinteractiveexample", "interactiveexample", "specifications", "compat",
    "quicklinkswithsubpages", "listsubpages", "listsubpagesforsidebar", "seecompattable", "deprecated_header",
    "non-standard_header", "securecontext_header", "availableinworkers", "draft", "outdated",
    "translationinprogress", "embedyoutube", "page", "livesamplelink", "todo", "js_property_attributes",
    "optional_inline", "readonlyinline", "deprecated_inline", "experimental_inline", "non-standard_inline",
    "experimental_header", "securecontext_inline", "jsref", "cssref", "htmlref", "apiref", "inheritancediagram",
}

_LINK_MACROS = {
    "htmlelement": ("Web/HTML/Element/{}", "`<{}>`"),
    "cssxref": ("Web/CSS/{}", "`{}`"),
    "jsxref": ("Web/JavaScript/Reference/Global_Objects/{}", "`{}`"),
    "domxref": ("Web/API/{}", "`{}`"),
    "glossary": ("Glossary/{}", "{}"),
    "httpheader": ("Web/HTTP/Headers/{}", "`{}`"),
    "httpstatus": ("Web/HTTP/Status/{}", "`{}`"),
    "httpmethod": ("Web/HTTP/Methods/{}", "`{}`"),
    "svgelement": ("Web/SVG/Element/{}", "`<{}>`"),
}

_CALLOUTS = {"NOTE": "Примечание.", "WARNING": "Внимание.", "CALLOUT": ""}


def _macro_args(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [a or b or c for a, b, c in _ARG.findall(raw)]


def _replace_macro(match: re.Match) -> str:
    name = match.group(1).lower()
    args = _macro_args(match.group(2))
    if name in _DROP or name.endswith("sidebar"):
        return ""
    if name in _LINK_MACROS and args:
        path, label = _LINK_MACROS[name]
        target = args[0]
        text = args[1] if len(args) > 1 and args[1] else label.format(target)
        if name == "domxref":
            target = target.replace("()", "").replace(".", "/")
        return f"[{text}]({MDN_BASE}{path.format(target.replace(' ', '_'))})"
    if name == "rfc" and args:
        return f"[RFC {args[0]}](https://datatracker.ietf.org/doc/html/rfc{args[0]})"
    if name == "htmlattrxref" and args:
        return f"`{args[0]}`"
    if args:
        # неизвестный макрос с подписью: показываем подпись, без неё — само значение как код
        return args[1] if len(args) > 1 and args[1] else f"`{args[0]}`"
    return ""


def _image(alt: str, src: str, directory: str, image_base: str, existing: set[str] | None) -> str:
    if src.startswith(("http://", "https://")):
        return f"![{alt}]({src})"
    path = f"{directory}/{src}"
    if existing is not None and path not in existing:
        # В переводе часто остаются ссылки на картинки, которых уже нет ни в репозитории, ни на сайте MDN
        return f"*Иллюстрация: {alt}*" if alt.strip() else ""
    return f"![{alt}]({image_base}{path})"


def _fix_html_images(html: str, directory: str, image_base: str, existing: set[str] | None) -> str:
    """То же для <img>, написанных прямо HTML-тегом внутри статьи."""

    def fix(match: re.Match) -> str:
        src = match.group(2)
        if src.startswith(("http://", "https://")):
            return match.group(0)
        path = f"{directory}/{src}"
        if existing is not None and path not in existing:
            return ""
        return f"{match.group(1)}{image_base}{path}{match.group(3)}"

    return re.sub(r'(<img\b[^>]*\bsrc=")([^"]+)("[^>]*>)', fix, html)


def _mdn_markdown(body: str, directory: str, image_base: str, existing: set[str] | None) -> str:
    body = _MACRO.sub(_replace_macro, body).replace("\\{{", "{{")
    body = re.sub(r"\]\(/(?=[a-zA-Z-]+/docs/)", "](https://developer.mozilla.org/", body)
    body = re.sub(r'href="/(?=[a-zA-Z-]+/docs/)', 'href="https://developer.mozilla.org/', body)
    # картинки лежат рядом со статьёй в репозитории — берём их оттуда, если они там есть
    body = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)", lambda m: _image(m.group(1), m.group(2), directory, image_base, existing), body)
    body = re.sub(
        r"^([ \t]*)>\s*\[!(NOTE|WARNING|CALLOUT)\]\s*$",  # врезки бывают и с отступом — внутри списков
        lambda m: f"{m.group(1)}> **{_CALLOUTS[m.group(2)]}**" if _CALLOUTS[m.group(2)] else f"{m.group(1)}>",
        body,
        flags=re.M,
    )
    return body


def parse_mdn(path: str, text: str, raw_base: str, existing: set[str] | None = None) -> Article | None:
    """existing — пути файлов в репозитории; None — не проверять, есть ли картинки."""
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not match:
        return None
    meta = yaml.safe_load(match.group(1)) or {}
    title, slug = meta.get("title"), meta.get("slug")
    if not title or not slug:
        return None
    directory = path.rsplit("/", 1)[0]
    body = _mdn_markdown(match.group(2), directory, raw_base, existing)
    content_html = _fix_html_images(render_markdown(body), directory, raw_base, existing)
    return Article(
        external_id=path,
        title=str(title),
        url=MDN_BASE + slug,
        parent_key=directory.rsplit("/", 1)[0],
        content_html=content_html,
        outline=markdown_outline(body),
        excerpt=first_paragraph(content_html),
        plain_text=html_to_text(content_html),
    )


# ---------- learn.javascript.ru ----------

_JS_MARKUP = re.compile(r"\[(?:/?(?:cut|smart|warn|info|online|summary|recent|iframe|edit|codetabs|compare)[^\]]*)\]")


def _jsinfo_title(text: str) -> str | None:
    for line in text.splitlines():
        if line.startswith("# "):
            return _JS_MARKUP.sub("", line[2:]).strip()
    return None


def parse_jsinfo(path: str, text: str) -> Article | None:
    title = _jsinfo_title(text)
    if not title:
        return None
    directory = path.rsplit("/", 1)[0]
    slug = re.sub(r"^\d+-", "", directory.rsplit("/", 1)[-1])
    outline = markdown_outline(_JS_MARKUP.sub("", text))
    # Режим «только ссылка»: текст статьи не сохраняем, ищем по названию и оглавлению
    return Article(
        external_id=path,
        title=title,
        url=f"https://learn.javascript.ru/{slug}",
        parent_key=directory.rsplit("/", 1)[0],
        outline=outline,
        plain_text=" ".join(item["title"] for item in outline),
    )


def jsinfo_section_title(text: str) -> str | None:
    return _jsinfo_title(text)
