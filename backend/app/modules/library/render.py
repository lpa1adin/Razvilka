"""Markdown → безопасный HTML. Очистка делается здесь, на сервере, один раз при импорте."""

import html
import re

import nh3
from markdown_it import MarkdownIt

_md = MarkdownIt("commonmark", {"html": True}).enable("table").enable("strikethrough")

_TAGS = {
    "p", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "a", "code", "pre", "em", "strong", "b", "i",
    "blockquote", "table", "thead", "tbody", "tr", "th", "td", "img", "br", "hr", "kbd", "dl", "dt", "dd",
    "sup", "sub", "del", "s", "span", "div", "figure", "figcaption", "details", "summary", "abbr", "var",
    "samp", "mark", "caption",
}
_ATTRS = {
    "a": {"href", "title"},
    "img": {"src", "alt", "title", "width", "height"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan", "scope"},
    "code": {"class"},  # language-css и т.п. — для подсветки
    "abbr": {"title"},
}


def render_markdown(text: str) -> str:
    raw = _md.render(text)
    # h1 у статьи — это заголовок страницы платформы; внутри текста поднимаем всё на уровень ниже
    raw = re.sub(r"<(/?)h1>", r"<\1h2>", raw)
    clean = nh3.clean(
        raw,
        tags=_TAGS,
        attributes=_ATTRS,
        url_schemes={"http", "https", "mailto"},
        link_rel="noopener noreferrer nofollow",
        clean_content_tags={"script", "style"},
    )
    return clean.replace("<img ", '<img loading="lazy" ')


def html_to_text(fragment_html: str) -> str:
    text = html.unescape(nh3.clean(fragment_html, tags=set()))
    return re.sub(r"\s+", " ", text).strip()


def first_paragraph(fragment_html: str, limit: int = 280) -> str:
    for match in re.finditer(r"<p>(.*?)</p>", fragment_html, flags=re.S):
        text = html_to_text(match.group(1))
        if len(text) > 40:
            return text if len(text) <= limit else text[: limit - 1].rsplit(" ", 1)[0] + "…"
    return ""


def markdown_outline(text: str, levels: tuple[int, ...] = (2, 3)) -> list[dict]:
    """Заголовки статьи: [{'level': 2, 'title': '...'}]. Строки внутри блоков кода не считаются."""
    tokens = _md.parse(text)
    outline = []
    for i, token in enumerate(tokens):
        if token.type == "heading_open" and int(token.tag[1]) in levels:
            title = html_to_text(_md.renderInline(tokens[i + 1].content))
            if title:
                outline.append({"level": int(token.tag[1]), "title": title})
    return outline
