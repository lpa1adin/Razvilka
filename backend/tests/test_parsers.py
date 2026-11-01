from app.modules.library.parsers import parse_jsinfo, parse_mdn

MDN = r"""---
title: Flexbox
slug: Learn_web_development/Core/CSS_layout/Flexbox
---

{{LearnSidebar}}{{PreviousMenuNext("A", "B", "C")}}

Элемент {{htmlelement("header")}} и свойство {{cssxref("flex-direction")}}, см. {{Glossary("CSS", "каскадные таблицы")}}.
Ссылка на [Введение](/ru/docs/Learn/HTML) и картинка ![схема](flex.png), ![оси](gone.png), ![](gone2.png).

<p><img src="pic.png" alt="есть"><img src="nope.png" alt="нет"></p>

<script>alert(1)</script><a href="javascript:alert(1)">клик</a>

> [!NOTE]
> Можно и в обратном направлении.

- пункт списка

   > [!WARNING]
   > Осторожно.

```html
<h1>\{{ book.title }}</h1>
```

## Почему Flexbox?

```css
section { display: flex; }
```
"""


def test_mdn_macros_links_and_images_are_rewritten():
    folder = "files/ru/learn_web_development/core/css_layout/flexbox"
    article = parse_mdn(f"{folder}/index.md", MDN, "https://raw/abc/", existing={f"{folder}/index.md", f"{folder}/flex.png", f"{folder}/pic.png"})
    html = article.content_html
    assert article.title == "Flexbox"
    assert article.url == "https://developer.mozilla.org/ru/docs/Learn_web_development/Core/CSS_layout/Flexbox"
    assert "LearnSidebar" not in html and "PreviousMenuNext" not in html
    assert 'href="https://developer.mozilla.org/ru/docs/Web/HTML/Element/header"' in html
    assert "<code>&lt;header&gt;</code>" in html
    assert ">каскадные таблицы</a>" in html
    assert 'href="https://developer.mozilla.org/ru/docs/Learn/HTML"' in html
    assert 'src="https://raw/abc/files/ru/learn_web_development/core/css_layout/flexbox/flex.png"' in html
    assert "gone.png" not in html and "gone2.png" not in html and "nope.png" not in html
    assert f'src="https://raw/abc/{folder}/pic.png"' in html
    assert "<em>Иллюстрация: оси</em>" in html
    assert "<strong>Примечание.</strong>" in html
    assert "<strong>Внимание.</strong>" in html and "[!WARNING]" not in html
    assert "{{ book.title }}" in html and "\\{{" not in html
    assert article.outline == [{"level": 2, "title": "Почему Flexbox?"}]
    assert article.parent_key == "files/ru/learn_web_development/core/css_layout"


def test_mdn_html_is_sanitized():
    html = parse_mdn("files/ru/x/index.md", MDN, "https://raw/").content_html
    assert "<script" not in html and "alert(1)</script" not in html
    assert "javascript:" not in html
    assert 'rel="noopener noreferrer nofollow"' in html


JSINFO = """# Привет, мир!

В этой части учебника мы изучаем собственно JavaScript.

## Тег «script»

```js
## это не заголовок
```

[smart header="Подсказка"]
текст
[/smart]

### Современная разметка
"""


def test_jsinfo_keeps_only_outline_and_link():
    article = parse_jsinfo("1-js/02-first-steps/01-hello-world/article.md", JSINFO)
    assert article.title == "Привет, мир!"
    assert article.url == "https://learn.javascript.ru/hello-world"
    assert article.content_html is None  # текст статьи не сохраняем — только ссылка (лицензия)
    assert [o["title"] for o in article.outline] == ["Тег «script»", "Современная разметка"]
    assert "собственно JavaScript" not in article.plain_text
    assert article.parent_key == "1-js/02-first-steps"
