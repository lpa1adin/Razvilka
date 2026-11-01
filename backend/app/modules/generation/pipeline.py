"""Шаги генерации, которые выполняет agent-worker: план и черновик по урокам, с автопроверками.

Черновик пишется по одному уроку за обращение: прогресс виден по шагам, а упавший урок не теряет готовые.
Повторный запуск (после перезапуска воркера) пропускает уже созданные уроки.
"""

import logging
import time
from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.core.db import SessionLocal
from app.modules.agent import claude
from app.modules.auth.models import User
from app.modules.courses import service as courses
from app.modules.courses.models import Course
from app.modules.courses.schemas import CourseContent
from app.modules.generation import prompts
from app.modules.generation.models import GenRequest, GenStatus, GenWhat
from app.modules.generation.schemas import DraftTask, LessonDraft, Plan, PlanLesson, PlanModule, Step, TaskFix
from app.modules.generation.service import normalize_plan, project_dir
from app.modules.library.models import Fragment, FragmentStatus
from app.modules.practice import service as practice
from app.modules.projectmap import cache
from app.modules.projectmap.graph import outline
from app.modules.practice.models import CheckStatus, Task
from app.modules.practice.schemas import TaskSpec
from app.modules.quiz import service as quiz
from app.modules.quiz.models import Question, QuestionStatus, QuizAttemptItem, QuizTopic
from app.modules.quiz.schemas import QuestionIn
from app.modules.review import service as review_service

log = logging.getLogger("generation")
CHECK_WAIT_SECONDS = 300
PROGRESS_EVERY = 1.5  # не чаще — каждое обновление шага пишется в базу


# ---------- Шаги ----------


class Steps:
    def __init__(self, db: Session, req: GenRequest):
        self.db, self.req, self._last = db, req, 0.0

    def set(self, key: str, state: str | None = None, detail: str | None = None, label: str | None = None) -> None:
        steps = [dict(s) for s in self.req.steps]
        step = next((s for s in steps if s["key"] == key), None)
        if step is None:
            step = Step(key=key, label=label or key, state="pending").model_dump()
            steps.append(step)
        if state:
            step["state"] = state
        if detail is not None:
            step["detail"] = detail[:300]
        if label:
            step["label"] = label
        self.req.steps = steps
        self.db.commit()

    def progress(self, key: str):
        """Колбэк для Claude: «читает src/main.js» — показываем админу, что агент делает прямо сейчас."""

        def report(text: str) -> None:
            now = time.monotonic()
            if now - self._last >= PROGRESS_EVERY:
                self._last = now
                self.set(key, detail=text)

        return report


def _fail(db: Session, req: GenRequest, steps: Steps, key: str, message: str) -> None:
    db.rollback()
    req.status = GenStatus.failed
    req.error = message
    steps.set(key, "failed", message)


class Paused(Exception):
    """Админ попросил паузу: шаг останавливается, всё готовое уже сохранено."""


def pause_mode(request_id: int) -> str:
    # Флаг ставит API в своей транзакции — читаем отдельной сессией, не трогая сессию конвейера
    with SessionLocal() as s:
        return s.scalar(select(GenRequest.pause).where(GenRequest.id == request_id)) or ""


def checkpoint(req: GenRequest) -> None:
    """Между уроками и шагами: любая запрошенная пауза останавливает работу здесь."""
    if pause_mode(req.id):
        raise Paused()


def stop_now(request_id: int):
    """Для вызова Claude: «остановить сейчас» прерывает его, не дожидаясь конца урока. БД — не чаще раза в 2 с."""
    last = {"at": 0.0, "stop": False}

    def check() -> bool:
        now = time.monotonic()
        if now - last["at"] >= 2:
            last["at"], last["stop"] = now, pause_mode(request_id) == "now"
        return last["stop"]

    return check


def spent(usage: dict[str, int]) -> str:
    """Расход токенов шага — для админа: видно, во что обходится генерация."""
    fresh = usage.get("input", 0) + usage.get("cache_write", 0)
    return f"токенов: {fresh / 1000:.1f} тыс. на входе (+{usage.get('cache_read', 0) / 1000:.1f} тыс. из кэша), {usage.get('output', 0) / 1000:.1f} тыс. на выходе"


# ---------- План ----------


def run_plan(db: Session, request_id: int, feedback: str) -> dict:
    req = db.get(GenRequest, request_id)
    steps = Steps(db, req)
    steps.set("plan", "running", "изучает граф проекта" if req.project else "подбирает темы", label="План")
    usage: dict[str, int] = {}
    cwd = project_dir(req)
    # Карта проекта прямо в задании: агенту не нужно ходить по файлам, чтобы понять устройство проекта
    system, prompt = prompts.plan_prompt(req, req.plan, feedback or None, cache.render_map(cwd) if cwd else "")
    try:
        plan = claude.run_structured(
            "plan", prompt, system, Plan, cwd=cwd, effort="high", on_progress=steps.progress("plan"),
            on_usage=lambda u: usage.update(u),
        )
    except Exception as exc:
        _fail(db, req, steps, "plan", str(exc))
        raise
    lessons = sum(len(m.lessons) for m in plan.modules)
    req.plan = normalize_plan(db, req, plan).model_dump()
    req.status = GenStatus.plan_ready
    req.error = None
    steps.set("plan", "done", f"модулей: {len(plan.modules)}, уроков: {lessons} · {spent(usage)}")
    return {"modules": len(plan.modules), "lessons": lessons, "tokens": usage}


# ---------- Черновик ----------


def _fragments(db: Session, ids: list[int]) -> dict[int, Fragment]:
    rows = db.scalars(select(Fragment).where(Fragment.id.in_(ids), Fragment.status == FragmentStatus.active))
    return {f.id: f for f in rows}


def _topic_for(db: Session, req: GenRequest, plan: Plan, module: PlanModule) -> QuizTopic:
    """Курс — одна тема теста на модуль, банк вопросов — одна тема на всю заявку."""
    key = module.id if req.what is GenWhat.course else "all"
    topics = dict(req.result.get("topics", {}))
    topic = db.get(QuizTopic, topics[key]) if key in topics else None
    if topic is None:
        # Модулей несколько — у каждого свой тест; один — тест называется как курс
        title = f"{plan.title}: {module.title}" if req.what is GenWhat.course and len(plan.modules) > 1 else plan.title
        slug = base = courses.slugify(title)[:70] or "test"
        n = 2
        while db.scalar(select(QuizTopic.id).where(QuizTopic.slug == slug)):
            slug, n = f"{base}-{n}", n + 1
        topic = QuizTopic(slug=slug, title=title[:200], description=plan.description[:1000], published=False, size=10)
        db.add(topic)
        db.flush()
        topics[key] = topic.id
        req.result = {**req.result, "topics": topics}
    return topic


def _discard(db: Session, rec: dict) -> None:
    """Перед переделкой урока убираем его старые черновики — но не то, что уже видели пользователи."""
    task = db.get(Task, rec.get("task_id")) if rec.get("task_id") else None
    if task is not None and not task.published_version:
        db.delete(task)
    for qid in rec.get("question_ids", []):
        q = db.get(Question, qid)
        used = db.scalar(select(QuizAttemptItem.id).where(QuizAttemptItem.question_id == qid).limit(1))
        if q is not None and q.status is QuestionStatus.draft and not used:
            db.delete(q)
    db.flush()


def _spec(draft: DraftTask, fragment_ids: list[int]) -> TaskSpec:
    return TaskSpec(
        title=draft.title, kind=draft.kind, statement=draft.statement, starter=draft.starter, solution=draft.solution,
        tests=draft.tests, sql_setup=draft.sql_setup, sql_checks=draft.sql_checks, hints=draft.hints,
        fragment_ids=fragment_ids[:10],
    )


def _materialize(db: Session, req: GenRequest, admin: User, plan: Plan, module: PlanModule, lesson: PlanLesson, draft: LessonDraft) -> dict:
    """Ответ Claude → настоящие черновики: задание, вопросы, блоки урока. Всё, что не прошло проверку
    формата, не теряется молча — попадает в заметки урока."""
    notes: list[str] = []
    known = _fragments(db, [t.fragment_id for t in draft.theory] + [q.fragment_id for q in draft.questions])
    theory = [t for t in draft.theory if t.fragment_id in known]
    if len(theory) < len(draft.theory):
        notes.append("Часть статей не нашлась в библиотеке и не добавлена.")
    if not theory:
        notes.append("В уроке нет теории — добавьте статью в редакторе курса.")
    theory_ids = list(dict.fromkeys(t.fragment_id for t in theory))

    task_id = None
    if draft.task:
        try:
            spec = _spec(draft.task, theory_ids)
            task = practice.create_task(db, spec.title or lesson.title, spec.kind, admin, spec)
            practice.request_check(db, task)
            task_id = task.id
        except (ValidationError, ValueError) as exc:
            notes.append(f"Задание не создано: формат не подошёл ({str(exc)[:200]}).")

    question_ids = []
    if draft.questions:
        topic = _topic_for(db, req, plan, module)
        for i, dq in enumerate(draft.questions, 1):
            try:
                data = QuestionIn(
                    type=dq.type, prompt=dq.prompt, code=dq.code, code_lang=dq.code_lang,
                    options=dq.options.model_dump(exclude_none=True), answer=dq.answer.model_dump(exclude_none=True),
                    explanation=dq.explanation, fragment_id=dq.fragment_id if dq.fragment_id in known else None,
                    subtopic=lesson.title[:120], difficulty=dq.difficulty, status=QuestionStatus.draft,
                )
            except ValidationError as exc:
                notes.append(f"Вопрос {i} пропущен: {exc.errors()[0]['msg']}.")
                continue
            if similar := quiz.similar_questions(db, topic.id, data.prompt, data.code):
                notes.append(f"Вопрос {i} пропущен: похож на «{similar[0].prompt[:60]}».")
                continue
            if data.fragment_id is None:
                notes.append(f"Вопрос {i}: источник не найден в библиотеке — укажите статью вручную.")
            question = Question(topic_id=topic.id)
            quiz.apply(question, data)
            db.add(question)
            db.flush()
            question_ids.append(question.id)

    db.commit()
    return {
        "module_id": module.id, "task_id": task_id, "question_ids": question_ids, "theory": theory_ids,
        "why": {str(t.fragment_id): t.why for t in theory}, "notes": notes, "fixes": 0, "done": True,
    }


def _lesson_blocks(req: GenRequest, module: PlanModule, lesson: PlanLesson, last_in_module: bool) -> list[dict]:
    rec = req.result.get("lessons", {}).get(lesson.id)
    if not rec:
        return []
    blocks = [
        {"id": f"t{i}-{lesson.id}", "type": "theory", "fragment_id": f, "why": rec["why"].get(str(f), "")}
        for i, f in enumerate(rec["theory"], 1)
    ]
    if rec.get("task_id"):
        blocks.append({"id": f"p-{lesson.id}", "type": "practice", "task_id": rec["task_id"]})
    topic_id = req.result.get("topics", {}).get(module.id)
    if last_in_module and topic_id:
        blocks.append({"id": f"q-{module.id}", "type": "quiz", "topic_id": topic_id})
    return blocks


def _sync_course(db: Session, req: GenRequest, admin: User, plan: Plan, only_lesson: str | None) -> None:
    """Черновик курса = план + созданные блоки. При переделке урока меняются только его блоки —
    ручные правки админа в остальных уроках не теряются."""
    if req.what is not GenWhat.course:
        return
    course = db.get(Course, req.result["course_id"]) if req.result.get("course_id") else None
    if course is None:
        course = courses.create_course(db, plan.title, plan.description, admin)
        req.result = {**req.result, "course_id": course.id}
    draft = courses.start_draft(db, course, admin)
    current = CourseContent.model_validate(draft.content)
    existing = {l.id: l for m in current.modules for l in m.lessons}

    modules = []
    for module in plan.modules:
        lessons = []
        for i, lesson in enumerate(module.lessons):
            blocks = _lesson_blocks(req, module, lesson, i == len(module.lessons) - 1)
            if only_lesson and lesson.id != only_lesson and lesson.id in existing:
                blocks = existing[lesson.id].model_dump()["blocks"]
                # Тест модуля переезжает в последний урок, если состав модуля поменялся
                blocks = [b for b in blocks if b["type"] != "quiz"] + [b for b in _lesson_blocks(req, module, lesson, i == len(module.lessons) - 1) if b["type"] == "quiz"]
            lessons.append({"id": lesson.id, "title": lesson.title, "goal": lesson.goal[:1500], "blocks": blocks})
        modules.append({"id": module.id, "title": module.title, "lessons": lessons})
    draft.title = plan.title
    draft.description = plan.description[:1500]
    draft.content = CourseContent.model_validate({"modules": modules}).model_dump()
    db.commit()


def _wait_checks(db: Session, ids: list[int], req: GenRequest | None = None) -> None:
    deadline = time.monotonic() + CHECK_WAIT_SECONDS
    while time.monotonic() < deadline:
        if req is not None and pause_mode(req.id) == "now":
            raise Paused()
        db.expire_all()
        versions = [practice.editing_version(db, t) for t in db.scalars(select(Task).where(Task.id.in_(ids)))]
        if all(v.check_status is not CheckStatus.queued for v in versions):
            return
        time.sleep(3)


def _autochecks(db: Session, req: GenRequest, steps: Steps, lesson_ids: list[str]) -> None:
    """Автопроверки без Claude: runner прогоняет эталон и стартовый код. Не прошло — Claude один раз чинит
    задание по отчёту проверки, дальше решает админ."""
    records = req.result.get("lessons", {})
    ids = [records[l]["task_id"] for l in lesson_ids if records.get(l, {}).get("task_id")]
    if not ids:
        steps.set("checks", "skipped", "в черновике нет практических заданий")
        return
    steps.set("checks", "running", "runner проверяет эталоны и стартовый код")
    _wait_checks(db, ids, req)

    for lesson_id in lesson_ids:
        rec = records.get(lesson_id, {})
        task = db.get(Task, rec.get("task_id")) if rec.get("task_id") else None
        if task is None or not task.draft_version:
            continue
        version = practice.editing_version(db, task)
        if version.check_status is not CheckStatus.failed or rec.get("fixes", 0) >= 1:
            continue
        checkpoint(req)
        steps.set("checks", detail=f"исправляет «{version.spec['title']}» по отчёту проверки")
        problems = (version.check_report or {}).get("problems", [])
        try:
            system, prompt = prompts.fix_prompt({k: v for k, v in version.spec.items() if k != "fragment_ids"}, problems)
            fix = claude.run_structured("fix", prompt, system, TaskFix, effort="high", max_turns=20, should_stop=stop_now(req.id))
            spec = _spec(fix.task, version.spec.get("fragment_ids", []))
            if spec.kind != version.spec["kind"]:
                raise ValueError("Claude поменял вид задания")
            version.spec = spec.model_dump()
            rec["notes"] = [*rec.get("notes", []), f"Автопроверка не прошла с первого раза. Исправлено: {fix.note}"]
            db.commit()
            practice.request_check(db, task)
        except (claude.AgentUnavailable, ValidationError, ValueError) as exc:
            rec["notes"] = [*rec.get("notes", []), f"Не удалось исправить задание автоматически: {str(exc)[:200]}"]
        rec["fixes"] = rec.get("fixes", 0) + 1
        req.result = {**req.result, "lessons": {**records, lesson_id: rec}}
        flag_modified(req, "result")
        db.commit()

    _wait_checks(db, ids, req)
    versions = [practice.editing_version(db, t) for t in db.scalars(select(Task).where(Task.id.in_(ids)))]
    passed = sum(v.check_status is CheckStatus.passed for v in versions)
    pending = sum(v.check_status is CheckStatus.queued for v in versions)
    detail = f"прошли {passed} из {len(versions)}" + (f", ещё в очереди: {pending}" if pending else "")
    steps.set("checks", "done" if passed == len(versions) else "failed", detail)


def _review_references(db: Session, req: GenRequest, steps: Steps, admin: User, lesson_ids: list[str]) -> None:
    """Независимый Ревьюер проверяет эталоны, прошедшие автотесты: эталон не должен учить плохому.
    Каждое ревью — отдельная сессия Claude без контекста генерации (то, что писал наставник, он не видит)."""
    records = req.result.get("lessons", {})
    tasks = [db.get(Task, records[l]["task_id"]) for l in lesson_ids if records.get(l, {}).get("task_id")]
    tasks = [t for t in tasks if t is not None and t.draft_version and practice.editing_version(db, t).check_status is CheckStatus.passed]
    if not tasks:
        steps.set("review", "skipped", "нечего проверять: нет эталонов, прошедших автотесты")
        return
    clean, flagged, failed = 0, 0, 0
    for n, task in enumerate(tasks, 1):
        # После паузы уже проверенные эталоны (та же редакция) второй раз лимит не тратят
        done = review_service.reference_review(db, task)
        if done is not None and done.status.value == "done":
            clean += done.verdict != "changes_requested"
            flagged += done.verdict == "changes_requested"
            continue
        checkpoint(req)
        steps.set("review", "running", f"проверяет эталон {n} из {len(tasks)}")
        try:
            review = review_service.request_reference(db, admin, task, enqueue_job=False)
            review_service.run(db, review.id)
            db.refresh(review)
        except review_service.ReviewError as exc:
            steps.set("review", "failed", str(exc))
            return
        if review.status.value == "failed":
            failed += 1
        elif review.verdict == "changes_requested":
            flagged += 1
            lesson = next(l for l in lesson_ids if records.get(l, {}).get("task_id") == task.id)
            c = review_service.counts(review)
            rec = records[lesson]
            rec["notes"] = [*rec.get("notes", []), f"Ревьюер: у эталона {c['blocker']} blocker, {c['major']} major. Нажмите «Ревьюер» в карточке — там каждое замечание с кодом эталона; исправьте эталон или примите замечания с пояснением."]
            req.result = {**req.result, "lessons": {**records, lesson: rec}}
            flag_modified(req, "result")
            db.commit()
        else:
            clean += 1
    detail = f"без серьёзных замечаний: {clean} из {len(tasks)}" + (f", с замечаниями: {flagged}" if flagged else "") + (f", не удалось: {failed}" if failed else "")
    steps.set("review", "done" if not flagged and not failed else "failed", detail)


def run_draft(db: Session, request_id: int, admin_id: int, lesson_id: str = "", instruction: str = "") -> dict:
    req = db.get(GenRequest, request_id)
    admin = db.get(User, admin_id)
    plan = Plan.model_validate(req.plan)
    steps = Steps(db, req)
    cwd = project_dir(req)
    if req.what is GenWhat.path:
        from app.modules.generation.path_pipeline import run_path_draft

        try:
            return run_path_draft(db, req, admin, steps, cwd, lesson_id, instruction)
        except (Paused, claude.Stopped):
            raise
        except Exception as exc:
            running = next((s["key"] for s in req.steps if s["state"] == "running"), "checks")
            _fail(db, req, steps, running, str(exc))
            raise
    pairs = [(m, l) for m in plan.modules for l in m.lessons]
    targets = [(m, l) for m, l in pairs if not lesson_id or l.id == lesson_id]

    # Шаги видны сразу: админ понимает, сколько ещё ждать
    # Номер — место урока в плане, а не среди переделываемых: иначе «Переделать урок» всегда давал «Урок 1»
    number = {l.id: n for n, (_, l) in enumerate(pairs, 1)}
    for module, lesson in targets:
        done = not lesson_id and req.result.get("lessons", {}).get(lesson.id, {}).get("done")
        steps.set(f"lesson:{lesson.id}", "done" if done else "pending", label=f"Урок {number[lesson.id]}. {lesson.title}")
    steps.set("checks", "pending", label="Автопроверки")
    steps.set("review", "pending", label="Ревьюер эталонов")

    for module, lesson in targets:
        key = f"lesson:{lesson.id}"
        records = dict(req.result.get("lessons", {}))
        if not lesson_id and records.get(lesson.id, {}).get("done"):
            continue
        checkpoint(req)
        steps.set(key, "running", "пишет черновик урока")
        fragments = _fragments(db, lesson.fragment_ids)
        described = [f"#{f.id} «{f.title}» — {f.source.title}" for f in fragments.values()] or ["— (подберите сами)"]
        files_outline = "\n".join(outline(cwd, f) for f in (lesson.files or [])[:6]) if cwd else ""
        system, prompt = prompts.lesson_prompt(
            req, plan.model_dump(), module.model_dump(), lesson.model_dump(), described, instruction or None, files_outline,
        )
        usage: dict[str, int] = {}
        try:
            draft = claude.run_structured(
                "draft", prompt, system, LessonDraft, cwd=cwd, effort="high", on_progress=steps.progress(key),
                on_usage=lambda u: usage.update(u), should_stop=stop_now(req.id),
            )
            if lesson.id in records:
                _discard(db, records[lesson.id])
            rec = _materialize(db, req, admin, plan, module, lesson, draft)
        except claude.Stopped:
            raise
        except Exception as exc:
            _fail(db, req, steps, key, str(exc))
            raise
        req.result = {**req.result, "lessons": {**records, lesson.id: rec}}
        flag_modified(req, "result")
        _sync_course(db, req, admin, plan, lesson_id or None)
        made = [f"статей: {len(rec['theory'])}"] + (["задание"] if rec["task_id"] else []) + (
            [f"вопросов: {len(rec['question_ids'])}"] if rec["question_ids"] else []
        )
        steps.set(key, "done", ", ".join(made) + f" · {spent(usage)}")

    _sync_course(db, req, admin, plan, lesson_id or None)
    checkpoint(req)
    _autochecks(db, req, steps, [l.id for _, l in targets])
    _review_references(db, req, steps, admin, [l.id for _, l in targets])
    req.status = GenStatus.draft_ready
    req.error = None
    db.commit()
    return {"lessons": len(targets), "finished_at": datetime.now(UTC).isoformat()}


def handle(db: Session, payload: dict) -> dict:
    if payload["type"] == "gen_plan":
        return run_plan(db, int(payload["request_id"]), payload.get("feedback", ""))
    if payload["type"] == "gen_draft":
        try:
            return run_draft(
                db, int(payload["request_id"]), int(payload["admin_id"]), payload.get("lesson_id", ""), payload.get("instruction", ""),
            )
        except (Paused, claude.Stopped):
            return _paused(db, int(payload["request_id"]), payload)
    raise ValueError(f"Неизвестная задача генерации {payload['type']!r}")



def _paused(db: Session, request_id: int, payload: dict) -> dict:
    """Пауза: готовые уроки уже в базе, недописанный урок отброшен. Запоминаем, как продолжить."""
    db.rollback()
    req = db.get(GenRequest, request_id)
    lesson_id = payload.get("lesson_id", "")
    # «Переделать урок»: если сам урок уже переписан, после паузы остаются только проверки — урок не повторяем
    redo_done = lesson_id and any(s["key"] == f"lesson:{lesson_id}" and s["state"] == "done" for s in req.steps)
    req.result = {**req.result, "resume": {} if not lesson_id or redo_done else {"lesson_id": lesson_id, "instruction": payload.get("instruction", "")}}
    req.steps = [{**s, "state": "pending", "detail": "на паузе — продолжится отсюда"} if s["state"] == "running" else s for s in req.steps]
    req.status = GenStatus.paused
    req.error = None
    # Флаг ставил API в другой сессии: здесь он для ORM «не менялся», поэтому сбрасываем явным UPDATE
    db.execute(update(GenRequest).where(GenRequest.id == request_id).values(pause=""))
    db.commit()
    log.info("генерация %s на паузе", request_id)
    return {"paused": True}
