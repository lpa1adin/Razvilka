"""Адреса содержимого: карта курса и чтение/запись одной ячейки без выгрузки всего курса.

Нужны, чтобы правка вида «измени блок 4 урока 2.3 курса 7» стоила два-три коротких вызова
(`app.cli map`, `show`, `set`), а не чтения всего JSON курса. Модель не вызывается.

Адреса:
  7                      курс (карта)
  7/2.3                  урок 3 модуля 2;  .../title, .../goal — его поля
  7/2.3/4                блок 4 урока;     .../why — заметка к теории; остальное уходит в то, на что блок ссылается
  task:28                задание;          /title /statement /tests /sql_setup /hints /hints/2 /starter/<файл> /solution/<файл>
  quiz:5                 банк вопросов;    /12 — вопрос с id 12 (JSON)
  fragment:123           статья библиотеки (только чтение); /text — текст целиком
"""

import copy
import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.auth.models import Role, User
from app.modules.courses import service as courses
from app.modules.courses.models import Course
from app.modules.courses.schemas import CourseContent, DraftIn
from app.modules.library.models import Fragment
from app.modules.practice import service as practice
from app.modules.practice.models import Task
from app.modules.practice.schemas import TaskDraftIn, TaskSpec
from app.modules.quiz.models import Question, QuizTopic
from app.modules.quiz.schemas import QuestionIn

KINDS = {"theory": "теория", "practice": "практика", "quiz": "тест"}
TASK_TEXT = ("title", "statement", "tests", "sql_setup")
PREVIEW = 3000


class CellError(Exception):
    """Понятное сообщение для того, кто набрал адрес."""


def _size(text: str) -> str:
    return f"{len(text)} симв."


def _num(part: str, what: str) -> int:
    if not part.isdigit() or int(part) < 1:
        raise CellError(f"{what}: ждали номер, а пришло «{part}»")
    return int(part)


def _pick(items: list, number: int, what: str):
    if number > len(items):
        raise CellError(f"{what} {number} нет: всего {len(items)}")
    return items[number - 1]


def _get(db: Session, model, ident: int, what: str):
    row = db.get(model, ident)
    if row is None:
        raise CellError(f"{what} #{ident} не найдено")
    return row


def _admin(db: Session) -> User:
    admin = db.scalars(select(User).where(User.role == Role.admin).order_by(User.id)).first()
    if admin is None:
        raise CellError("Нет ни одного админа: черновик создать некому")
    return admin


def _state(row) -> str:
    if row.draft_version and row.published_version:
        return "опубл.+черновик"
    return "черновик" if row.draft_version else "опубл."


# ---------- карта ----------


def _target(db: Session, block: dict) -> str:
    if block["type"] == "theory":
        row = db.execute(
            select(Fragment.title, func.length(Fragment.plain_text)).where(Fragment.id == block["fragment_id"])
        ).first()
        return f"fragment:{block['fragment_id']} " + (f"«{row[0]}» ({row[1]} симв.)" if row else "— нет в библиотеке")
    if block["type"] == "practice":
        task = db.get(Task, block["task_id"])
        if task is None:
            return f"task:{block['task_id']} — нет такого задания"
        version = practice.editing_version(db, task)
        return f"task:{task.id} «{version.spec.get('title', '')}» [{_state(task)}, проверка {version.check_status.value}]"
    topic = db.get(QuizTopic, block["topic_id"])
    if topic is None:
        return f"quiz:{block['topic_id']} — нет такого банка"
    count = db.scalar(select(func.count()).select_from(Question).where(Question.topic_id == topic.id))
    return f"quiz:{topic.id} «{topic.title}» ({count} вопр.)"


def course_list(db: Session) -> str:
    lines = []
    for course in db.scalars(select(Course).order_by(Course.id)).all():
        version = courses.editing_version(db, course)
        modules = version.content.get("modules", [])
        lessons = sum(len(m["lessons"]) for m in modules)
        lines.append(f"{course.id} «{version.title}» [{_state(course)}] модулей {len(modules)}, уроков {lessons}")
    return "\n".join(lines) or "Курсов нет"


def course_map(db: Session, course_id: int) -> str:
    course = _get(db, Course, course_id, "Курс")
    version = courses.editing_version(db, course)
    lines = [f"Курс {course.id} «{version.title}» [{_state(course)}], версия {version.number}"]
    for mi, module in enumerate(version.content.get("modules", []), 1):
        lines.append(f"{course.id}/{mi} Модуль «{module['title']}»")
        for li, lesson in enumerate(module["lessons"], 1):
            lines.append(f"  {course.id}/{mi}.{li} Урок «{lesson['title']}»")
            for bi, block in enumerate(lesson.get("blocks", []), 1):
                lines.append(f"    {course.id}/{mi}.{li}/{bi} {KINDS[block['type']]} {_target(db, block)}")
    return "\n".join(lines)


def _usage(db: Session, key: str, ident: int) -> list[str]:
    """Обратные связи: в каких уроках стоит задание или банк вопросов."""
    found = []
    for course in db.scalars(select(Course).order_by(Course.id)).all():
        content = courses.editing_version(db, course).content
        for mi, module in enumerate(content.get("modules", []), 1):
            for li, lesson in enumerate(module["lessons"], 1):
                for bi, block in enumerate(lesson.get("blocks", []), 1):
                    if block.get(key) == ident:
                        found.append(f"{course.id}/{mi}.{li}/{bi}")
    return found


# ---------- разбор адреса ----------


def _lesson(db: Session, course_part: str, lesson_part: str):
    course = _get(db, Course, _num(course_part, "Курс"), "Курс")
    version = courses.editing_version(db, course)
    # Копия: правка JSONB на месте не замечается SQLAlchemy, и черновик молча не сохранится
    content = copy.deepcopy(version.content)
    module_no, _, lesson_no = lesson_part.partition(".")
    if not lesson_no:
        raise CellError(f"Урок задаётся как «модуль.урок», например {course.id}/2.3")
    module = _pick(content.get("modules", []), _num(module_no, "Модуль"), "Модуля")
    lesson = _pick(module["lessons"], _num(lesson_no, "Урок"), "Урока")
    return course, version, content, lesson


def _resolve(db: Session, address: str) -> tuple[str, int, list[str]]:
    """Адрес блока сводится к тому, на что блок ссылается: ('task', 28, ['tests'])."""
    parts = [p for p in address.strip().strip("/").split("/") if p]
    if not parts:
        raise CellError("Пустой адрес")
    head = parts[0]
    if ":" in head:
        kind, _, ident = head.partition(":")
        if kind not in ("task", "quiz", "fragment"):
            raise CellError(f"Не знаю «{kind}:» — есть task:, quiz:, fragment:")
        return kind, _num(ident, kind), parts[1:]
    if len(parts) < 3 or not parts[2].isdigit():
        return "course", _num(head, "Курс"), parts[1:]
    *_, lesson = _lesson(db, head, parts[1])
    block = _pick(lesson.get("blocks", []), int(parts[2]), "Блока")
    rest = parts[3:]
    if block["type"] == "theory":
        if rest == ["why"]:
            return "course", int(head), parts[1:]
        return "fragment", block["fragment_id"], rest
    if block["type"] == "practice":
        return "task", block["task_id"], rest
    return "quiz", block["topic_id"], rest


# ---------- чтение ----------


def _show_course(db: Session, course_id: int, rest: list[str]) -> str:
    if not rest:
        return course_map(db, course_id)
    *_, lesson = _lesson(db, str(course_id), rest[0])
    if len(rest) == 1:
        lines = [f"Урок «{lesson['title']}»", f"Цель: {lesson.get('goal', '') or '—'}"]
        for bi, block in enumerate(lesson.get("blocks", []), 1):
            lines.append(f"  {course_id}/{rest[0]}/{bi} {KINDS[block['type']]} {_target(db, block)}")
        return "\n".join(lines)
    if len(rest) == 2 and rest[1] in ("title", "goal"):
        return lesson.get(rest[1], "")
    if len(rest) == 3 and rest[2] == "why":
        return _pick(lesson.get("blocks", []), _num(rest[1], "Блок"), "Блока").get("why", "")
    raise CellError("У урока есть поля title и goal, у блока теории — why")


def _task_field(spec: dict, rest: list[str]):
    name = rest[0]
    if name in TASK_TEXT and len(rest) == 1:
        return spec.get(name, "")
    if name == "hints":
        hints = spec.get("hints", [])
        if len(rest) == 1:
            return "\n".join(f"{i}. {h}" for i, h in enumerate(hints, 1))
        return _pick(hints, _num(rest[1], "Подсказка"), "Подсказки")
    if name in ("starter", "solution") and len(rest) == 2:
        files = spec.get(name, {})
        if rest[1] not in files:
            raise CellError(f"В {name} нет файла {rest[1]}; есть: {sorted(files) or 'ничего'}")
        return files[rest[1]]
    raise CellError("Поля задания: title, statement, tests, sql_setup, hints, hints/N, starter/<файл>, solution/<файл>")


def _show_task(db: Session, task_id: int, rest: list[str]) -> str:
    task = _get(db, Task, task_id, "Задание")
    version = practice.editing_version(db, task)
    spec = version.spec
    if rest:
        return _task_field(spec, rest)
    lines = [
        f"Задание {task.id} «{spec.get('title', '')}» [{_state(task)}], вид {spec['kind']}, "
        f"версия {version.number}, проверка {version.check_status.value}",
        f"Стоит в уроках: {', '.join(_usage(db, 'task_id', task.id)) or 'нигде'}",
        f"  task:{task.id}/statement  {_size(spec.get('statement', ''))}",
    ]
    for part in ("starter", "solution"):
        for name, code in spec.get(part, {}).items():
            lines.append(f"  task:{task.id}/{part}/{name}  {_size(code)}")
    for name in ("tests", "sql_setup"):
        if spec.get(name):
            lines.append(f"  task:{task.id}/{name}  {_size(spec[name])}")
    lines.append(f"  task:{task.id}/hints  {len(spec.get('hints', []))} шт.")
    if spec.get("sql_checks"):
        lines.append(f"  SQL-проверок: {len(spec['sql_checks'])} (правятся в редакторе задания)")
    if spec.get("fragment_ids"):
        lines.append("  теория: " + ", ".join(f"fragment:{i}" for i in spec["fragment_ids"]))
    return "\n".join(lines)


def _question(db: Session, topic_id: int, part: str) -> Question:
    question = db.get(Question, _num(part, "Вопрос"))
    if question is None or question.topic_id != topic_id:
        raise CellError(f"В банке {topic_id} нет вопроса {part}")
    return question


def _question_json(question: Question) -> str:
    data = {name: getattr(question, name) for name in QuestionIn.model_fields}
    return json.dumps(QuestionIn.model_validate(data).model_dump(mode="json"), ensure_ascii=False, indent=2)


def _show_quiz(db: Session, topic_id: int, rest: list[str]) -> str:
    topic = _get(db, QuizTopic, topic_id, "Банк вопросов")
    if rest:
        return _question_json(_question(db, topic.id, rest[0]))
    lines = [
        f"Банк {topic.id} «{topic.title}» [{'опубл.' if topic.published else 'черновик'}], в тесте {topic.size} вопр.",
        f"Стоит в уроках: {', '.join(_usage(db, 'topic_id', topic.id)) or 'нигде'}",
    ]
    for q in db.scalars(select(Question).where(Question.topic_id == topic.id).order_by(Question.id)).all():
        prompt = " ".join(q.prompt.split())
        lines.append(f"  quiz:{topic.id}/{q.id} [{q.type.value}, {q.status.value}, сложн. {q.difficulty}] {prompt[:90]}")
    return "\n".join(lines)


def _show_fragment(db: Session, fragment_id: int, rest: list[str], full: bool) -> str:
    fragment = _get(db, Fragment, fragment_id, "Статья")
    text = fragment.plain_text or fragment.excerpt
    if rest == ["text"] or full:
        return text
    if rest:
        raise CellError("У статьи одно поле: text")
    lines = [f"Статья {fragment.id} «{fragment.title}» ({_size(text)}), раздел «{fragment.section}»", fragment.url]
    if fragment.outline:
        lines.append("Разделы: " + "; ".join(str(h.get("title", h)) if isinstance(h, dict) else str(h) for h in fragment.outline))
    lines.append(text[:PREVIEW])
    if len(text) > PREVIEW:
        lines.append(f"… показано {PREVIEW} из {len(text)} симв.; целиком: fragment:{fragment.id}/text")
    return "\n".join(lines)


def show(db: Session, address: str, full: bool = False) -> str:
    kind, ident, rest = _resolve(db, address)
    if kind == "course":
        return _show_course(db, ident, rest)
    if kind == "task":
        return _show_task(db, ident, rest)
    if kind == "quiz":
        return _show_quiz(db, ident, rest)
    return _show_fragment(db, ident, rest, full)


# ---------- запись ----------


def _set_course(db: Session, course_id: int, rest: list[str], value: str) -> str:
    if not rest:
        raise CellError("Что менять? Например 7/2.3/goal")
    course = _get(db, Course, course_id, "Курс")
    note = ""
    if not course.draft_version:
        courses.start_draft(db, course, _admin(db))
        note = " (создан черновик; опубликованная версия не тронута)"
    course, version, content, lesson = _lesson(db, str(course_id), rest[0])
    value = value.strip()
    if len(rest) == 2 and rest[1] in ("title", "goal"):
        lesson[rest[1]] = value
    elif len(rest) == 3 and rest[2] == "why":
        block = _pick(lesson.get("blocks", []), _num(rest[1], "Блок"), "Блока")
        if block["type"] != "theory":
            raise CellError("Заметка why есть только у блока теории")
        block["why"] = value
    else:
        raise CellError("В курсе меняются: <урок>/title, <урок>/goal, <урок>/<блок теории>/why")
    payload = DraftIn(
        number=version.number, title=version.title, description=version.description,
        content=CourseContent.model_validate(content),
    )
    courses.save_draft(db, course, payload)
    return f"Сохранено в черновике курса {course.id}, версия {version.number}{note}"


def _set_task(db: Session, task_id: int, rest: list[str], value: str, check: bool) -> str:
    if not rest:
        raise CellError("Что менять? Например task:28/tests")
    task = _get(db, Task, task_id, "Задание")
    note = ""
    if not task.draft_version:
        practice.start_draft(db, task, _admin(db))
        note = " (создан черновик; опубликованная версия не тронута)"
    version = practice.editing_version(db, task)
    spec = json.loads(json.dumps(version.spec))
    name = rest[0]
    if name in TASK_TEXT and len(rest) == 1:
        spec[name] = value.strip() if name == "title" else value
    elif name == "hints" and len(rest) == 2:
        hints = spec.setdefault("hints", [])
        number = _num(rest[1], "Подсказка")
        if number == len(hints) + 1:
            hints.append(value.strip())
        else:
            _pick(hints, number, "Подсказки")
            hints[number - 1] = value.strip()
    elif name in ("starter", "solution") and len(rest) == 2:
        spec.setdefault(name, {})[rest[1]] = value
    else:
        raise CellError("В задании меняются: title, statement, tests, sql_setup, hints/N, starter/<файл>, solution/<файл>")
    practice.save_draft(db, task, TaskDraftIn(number=version.number, spec=TaskSpec.model_validate(spec)))
    result = f"Сохранено в черновике задания {task.id}, версия {version.number}{note}"
    if check:
        try:
            practice.request_check(db, task)
            result += "; автопроверка поставлена в очередь (бесплатно), итог — в show task:" + str(task.id)
        except practice.TaskError as exc:
            result += f"; автопроверка не запущена: {exc}"
    return result


def _set_quiz(db: Session, topic_id: int, rest: list[str], value: str) -> str:
    if len(rest) != 1:
        raise CellError("В банке меняется один вопрос целиком: quiz:5/12, значение — JSON как в show")
    question = _question(db, topic_id, rest[0])
    try:
        data = QuestionIn.model_validate(json.loads(value))
    except json.JSONDecodeError as exc:
        raise CellError(f"Это не JSON: {exc}") from exc
    for field, new in data.model_dump().items():
        setattr(question, field, new)
    db.commit()
    return f"Вопрос {question.id} банка {topic_id} сохранён"


def set_cell(db: Session, address: str, value: str, check: bool = True) -> str:
    kind, ident, rest = _resolve(db, address)
    try:
        if kind == "course":
            return _set_course(db, ident, rest, value)
        if kind == "task":
            return _set_task(db, ident, rest, value, check)
        if kind == "quiz":
            return _set_quiz(db, ident, rest, value)
    except (ValueError, courses.CourseError, practice.TaskError) as exc:
        if isinstance(exc, CellError):
            raise
        db.rollback()
        raise CellError(f"Не сохранено: {exc}") from exc
    raise CellError("Статьи библиотеки приходят из источников и здесь не правятся")
