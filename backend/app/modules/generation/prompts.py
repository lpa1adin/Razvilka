"""Инструкции наставнику для Мастерской. Примеры формата заданий берутся из seed — тех же заданий,
что уже прошли автопроверку, поэтому Claude видит рабочий образец, а не описание «на словах»."""

import json
from pathlib import Path

SEED = Path(__file__).resolve().parent.parent / "practice" / "seed"
LEVELS = {1: "новичок: знает основы HTML/CSS", 2: "средний: делал свои сайты", 3: "продвинутый: уверенно пишет код"}
WHAT = {"course": "курс", "task": "набор практических заданий", "quiz": "банк вопросов для теста", "path": "путь «напиши заново сам»"}

RULES = """\
Ты — наставник учебной платформы «Развилка». Ученик учится разработке на практике, часто на своих же проектах.

Жёсткие правила:
1. Теорию ты НЕ пишешь. Теория — только статьи библиотеки платформы. Найди их инструментом library_search,
   проверь содержание через library_fragment и ссылайся только на найденные id. Если подходящей статьи нет —
   так и напиши в summary/notes, не выдумывай id.
2. Проект владельца доступен только на чтение. Работай по скиллу project-graph: карта проекта уже в задании,
   оглавление файла — project_file, Read — только за точными строками кода. Не читай проект целиком и не
   открывай библиотеки. Опирайся на реальные файлы, классы и функции из графа, не придумывай несуществующие.
3. Всё на русском. Тон — спокойный, конкретный, без воды.
4. Ответ — строго по JSON-схеме, без пояснений вне неё.
"""


def plan_prompt(req, previous: dict | None, feedback: str | None, project_map: str = "") -> tuple[str, str]:
    source = (
        f"Проект: папка «{req.project}» (текущая папка){f', часть: {req.focus}' if req.focus else ''}."
        if req.project else "Без проекта — тема из заявки."
    )
    task = [
        f"Составь план: {WHAT[req.what.value]}.",
        source,
        f"Тема: {req.topic}" if req.topic else "",
        f"Уровень ученика: {LEVELS[req.level]}.",
        f"Пожелания админа: {req.notes}" if req.notes else "",
        "",
        "Как строить план:",
        "- Устройство проекта — по карте ниже; файл целиком читай, только если без точной цитаты не обойтись.",
        "- Модули и уроки идут от простого к сложному. В уроке одна мысль; files — файлы проекта, на которых он построен.",
        "- Для каждого урока подбери 1–3 статьи библиотеки (fragment_ids).",
        "- practice — задание, которое проверяется автотестами в браузере (web), на Python или SQL. Не каждому уроку оно нужно.",
        "- quiz — сколько вопросов по теории урока (0–15). Вопросы модуля — банк его теста: тест берёт 5–10 случайных,",
        "  поэтому в модуле с теорией в сумме 20–50 вопросов. Модулю без теории (только практика) тест не нужен — 0.",
    ]
    if req.what.value == "task":
        task.append("- Нужны только практические задания: один модуль, у каждого урока есть practice, quiz = 0.")
    if req.what.value == "quiz":
        task.append("- Нужен только банк вопросов: один модуль, уроки = подтемы, practice нет, quiz 5–15 на подтему, всего 20–50.")
    if req.what.value == "path":
        task += [
            "- Это путь «напиши заново сам» (BRIEF §5.5): ученик пишет этот проект сам с пустой папки, по этапам.",
            "- Один модуль; уроки = этапы, 3–6 штук, от пустой папки до готового проекта. Каждый этап — работающий",
            "  промежуточный результат (страница открывается), следующий строится поверх предыдущего.",
            "- files — какие файлы ученик создаёт или дополняет на этапе (пути как в проекте).",
            "- forks — 1–2 развилки этапа: решения, которые автор принимал (раскладка, структура файлов, подключение",
            "  библиотеки, адаптив…). Только вопрос и контекст, без ответа автора. practice = null, quiz = 0.",
            "- roles — роль каждой важной части проекта (файлы и папки из карты), коротко.",
        ]
    if project_map:
        task += ["", project_map]
    if previous:
        task += ["", "Текущий план (его нужно переделать):", json.dumps(previous, ensure_ascii=False)]
    if feedback:
        task += ["", f"Что поменять по просьбе админа: {feedback}"]
    return RULES, "\n".join(line for line in task if line is not None)


def _example(name: str, keys: tuple[str, ...]) -> str:
    data = json.loads((SEED / name).read_text())
    return json.dumps({k: data[k] for k in keys if k in data}, ensure_ascii=False)


TASK_FORMAT = f"""\
Формат практического задания (task):
- statement — условие в markdown: что сделать, по пунктам, как проверят.
- starter — стартовые файлы ученика, solution — эталонное решение. Файлы: web — index.html, style.css, script.js;
  python — main.py; sql — query.sql.
- Автопроверка обязательна: эталон проходит ВСЕ тесты, стартовый код НЕ проходит (иначе задание пустое).
- hints — 2–3 подсказки по нарастающей: от направления к конкретному шагу, без готового кода целиком.

web: tests — JavaScript. API: test('Название', () => {{ expect(условие, 'что не так') }}),
test('Название', {{ width: 375 }}, () => {{...}}) — ширины 375 / 768 / 1280 (по умолчанию 1280),
$(css), $$(css) — массив, style(el, 'свойство') — вычисленный стиль, click(el), await wait(ms).
Пример (прошёл проверку): {_example("header.json", ("kind", "statement", "starter", "solution", "tests", "hints"))}

python: tests — pytest-подобные функции test_*, первая строка docstring — название проверки; импорт из main.
Пример: {_example("slug.json", ("kind", "statement", "starter", "solution", "tests", "hints"))}

sql: sql_setup — схема и данные (SQLite), sql_checks — проверки: same_result (результат совпадает с эталоном,
order_matters) или assert (sql возвращает истину после кода ученика).
Пример: {_example("routes_sql.json", ("kind", "statement", "starter", "solution", "sql_setup", "sql_checks", "hints"))}
"""

QUESTION_FORMAT = """\
Формат вопросов (questions):
- type: single (один ответ), multiple (несколько, засчитывается точный набор), order (порядок шагов),
  match (сопоставление). single/multiple/order: options.items; match: options.left (2–6) и options.right (2–8).
- answer: single/multiple — correct: [id]; order — order: [все id по порядку]; match — pairs: {id слева: id справа}.
- id вариантов — короткие латинские: a, b, c… У single ровно один верный ответ.
- Вопрос проверяет понимание, а не память на мелочи. Можно дать код (code, code_lang) — «что выведет», «найди ошибку».
- explanation — почему верен именно этот ответ, 1–3 предложения.
- fragment_id — статья урока, где разобран ответ. Спрашивай только о том, что в этих статьях есть.
- Код в вариантах оборачивай в `обратные кавычки`.
"""


def lesson_prompt(
    req, plan: dict, module: dict, lesson: dict, fragments: list[str], instruction: str | None, files_outline: str = "",
    reviewer_rules: str = "",
) -> tuple[str, str]:
    outline = "\n".join(
        f"{m['title']}: " + "; ".join(l["title"] for l in m["lessons"]) for m in plan["modules"]
    )
    parts = [
        f"Напиши черновик урока для «{plan['title']}» ({WHAT[req.what.value]}). Уровень ученика: {LEVELS[req.level]}.",
        f"Весь план:\n{outline}",
        "",
        f"Модуль «{module['title']}», урок «{lesson['title']}».",
        f"Цель урока: {lesson['goal']}",
        f"Файлы проекта: {', '.join(lesson.get('files') or []) or '—'}" if req.project else "",
        f"Оглавление этих файлов (из графа проекта):\n{files_outline}" if files_outline else "",
        "Статьи урока (уже выбраны в плане; можно добавить другие из library_search):",
        *[f"- {f}" for f in fragments],
        "",
        "Что нужно:",
        "- theory: статьи урока с пояснением, зачем читать каждую именно здесь.",
    ]
    practice = lesson.get("practice")
    if practice:
        parts.append(f"- task: задание вида {practice['kind']}. Идея из плана: {practice['idea']}")
        parts.append(TASK_FORMAT)
        if reviewer_rules:
            parts += [
                "Эталон (solution) потом проверит независимый Ревьюер по правилам ниже; для эталона любое нарушение — "
                "минимум major. Пиши эталон сразу так, чтобы замечаний не было: граничные случаи (пусто, null/None, 0, "
                "неверный тип), без необработанных исключений на реалистичном вводе, понятные имена, без лишнего.",
                reviewer_rules,
            ]
    else:
        parts.append("- task: null — в этом уроке практики нет.")
    if lesson.get("quiz"):
        parts.append(f"- questions: ровно {lesson['quiz']} вопросов разной сложности (difficulty 1–3).")
        parts.append(QUESTION_FORMAT)
    else:
        parts.append("- questions: пустой список.")
    if instruction:
        parts += ["", f"Это переделка урока. Просьба админа: {instruction}"]
    return RULES, "\n".join(parts)


def fix_prompt(task: dict, problems: list[str]) -> tuple[str, str]:
    return RULES, "\n".join([
        "Автопроверка практического задания не прошла. Исправь задание так, чтобы эталон проходил все тесты,",
        "а стартовый код — нет. Смысл задания не меняй.",
        "",
        "Что нашла проверка:",
        *[f"- {p}" for p in problems],
        "",
        "Задание сейчас:",
        json.dumps(task, ensure_ascii=False),
        "",
        TASK_FORMAT,
    ])


def quiz_topup_prompt(topic: str, count: int, fragments: list[str], existing: list[str]) -> tuple[str, str]:
    return RULES, "\n".join([
        f"Допиши {count} новых вопросов в банк теста «{topic}». Тест берёт из банка случайные вопросы, поэтому",
        "банк должен быть разнообразным: разные стороны темы, типы вопросов и сложность (difficulty 1–3).",
        "Статьи темы (спрашивай только о том, что в них есть; читай через library_fragment):",
        *[f"- {f}" for f in fragments],
        "",
        "Уже есть в банке — не повторяй их ни по смыслу, ни перефразом:",
        *[f"- {p}" for p in existing],
        "",
        QUESTION_FORMAT,
    ])


def review_fix_prompt(task: dict, findings: list[dict], reviewer_rules: str) -> tuple[str, str]:
    return RULES, "\n".join([
        "Независимый Ревьюер проверил ЭТАЛОН практического задания и его автотесты и нашёл замечания. Исправь эталон",
        "(solution) и тесты (tests) так, чтобы этих замечаний не осталось. Смысл задания не меняй.",
        "- Применится только solution и tests. Тесты можно добавлять и уточнять, но не удалять и не переименовывать.",
        "- Условие (statement), стартовый код (starter) и подсказки (hints) не подгоняй под код: если без их правки",
        "  никак не обойтись, внеси её — она уйдёт админу на одобрение и до этого не применится.",
        "- Эталон обязан проходить все тесты, стартовый код — нет. Поменял поведение на граничном случае — добавь тест.",
        "",
        "Замечания Ревьюера:",
        *[
            f"- [{f['severity']}] {f['rule']} {f['file']}:{f.get('line') or '—'} — {f['problem']} "
            f"Когда сломается: {f['scenario']} Куда смотреть: {f['fix_hint']}"
            for f in findings
        ],
        "",
        "Правила Ревьюера (для эталона любое нарушение — минимум major; не создай новых нарушений):",
        reviewer_rules,
        "",
        "Задание сейчас:",
        json.dumps(task, ensure_ascii=False),
        "",
        TASK_FORMAT,
    ])


STAGE_TESTS = {
    "web": """\
Автотесты этапа — JavaScript, выполняются на странице ученика (index.html со встроенными CSS и JS) на ширинах
1280, 768, 375. API: test('Название', () => { expect(условие, 'что не так') }), test('Название', { width: 375 }, () => {...}),
$(css), $$(css) — массив, style(el, 'свойство'), click(el), await wait(ms).
Проверяй результат этапа (структуру, классы, раскладку, адаптив), а не конкретный текст или пиксели: ученик пишет
сам и может отличаться в деталях. Тесты обязаны проходить на оригинальном проекте целиком (он — эталон) и падать
на пустой папке. Внешние ресурсы недоступны (нет сети): шрифты и картинки не проверяй.""",
    "python": """\
Автотесты этапа — функции test_* на Python, первая строка docstring — название проверки; модули ученика
импортируются из его папки. Тесты обязаны проходить на оригинальном проекте и падать на пустой папке.""",
}


def stage_prompt(req, plan: dict, stage: dict, n: int, kind: str, files_outline: str, fragments: list[str], instruction: str | None) -> tuple[str, str]:
    outline = "\n".join(f"{i}. {l['title']}: {l['goal']}" for i, l in enumerate(plan["modules"][0]["lessons"], 1))
    forks = "\n".join(f"- {f['question']} ({f.get('context', '')})" for f in stage.get("forks", [])) or "—"
    parts = [
        f"Напиши этап {n} пути «напиши заново сам» по проекту «{req.project}». Уровень ученика: {LEVELS[req.level]}.",
        f"Все этапы:\n{outline}",
        "",
        f"Этап {n}: {stage['title']}. Цель: {stage['goal']}",
        f"Файлы этапа: {', '.join(stage.get('files') or []) or '—'}",
        f"Оглавление этих файлов в оригинале:\n{files_outline}" if files_outline else "",
        "Статьи к этапу: " + ("; ".join(fragments) or "—"),
        "",
        "Что нужно:",
        "- statement — условие: что сделать в своей рабочей папке, по пунктам; без готового кода автора.",
        "- forks — развилки этапа из плана с ответом автора (reference): что выбрал автор и почему, со ссылкой на файлы.",
        f"Развилки из плана:\n{forks}",
        STAGE_TESTS[kind],
    ]
    if instruction:
        parts += ["", f"Это переделка этапа. Просьба админа: {instruction}"]
    return RULES, "\n".join(p for p in parts if p)


def stage_fix_prompt(tests: str, problems: list[str], kind: str) -> tuple[str, str]:
    return RULES, "\n".join([
        "Автотесты этапа не прошли автопроверку: на оригинальном проекте они должны проходить, на пустой папке — падать.",
        "Исправь тесты, не меняя смысла этапа. Если проверка слишком привязана к деталям (точный текст, пиксели) — ослабь её.",
        "", "Что нашла проверка:", *[f"- {p}" for p in problems], "", "Тесты сейчас:", tests, "", STAGE_TESTS[kind],
    ])
