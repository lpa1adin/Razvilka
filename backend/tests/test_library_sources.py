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
