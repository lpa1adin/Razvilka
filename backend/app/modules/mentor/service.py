"""Чат-помощник (BRIEF §5.7). Отвечает по уроку или заданию, наводит на решение, готовое решение не выдаёт.

API кладёт вопрос в очередь `chat`, agent-worker дописывает ответ в базу по кусочкам, а браузер читает
их потоком (SSE). Так ответ виден по мере генерации, а токен Claude есть только у воркера.
"""

import time

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.agent import claude
from app.modules.auth.models import User
from app.modules.courses import service as courses
from app.modules.jobs.queue import enqueue
from app.modules.mentor.models import MentorMessage, MentorThread, MessageStatus
from app.modules.practice import service as practice
from app.modules.practice.models import TaskAttempt
from app.modules.practice.schemas import Code, TaskSpec

HISTORY = 14  # сколько последних сообщений видит наставник
FLUSH_SECONDS = 0.3

SYSTEM = """\
Ты — наставник учебной платформы «Развилка». Ученик спрашивает тебя по текущему уроку или заданию.

Как отвечать:
- По-русски, коротко и по делу: 2–6 предложений или короткий список. Markdown: **жирный**, `код`, списки,
  блоки кода с ```. Длинные лекции не нужны.
- Объясняй и наводи, а не решай за ученика. ГОТОВОЕ РЕШЕНИЕ ЗАДАНИЯ НЕ ВЫДАВАЙ: ни целиком, ни по частям,
  даже если очень просят. Можно показать общий приём на другом, небольшом примере.
- Теорию не пересказывай своими словами как источник — отправляй к статьям урока. Ссылка на статью:
  [Название](/library/ID). Другие статьи ищи через library_search; ссылайся только на найденные id.
- Если ученик просит создать курс, задание или тест — объясни, что их создаёт администратор, и предложи
  кнопку «Предложить тему» внизу панели: заявка уйдёт админу в Мастерскую.
- Если вопрос не про учёбу — мягко верни к уроку.

Подсказки по заданию идут по нарастающей (номер подсказки указан в сообщении):
1 — направление: какое понятие нужно и где о нём прочитать;
2 — где именно в коде ученика проблема и почему;
3 и дальше — конкретный следующий шаг словами, можно 1–2 строки кода, но не всё решение.
"""


class MentorUnavailable(Exception):
    pass


class MessageIn(BaseModel):
    context_kind: str = Field(pattern="^(lesson|task|general)$")
    context_ref: str = Field("", max_length=200)
    text: str = Field("", max_length=4000)
    hint: bool = False
    files: dict[str, Code] | None = None  # код из редактора — даже если ещё не сохранился


def thread_for(db: Session, user: User, kind: str, ref: str, create: bool = False) -> MentorThread | None:
    thread = db.scalar(select(MentorThread).where(
        MentorThread.user_id == user.id, MentorThread.context_kind == kind, MentorThread.context_ref == ref,
    ))
    if thread is None and create:
        thread = MentorThread(user_id=user.id, context_kind=kind, context_ref=ref)
        db.add(thread)
        db.flush()
    return thread


def messages(db: Session, thread: MentorThread | None) -> list[MentorMessage]:
    if thread is None:
        return []
    return list(db.scalars(select(MentorMessage).where(MentorMessage.thread_id == thread.id).order_by(MentorMessage.id)))


def _task(db: Session, ref: str):
    task = practice.visible_task(db, ref, None)
    if task is None:
        raise MentorUnavailable("Задание не найдено или снято с публикации")
    return task


def _check_context(db: Session, user: User, kind: str, ref: str) -> None:
    if kind == "task":
        _task(db, ref)
    elif kind == "lesson":
        slug, _, lesson_id = ref.partition("/")
        course = courses.visible_course(db, slug, user, None)
        if course is None or courses.lesson_detail(db, user, course, lesson_id, None) is None:
            raise MentorUnavailable("Урок не найден")


def send(db: Session, user: User, payload: MessageIn) -> MentorMessage:
    if not claude.configured():
        raise MentorUnavailable(
            "Наставник не подключён: администратор ещё не добавил токен Claude. Уроки, тесты и песочница работают без него."
        )
    if payload.hint and payload.context_kind != "task":
        raise MentorUnavailable("Подсказки бывают только в задании")
    if not payload.text.strip() and not payload.hint:
        raise MentorUnavailable("Напишите вопрос")
    _check_context(db, user, payload.context_kind, payload.context_ref)
    thread = thread_for(db, user, payload.context_kind, payload.context_ref, create=True)
    busy = db.scalar(select(MentorMessage.id).where(
        MentorMessage.thread_id == thread.id,
        MentorMessage.status.in_([MessageStatus.pending, MessageStatus.streaming]),
    ))
    if busy:
        raise MentorUnavailable("Наставник ещё отвечает на прошлый вопрос")

    if payload.hint:
        # Каждая подсказка наставника отмечается в работе над заданием — и потом в попытке (BRIEF §5.7)
        work = practice._ensure_work(db, user, _task(db, payload.context_ref))
        work.mentor_hints = (work.mentor_hints or 0) + 1  # у только что созданной записи значения ещё нет
    db.add(MentorMessage(thread_id=thread.id, role="user", content=payload.text.strip() or "Дай подсказку", hint=payload.hint))
    answer = MentorMessage(thread_id=thread.id, role="assistant", status=MessageStatus.pending)
    db.add(answer)
    db.commit()
    enqueue(db, "chat", {"type": "mentor_reply", "message_id": str(answer.id), "files": payload.files})
    return answer


# ---------- Ответ (agent-worker) ----------


def _lesson_context(db: Session, user: User, ref: str) -> str:
    slug, _, lesson_id = ref.partition("/")
    course = courses.visible_course(db, slug, user, None)
    lesson = courses.lesson_detail(db, user, course, lesson_id, None) if course else None
    if lesson is None:
        return "Урок не найден."
    lines = [f"Курс «{lesson.course_title}», модуль «{lesson.module_title}», урок «{lesson.title}».", f"Цель урока: {lesson.goal or '—'}", "Теория урока:"]
    for block in lesson.blocks:
        if block.fragment:
            lines.append(f"- [{block.fragment.title}](/library/{block.fragment.id}) — {block.fragment.source.title}. {block.why}")
    for p in lesson.practice:
        if p.task:
            lines.append(f"Практика урока: задание «{p.task.title}».")
    return "\n".join(lines)


def _task_context(db: Session, user: User, ref: str, files: dict | None) -> str:
    task = _task(db, ref)
    learner = practice.for_learner(db, user, task, None)
    spec = TaskSpec.model_validate(practice.get_version(db, task.id, learner.version).spec)
    code = files or learner.files
    lines = [f"Задание «{spec.title}» ({spec.kind}).", "Условие:", spec.statement, "", "Код ученика сейчас:"]
    for name, text in code.items():
        lines.append(f"--- {name} ---\n{text[:12000]}")
    attempt = db.scalar(
        select(TaskAttempt).where(TaskAttempt.user_id == user.id, TaskAttempt.task_id == task.id).order_by(TaskAttempt.id.desc()).limit(1)
    )
    if attempt:
        lines.append("Последняя проверка:")
        lines += [f"{'✓' if r.get('passed') else '✗'} {r.get('name')}{': ' + r['message'] if r.get('message') else ''}" for r in attempt.results[:30]]
    if spec.sql_setup:
        lines.append(f"Схема и данные БД:\n{spec.sql_setup[:4000]}")
    if learner.fragments:
        lines.append("Теория к заданию: " + "; ".join(f"[{f['title']}](/library/{f['id']})" for f in learner.fragments))
    if learner.hints:
        lines.append("Подсказки, которые ученик уже открыл: " + " | ".join(learner.hints))
    return "\n".join(lines)


def build_prompt(db: Session, answer: MentorMessage, files: dict | None) -> str:
    thread = db.get(MentorThread, answer.thread_id)
    user = db.get(User, thread.user_id)
    if thread.context_kind == "lesson":
        context = _lesson_context(db, user, thread.context_ref)
    elif thread.context_kind == "task":
        context = _task_context(db, user, thread.context_ref, files)
    else:
        context = "Ученик пишет не из урока: общий вопрос по учёбе."

    history = list(db.scalars(
        select(MentorMessage).where(MentorMessage.thread_id == thread.id, MentorMessage.id < answer.id)
        .order_by(MentorMessage.id.desc()).limit(HISTORY)
    ))[::-1]
    question = history[-1] if history else None
    dialog = [f"{'Ученик' if m.role == 'user' else 'Наставник'}: {m.content}" for m in history[:-1] if m.content]
    hints = db.scalar(select(func.count()).where(MentorMessage.thread_id == thread.id, MentorMessage.hint.is_(True), MentorMessage.id < answer.id))
    ask = question.content if question else ""
    if question and question.hint:
        ask = f"[Подсказка №{hints}] {ask}"
    return "\n\n".join(part for part in [
        f"Контекст:\n{context}",
        "Переписка до этого:\n" + "\n".join(dialog) if dialog else "",
        f"Новое сообщение ученика:\n{ask}",
    ] if part)


def reply(db: Session, message_id: int, files: dict | None) -> dict:
    answer = db.get(MentorMessage, message_id)
    if answer is None or answer.status is not MessageStatus.pending:
        return {"skipped": True}
    prompt = build_prompt(db, answer, files)
    answer.status = MessageStatus.streaming
    db.commit()

    buffer: list[str] = []
    last = [time.monotonic()]

    def on_delta(text: str) -> None:
        buffer.append(text)
        if time.monotonic() - last[0] >= FLUSH_SECONDS:
            last[0] = time.monotonic()
            answer.content = "".join(buffer)
            db.commit()

    try:
        text = claude.stream_reply(prompt, SYSTEM, on_delta)
    except claude.AgentUnavailable as exc:
        answer.content = "".join(buffer)
        answer.status = MessageStatus.failed
        answer.error = str(exc)
        db.commit()
        return {"error": str(exc)}
    answer.content = text or "".join(buffer)
    answer.status = MessageStatus.done
    db.commit()
    return {"chars": len(answer.content)}
