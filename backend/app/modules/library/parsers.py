"""Разбор статей конкретных источников. Каждый парсер получает путь и текст файла, отдаёт Article."""

import re
from dataclasses import dataclass, field

import yaml
from docutils.core import publish_parts
from docutils.parsers.rst import Directive, directives, nodes

from app.modules.library.render import first_paragraph, html_outline, html_to_text, markdown_outline, render_markdown, sanitize_html

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



# ---------- OWASP Cheat Sheet Series ----------

OWASP_BASE = "https://cheatsheetseries.owasp.org/cheatsheets/"


def parse_owasp(path: str, text: str, raw_base: str) -> Article | None:
    lines = text.splitlines()
    head = next((i for i, l in enumerate(lines) if l.startswith("# ")), None)
    if head is None:
        return None
    title = lines[head][2:].strip()
    body = "\n".join(lines[head + 1:])
    name = path.rsplit("/", 1)[-1].removesuffix(".md")
    # Ссылки на соседние шпаргалки ведут на сайт OWASP, картинки — в репозиторий
    body = re.sub(r"\]\((?!https?:|#|mailto:)([\w.-]+)\.md(#[^)]*)?\)", lambda m: f"]({OWASP_BASE}{m.group(1)}.html{m.group(2) or ''})", body)
    body = re.sub(r"!\[([^\]]*)\]\((?!https?:)(?:\.\./)?([^)\s]+)\)", lambda m: f"![{m.group(1)}]({raw_base}{m.group(2)})", body)
    content_html = render_markdown(body)
    return Article(
        external_id=path,
        title=title,
        url=f"{OWASP_BASE}{name}.html",
        parent_key="cheatsheets",
        section="OWASP Cheat Sheet Series",
        content_html=content_html,
        outline=markdown_outline(body),
        excerpt=first_paragraph(content_html),
        plain_text=html_to_text(content_html),
    )


# ---------- Документация Python (reST + директивы Sphinx) ----------

PYDOCS_BASE = "https://docs.python.org/3/"
PYDOCS_SECTIONS = {"tutorial": "Учебник Python", "library": "Стандартная библиотека", "howto": "Python HOWTO"}

# :func:`json.dumps`, :class:`~pathlib.Path`, :ref:`текст <метка>` — роли Sphinx, которых docutils не знает
_ROLE = re.compile(r":(?:[\w-]+:)?([\w-]+):`([^`]+)`")
_PLAIN_ROLES = {"ref", "term", "doc", "pep", "rfc", "abbr", "dfn", "title", "manpage", "gh", "issue", "source"}


def _role(match: re.Match) -> str:
    name, text = match.group(1), match.group(2).strip()
    if text.endswith(">") and "<" in text:
        shown = text[: text.rindex("<")].strip()
        text = shown or text[text.rindex("<") + 1 : -1]
    text = text.lstrip("!")
    if text.startswith("~"):
        text = text[1:].rsplit(".", 1)[-1]
    if name in ("pep", "rfc"):
        return f"{name.upper()} {text}"
    return text if name in _PLAIN_ROLES else f"``{text}``"


class _AnyOptions(dict):
    """Директивы Sphinx бывают с любыми опциями (:noindex:, :module:…) — принимаем все, не разбирая."""

    def __getitem__(self, key):
        return directives.unchanged

    def __contains__(self, key):
        return True


class _Sphinx(Directive):
    has_content = True
    optional_arguments = 1
    final_argument_whitespace = True
    option_spec = _AnyOptions()
    LABELS = {"versionadded": "Добавлено в версии", "versionchanged": "Изменено в версии", "deprecated": "Устарело с версии",
              "seealso": "См. также", "impl-detail": "Деталь реализации CPython", "availability": "Доступность"}
    SIGNATURES = {"function", "method", "class", "attribute", "data", "exception", "decorator", "describe", "envvar",
                  "option", "cmdoption", "opcode", "classmethod", "staticmethod", "property", "coroutinefunction",
                  "coroutinemethod", "abstractmethod", "decoratormethod", "type"}
    CODE = {"code-block", "sourcecode", "testcode", "doctest", "testoutput", "productionlist"}

    def run(self):
        name, arg = self.name, (self.arguments[0] if self.arguments else "")
        body = nodes.container()
        if self.content and name not in self.CODE:
            self.state.nested_parse(self.content, self.content_offset, body)
        if name in self.CODE:
            text = "\n".join(self.content) if name != "productionlist" else arg + "\n" + "\n".join(self.content)
            return [nodes.literal_block(text, text)] if text.strip() else []
        if name in self.SIGNATURES:
            arg = re.sub(r"\s*\\\s*", " ", arg)  # длинные сигнатуры переносят строку обратным слэшем
            head = nodes.paragraph("", "", nodes.strong("", "", nodes.literal(arg, arg)))
            return [head, nodes.block_quote("", *body.children)]
        if name in self.LABELS:
            label = f"{self.LABELS[name]} {arg}".strip() if name not in ("seealso", "impl-detail") else self.LABELS[name]
            return [nodes.paragraph("", "", nodes.emphasis(label + ".", label + ".")), *body.children]
        return list(body.children)  # прочее (only, rubric-подобные) — просто содержимое


_HIDDEN = ("index", "toctree", "highlight", "currentmodule", "module", "moduleauthor", "sectionauthor", "testsetup",
           "testcleanup", "tabularcolumns", "audit-event", "audit-event-table", "c:function", "c:macro", "c:type",
           "c:member", "c:var", "program", "literalinclude", "include", "raw", "miscnews", "limited-api-list")


class _Hidden(Directive):
    has_content = True
    optional_arguments = 1
    final_argument_whitespace = True
    option_spec = _AnyOptions()

    def run(self):
        return []


for _name in (*_Sphinx.SIGNATURES, *_Sphinx.LABELS, *_Sphinx.CODE, "only", "versionremoved", "glossary"):
    directives.register_directive(_name, _Sphinx)
for _name in _HIDDEN:
    directives.register_directive(_name, _Hidden)

_SETTINGS = {
    "report_level": 5, "halt_level": 5, "file_insertion_enabled": False, "raw_enabled": False,
    "syntax_highlight": "none", "input_encoding": "unicode", "doctitle_xform": True, "initial_header_level": 2,
}


def parse_pydocs(path: str, text: str) -> Article | None:
    """Doc/library/json.rst → статья. Роли и директивы Sphinx упрощаются до обычного текста и кода."""
    rel = path.removeprefix("Doc/").removesuffix(".rst")
    if rel.endswith("index") or rel.rsplit("/", 1)[-1].startswith("_"):
        return None
    source = _ROLE.sub(_role, text).replace("|version|", "3").replace("|release|", "3")
    try:
        parts = publish_parts(source, writer="html5", settings_overrides=_SETTINGS)
    except Exception:  # одна сломанная страница не должна останавливать импорт всей документации
        return None
    title = html_to_text(parts.get("title", "")).replace("``", "").strip()
    if not title:
        return None
    raw = parts["body"].replace('<span class="docutils literal">', "<code>")
    raw = re.sub(r"<code>(.*?)</span>", r"<code>\1</code>", raw, flags=re.S)
    # Схемы документации лежат рядом с .rst в виде svg — относительные ссылки на них здесь не откроются
    raw = re.sub(r'<img\b(?![^>]*\bsrc="https?:)[^>]*>', "", raw)
    content_html = sanitize_html(raw)
    return Article(
        external_id=path,
        title=title,
        url=f"{PYDOCS_BASE}{rel}.html",
        parent_key=rel.split("/", 1)[0],
        section=PYDOCS_SECTIONS.get(rel.split("/", 1)[0], ""),
        content_html=content_html,
        outline=html_outline(content_html),
        excerpt=first_paragraph(content_html),
        plain_text=html_to_text(content_html),
    )
