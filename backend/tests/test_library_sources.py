"""Новые источники библиотеки (OWASP, документация Python) и источники правил Ревьюера."""

from pathlib import Path

from app.modules.library import parsers
from app.modules.review.service import DEFAULT_RULES, parse_rules

PYDOC = """\
:mod:`!json` --- JSON encoder and decoder
=========================================

.. module:: json
   :synopsis: Encode and decode the JSON format.

**Source code:** :source:`Lib/json/__init__.py`

`JSON (JavaScript Object Notation) <https://json.org>`_, specified by :rfc:`7159`.

.. function:: dumps(obj, *, skipkeys=False, \\
                    indent=None)

   Serialize *obj* to a JSON formatted :class:`str` using :ref:`this table <py-to-json-table>`.

   .. versionchanged:: 3.6
      All optional parameters are now keyword-only.

Basic usage::

   >>> import json
   >>> json.dumps([1, 2])
   '[1, 2]'

Command line
------------

.. code-block:: shell-session

   $ python -m json --help

.. index:: single: JSON
"""

OWASP = """\
# SQL Injection Prevention Cheat Sheet

## Introduction

See the [Injection Prevention Cheat Sheet](Injection_Prevention_Cheat_Sheet.md#intro) and ![diagram](../assets/sqli.png).
"""


def test_pydocs_parser_turns_sphinx_into_plain_html():
    a = parsers.parse_pydocs("Doc/library/json.rst", PYDOC)
    assert a.title == "json --- JSON encoder and decoder"
    assert a.url == "https://docs.python.org/3/library/json.html" and a.section == "Стандартная библиотека"
    assert "RFC 7159" in a.plain_text and "dumps(obj, *, skipkeys=False, indent=None)" in a.plain_text
    assert "Изменено в версии 3.6" in a.plain_text and "<code>str</code>" in a.content_html
    assert "python -m json --help" in a.content_html and "json.dumps([1, 2])" in a.content_html
    assert {"level": 2, "title": "Command line"} in a.outline
    assert "<script" not in a.content_html and "single: JSON" not in a.plain_text
    assert parsers.parse_pydocs("Doc/library/index.rst", PYDOC) is None


def test_owasp_parser_links_to_site():
    a = parsers.parse_owasp("cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.md", OWASP, "https://raw.example/")
    assert a.title == "SQL Injection Prevention Cheat Sheet"
    assert a.url == "https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html"
    assert 'href="https://cheatsheetseries.owasp.org/cheatsheets/Injection_Prevention_Cheat_Sheet.html#intro"' in a.content_html
    assert 'src="https://raw.example/assets/sqli.png"' in a.content_html
    assert a.section == "OWASP Cheat Sheet Series"


def test_every_reviewer_rule_has_a_source():
    rules = parse_rules(Path(DEFAULT_RULES).read_text())
    assert len(rules) >= 24 and "TEST-02" in {r.id for r in rules}
    missing = [r.id for r in rules if not r.source.startswith("[")]
    assert missing == [], missing
    sec02 = next(r for r in rules if r.id == "SEC-02")
    assert sec02.text == "SQL — только параметризованные запросы или ORM."
    assert "SQL_Injection_Prevention_Cheat_Sheet" in sec02.source


REACT = """---
title: Условный рендеринг
---

<Intro>

Компоненты показывают разное в зависимости от условий.

</Intro>

## Условный возврат JSX {/*conditionally-returning-jsx*/}

<Sandpack>

```js
export default function Item({ name }) {
  return <li>{name}</li>;
}
```

</Sandpack>

<Pitfall>

Не ставьте числа слева от `&&`.

</Pitfall>

<Recipes titleText="Примеры состояния" titleId="ex">
"""

FASTAPI = """# Path-параметры { #path-parameters }

Параметры пути:

{* ../../docs_src/path_params/tutorial001_py310.py hl[6:7] *}

/// tip | Подсказка

Это даёт поддержку редактора.

///

## С типами { #with-types }
"""


def test_react_parser_strips_site_components():
    a = parsers.parse_react("src/content/learn/conditional-rendering.md", REACT)
    assert a.title == "Условный рендеринг" and a.url == "https://ru.react.dev/learn/conditional-rendering"
    assert a.section == "Изучение React" and {"level": 2, "title": "Условный возврат JSX"} in a.outline
    assert "Sandpack" not in a.content_html and "{/*" not in a.content_html
    assert "&lt;li&gt;{name}&lt;/li&gt;" in a.content_html  # JSX в коде экранирован, а не выкинут
    assert "<strong>Подводный камень.</strong>" in a.content_html and "Примеры состояния" in a.plain_text
    assert parsers.parse_react("src/content/learn/index.md", REACT).url == "https://ru.react.dev/learn"


def test_fastapi_parser_inlines_code_from_repo():
    files = {"docs_src/path_params/tutorial001_py310.py": "from fastapi import FastAPI\n\napp = FastAPI()\n"}
    a = parsers.parse_fastapi("docs/ru/docs/tutorial/path-params.md", FASTAPI, files.get)
    assert a.title == "Path-параметры" and a.url == "https://fastapi.tiangolo.com/ru/tutorial/path-params/"
    assert a.section == "Учебник FastAPI" and {"level": 2, "title": "С типами"} in a.outline
    assert "app = FastAPI()" in a.content_html and "{*" not in a.content_html
    assert "<blockquote>" in a.content_html and "Подсказка." in a.plain_text and "///" not in a.plain_text
    missing = parsers.parse_fastapi("docs/ru/docs/tutorial/path-params.md", FASTAPI, lambda _: None)
    assert "Пример кода: tutorial001_py310.py" in missing.plain_text
