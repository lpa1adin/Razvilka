"""Белый список источников. Добавить источник можно только здесь, в коде, — не через интерфейс.

Лицензии проверены вручную 2026-10-31 по файлам LICENSE.md в репозиториях. При каждом импорте
сборщик сверяет файл лицензии с прошлым разом; если он изменился — импорт останавливается
до проверки админом (Мастерская → Источники).
"""

from dataclasses import dataclass

from app.modules.library.models import LicenseMode


@dataclass(frozen=True)
class SourceSpec:
    slug: str
    title: str
    author: str
    kind: str
    homepage: str
    license_name: str
    license_url: str
    license_mode: LicenseMode
    license_note: str
    repo: str
    # шаблоны sparse-checkout (gitignore-синтаксис): берём только нужные файлы, без картинок
    patterns: tuple[str, ...]
    license_file: str
    # строка, которая обязана быть в файле лицензии; нет её — значит, лицензию поменяли
    license_marker: str
    parser: str  # mdn | jsinfo | owasp | pydocs


SOURCES: dict[str, SourceSpec] = {
    spec.slug: spec
    for spec in (
        SourceSpec(
            slug="mdn-ru",
            title="MDN Web Docs (русская версия)",
            author="Участники MDN, Mozilla",
            kind="docs",
            homepage="https://developer.mozilla.org/ru/",
            license_name="CC BY-SA 2.5",
            license_url="https://creativecommons.org/licenses/by-sa/2.5/deed.ru",
            license_mode=LicenseMode.full_text,
            license_note=(
                "Текст показан полностью с указанием авторов. Изменения: служебные макросы MDN заменены "
                "текстом и ссылками, интерактивные примеры убраны. Адаптация распространяется на тех же условиях (CC BY-SA 2.5)."
            ),
            repo="https://github.com/mdn/translated-content",
            patterns=(
                "/LICENSE.md",
                "/files/ru/learn_web_development/**/index.md",
                "/files/ru/web/html/**/index.md",
                "/files/ru/web/javascript/guide/**/index.md",
            ),
            license_file="LICENSE.md",
            license_marker="CC-BY-SA 2.5",
            parser="mdn",
        ),
        SourceSpec(
            slug="learnjs-ru",
            title="Современный учебник JavaScript (learn.javascript.ru)",
            author="Илья Кантор и участники",
            kind="tutorial",
            homepage="https://learn.javascript.ru/",
            license_name="CC BY-NC 4.0 (с оговорками автора)",
            license_url="https://github.com/javascript-tutorial/ru.javascript.info/blob/master/LICENSE.md",
            license_mode=LicenseMode.reference,
            license_note=(
                "Автор разрешает свободно читать учебник, а для любого другого использования просит связаться "
                "с ним (iliakan@javascript.info). Поэтому здесь только оглавление статьи и ссылка — читайте в оригинале."
            ),
            repo="https://github.com/javascript-tutorial/ru.javascript.info",
            patterns=(
                "/LICENSE.md",
                "/1-js/**/article.md",
                "/1-js/**/index.md",
                "/2-ui/**/article.md",
                "/2-ui/**/index.md",
            ),
            license_file="LICENSE.md",
            license_marker="CC-BY-NC",
            parser="jsinfo",
        ),
        SourceSpec(
            slug="owasp-cheatsheets",
            title="OWASP Cheat Sheet Series",
            author="OWASP Foundation и участники",
            kind="docs",
            homepage="https://cheatsheetseries.owasp.org/",
            license_name="CC BY-SA 4.0",
            license_url="https://creativecommons.org/licenses/by-sa/4.0/deed.ru",
            license_mode=LicenseMode.full_text,
            license_note=(
                "Текст показан полностью, на английском, с указанием авторов. Изменения: ссылки на соседние шпаргалки "
                "ведут на сайт OWASP. Адаптация распространяется на тех же условиях (CC BY-SA 4.0)."
            ),
            repo="https://github.com/OWASP/CheatSheetSeries",
            patterns=("/LICENSE.md", "/cheatsheets/*.md"),
            license_file="LICENSE.md",
            license_marker="Attribution-ShareAlike 4.0",
            parser="owasp",
        ),
        SourceSpec(
            slug="python-docs",
            title="Документация Python (docs.python.org)",
            author="Python Software Foundation",
            kind="docs",
            homepage="https://docs.python.org/3/",
            license_name="PSF License Version 2 (примеры кода — Zero-Clause BSD)",
            license_url="https://docs.python.org/3/license.html",
            license_mode=LicenseMode.full_text,
            license_note=(
                "Официальная документация Python, на английском, текст полностью. Изменения: роли и директивы Sphinx "
                "заменены обычным текстом и блоками кода, служебные индексы убраны. © Python Software Foundation."
            ),
            repo="https://github.com/python/cpython",
            patterns=("/LICENSE", "/Doc/tutorial/*.rst", "/Doc/library/*.rst", "/Doc/howto/*.rst"),
            license_file="LICENSE",
            license_marker="Python Software Foundation License Version 2",
            parser="pydocs",
        ),
    )
}
