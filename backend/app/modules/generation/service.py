"""Мастерская → Генерация (BRIEF §5.10): заявка → план → черновик → автопроверки → проверка админом → публикация.

Здесь — то, что делает API: заявки, правка плана, постановка задач в очередь, публикация.
Сами обращения к Claude — в pipeline.py, их выполняет agent-worker.
"""

import os
import re
from collections import Counter
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.modules.auth.models import User
from app.modules.courses import service as courses
from app.modules.courses.models import Course
from app.modules.generation.models import GenRequest, GenStatus, GenWhat
from app.modules.generation.schemas import (
    CreatedCourse,
    CreatedLesson,
    CreatedTask,
    Plan,
    ProjectOut,
    PublishOut,
    RequestCard,
    RequestIn,
    RequestOut,
    Step,
    TopicProposalIn,
)
from app.modules.jobs.queue import enqueue, has_pending
from app.modules.library.models import Fragment
from app.modules.practice import service as practice
from app.modules.practice.models import CheckStatus, Task
from app.modules.quiz.models import Question, QuestionStatus, QuizTopic
from app.modules.review import service as review_service
from app.modules.assess.models import Assignment
from app.modules.paths.models import ProjectPath

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "dist", "build", ".next", "__pycache__", ".cache", "graphify-out"}
LANGS = {
    ".html": "HTML", ".css": "CSS", ".js": "JavaScript", ".jsx": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript",
    ".py": "Python", ".sql": "SQL", ".md": "Markdown", ".json": "JSON", ".vue": "Vue", ".svelte": "Svelte",
}
BUSY = (GenStatus.planning, GenStatus.drafting)
ITEM_ID = re.compile(r"^[a-z0-9-]{4,40}$")  # как ItemId в схемах курса


class GenError(Exception):
    pass


# ---------- Проекты ----------


def _scan(path: Path, limit: int = 4000) -> tuple[int, list[str]]:
    count, langs = 0, Counter()
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for name in files:
            count += 1
            if lang := LANGS.get(Path(name).suffix.lower()):
                langs[lang] += 1
            if count >= limit:
                return count, [l for l, _ in langs.most_common(4)]
    return count, [l for l, _ in langs.most_common(4)]


def list_projects() -> list[ProjectOut]:
    root = Path(settings.projects_root)
    if not root.is_dir():
        return []
    out = []
    for entry in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if entry.is_dir() and not entry.name.startswith(".") and entry.name not in SKIP_DIRS:
            files, langs = _scan(entry)
            out.append(ProjectOut(name=entry.name, files=files, languages=langs))
    return out


def project_dir(req: GenRequest) -> str | None:
    """Папка, которую видит агент. Имя проекта и часть проверяются: выйти за пределы папки нельзя."""
    if not req.project:
        return None
    root = os.path.realpath(settings.projects_root)
    path = os.path.realpath(os.path.join(root, req.project, req.focus or ""))
    if not path.startswith(root + os.sep) or not os.path.isdir(path):
        raise GenError(f"Папка «{req.project}/{req.focus}» не найдена среди проектов")
    return path


def _validate_source(payload: RequestIn) -> None:
    if not payload.project and not payload.topic:
        raise GenError("Выберите проект или впишите тему")
    if payload.project:
        if "/" in payload.project or payload.project.startswith("."):
            raise GenError("Проект — это одна папка из списка")
        if ".." in payload.focus.split("/"):
            raise GenError("Часть проекта — путь внутри папки проекта")
        project_dir(GenRequest(project=payload.project, focus=payload.focus))


# ---------- Заявки ----------


def create_request(db: Session, admin: User, payload: RequestIn) -> GenRequest:
    _validate_source(payload)
    req = GenRequest(**payload.model_dump(), origin="admin", created_by=admin.id, status=GenStatus.new, steps=[], result={})
    db.add(req)
    db.commit()
    return req


def propose(db: Session, user: User, payload: TopicProposalIn) -> GenRequest:
    """Пользователь не создаёт контент — он только предлагает тему (BRIEF §5.7)."""
    req = GenRequest(
        what=GenWhat.course, origin="user", topic=payload.topic, notes=payload.notes, created_by=user.id,
        status=GenStatus.proposed, steps=[], result={},
    )
    db.add(req)
    db.commit()
    return req


def update_request(db: Session, req: GenRequest, payload: RequestIn) -> None:
    if req.status not in (GenStatus.proposed, GenStatus.new, GenStatus.failed) or req.plan:
        raise GenError("Заявку можно менять, пока не построен план")
    _validate_source(payload)
    for name, value in payload.model_dump().items():
        setattr(req, name, value)
    if req.status is GenStatus.proposed:
        req.status = GenStatus.new  # правка админом = заявка принята
    db.commit()


def reject(db: Session, req: GenRequest) -> None:
    if req.status is not GenStatus.proposed:
        raise GenError("Отклонить можно только новую заявку пользователя")
    req.status = GenStatus.rejected
    db.commit()


def busy(db: Session, req: GenRequest) -> bool:
    return req.status in BUSY or has_pending(db, "agent", request_id=str(req.id))


def _ensure_idle(db: Session, req: GenRequest) -> None:
    if busy(db, req):
        raise GenError("Наставник ещё работает над этой заявкой — дождитесь окончания шага")


def start_plan(db: Session, req: GenRequest, feedback: str | None = None) -> None:
    _ensure_idle(db, req)
    if req.status in (GenStatus.proposed, GenStatus.rejected):
        raise GenError("Сначала примите заявку")
    if req.result.get("lessons"):
        raise GenError("Черновик уже создан — меняйте уроки по одному («Переделать урок») или создайте новую заявку")
    project_dir(req)
    req.status = GenStatus.planning
    req.error = None
    req.steps = [Step(key="plan", label="План", state="pending").model_dump()]
    db.commit()
    enqueue(db, "agent", {"type": "gen_plan", "request_id": str(req.id), "feedback": feedback or ""})


def save_plan(db: Session, req: GenRequest, plan: Plan) -> None:
    if req.status is not GenStatus.plan_ready:
        raise GenError("План можно править, пока по нему не начат черновик")
    req.plan = normalize_plan(db, req, plan).model_dump()
    db.commit()


def normalize_plan(db: Session, req: GenRequest, plan: Plan) -> Plan:
    """Стабильные id, только существующие статьи, ограничения вида заявки."""
    known = set(db.scalars(select(Fragment.id).where(Fragment.id.in_(
        [f for m in plan.modules for l in m.lessons for f in l.fragment_ids]
    ))))
    used: set[str] = set()

    def new_id(prefix: str, current: str) -> str:
        ident = current if current and current not in used and ITEM_ID.match(current) else f"{prefix}{os.urandom(4).hex()}"
        used.add(ident)
        return ident

    for module in plan.modules:
        module.id = new_id("m", module.id)
        for lesson in module.lessons:
            lesson.id = new_id("l", lesson.id)
            lesson.fragment_ids = [f for f in dict.fromkeys(lesson.fragment_ids) if f in known]
            if req.what is GenWhat.quiz:
                lesson.practice = None
            if req.what is GenWhat.task:
                lesson.quiz = 0
            if req.what is GenWhat.path:
                lesson.practice, lesson.quiz = None, 0
            else:
                lesson.forks = []
    if req.what is GenWhat.path:
        # Путь — один модуль: этапы идут подряд
        plan.modules = [plan.modules[0].model_copy(update={"lessons": [l for m in plan.modules for l in m.lessons][:8]})]
    return plan


def start_draft(db: Session, req: GenRequest, admin: User) -> None:
    _ensure_idle(db, req)
    # failed — продолжение после сбоя: готовые уроки пропускаются
    if req.status not in (GenStatus.plan_ready, GenStatus.failed) or not req.plan:
        raise GenError("Без утверждённого плана черновик не создаётся")
    plan = Plan.model_validate(req.plan)
    if req.what is GenWhat.task and not any(l.practice for m in plan.modules for l in m.lessons):
        raise GenError("В плане нет ни одного практического задания")
    if req.what is GenWhat.quiz and not any(l.quiz for m in plan.modules for l in m.lessons):
        raise GenError("В плане нет ни одного вопроса")
    if req.what is GenWhat.path and not req.project:
        raise GenError("Путь «напиши заново сам» строится по проекту — выберите папку")
    req.status = GenStatus.drafting
    req.error = None
    req.pause = ""
    db.commit()
    enqueue(db, "agent", {"type": "gen_draft", "request_id": str(req.id), "admin_id": str(admin.id)})


def pause(db: Session, req: GenRequest, mode: str) -> None:
    """after — дописать текущий урок и остановиться; now — прервать вызов Claude сразу (урок начнётся заново)."""
    if req.status is not GenStatus.drafting:
        raise GenError("Приостановить можно, пока пишется черновик")
    req.pause = mode
    db.commit()


def resume(db: Session, req: GenRequest, admin: User) -> None:
    _ensure_idle(db, req)
    if req.status is not GenStatus.paused:
        raise GenError("Заявка не на паузе")
    again = {k: v for k, v in req.result.get("resume", {}).items() if v}
    req.status = GenStatus.drafting
    req.error = None
    req.pause = ""
    db.commit()
    enqueue(db, "agent", {"type": "gen_draft", "request_id": str(req.id), "admin_id": str(admin.id), **again})


def redo_lesson(db: Session, req: GenRequest, lesson_id: str, instruction: str, admin: User) -> None:
    _ensure_idle(db, req)
    if req.status not in (GenStatus.draft_ready, GenStatus.failed) or lesson_id not in req.result.get("lessons", {}):
        raise GenError("Переделать можно урок уже созданного черновика")
    req.status = GenStatus.drafting
    req.error = None
    req.pause = ""
    db.commit()
    enqueue(db, "agent", {
        "type": "gen_draft", "request_id": str(req.id), "admin_id": str(admin.id),
        "lesson_id": lesson_id, "instruction": instruction,
    })


def task_ids(req: GenRequest) -> list[int]:
    return [rec["task_id"] for rec in req.result.get("lessons", {}).values() if rec.get("task_id")]


def question_ids(req: GenRequest) -> list[int]:
    return [q for rec in req.result.get("lessons", {}).values() for q in rec.get("question_ids", [])]


def topic_ids(req: GenRequest) -> list[int]:
    return list(dict.fromkeys(req.result.get("topics", {}).values()))


def recheck(db: Session, req: GenRequest) -> int:
    started = 0
    for task in db.scalars(select(Task).where(Task.id.in_(task_ids(req)))):
        if task.draft_version:
            try:
                practice.request_check(db, task)
                started += 1
            except practice.TaskError:
                pass  # проверка уже идёт
    return started


# ---------- Публикация ----------


def publish_all(db: Session, req: GenRequest, admin: User) -> PublishOut:
    """Одна кнопка вместо десятка: задания, вопросы, темы тестов и курс. Если хоть что-то не готово —
    не публикуется ничего, чтобы пользователь не увидел половину курса."""
    if busy(db, req):
        raise GenError("Наставник ещё работает над заявкой")
    if req.what is GenWhat.path:
        return _publish_path(db, req)
    problems: list[str] = []
    tasks = list(db.scalars(select(Task).where(Task.id.in_(task_ids(req)))))
    questions = list(db.scalars(select(Question).where(Question.id.in_(question_ids(req)))))
    topics = list(db.scalars(select(QuizTopic).where(QuizTopic.id.in_(topic_ids(req)))))
    course = db.get(Course, req.result["course_id"]) if req.result.get("course_id") else None

    for task in tasks:
        if task.draft_version:
            version = practice.get_version(db, task.id, task.draft_version)
            title = version.spec.get("title") or task.slug
            problems += [f"Задание «{title}»: {p}" for p in practice.publish_problems(db, version)]
            problems += [f"Задание «{title}»: {p}" for p in review_service.reference_problems(db, task)]
    for q in questions:
        if q.status is QuestionStatus.draft and q.fragment_id is None:
            problems.append(f"Вопрос «{q.prompt[:60]}»: нет источника — укажите статью в редакторе вопроса.")
    if course and course.draft_version:
        own = {f"задание №{t.id} не опубликовано" for t in tasks} | {f"тема теста №{t.id} не опубликована" for t in topics}
        version = courses.get_version(db, course.id, course.draft_version)
        problems += [f"Курс: {p}" for p in courses.publish_problems(db, version) if not any(o in p for o in own)]
    if problems:
        return PublishOut(published=[], problems=problems)

    published: list[str] = []
    note = f"Мастерская, заявка №{req.id}"
    for task in tasks:
        if task.draft_version:
            practice.publish(db, task, note)
            published.append(f"задание «{practice.get_version(db, task.id, task.published_version).spec['title']}»")
    count = 0
    for q in questions:
        if q.status is QuestionStatus.draft:
            q.status = QuestionStatus.published
            count += 1
    db.flush()
    for topic in topics:
        total = db.scalar(select(func.count()).where(Question.topic_id == topic.id, Question.status == QuestionStatus.published))
        if total and not topic.published:
            topic.published = True
            topic.size = min(10, total)
            published.append(f"тест «{topic.title}»")
    if count:
        published.append(f"вопросов: {count}")
    db.commit()
    if course and course.draft_version:
        courses.publish(db, course, admin, note)
        published.append(f"курс «{courses.get_version(db, course.id, course.published_version).title}»")
    return PublishOut(published=published, problems=[])


def _publish_path(db: Session, req: GenRequest) -> PublishOut:
    """Путь и все его этапы — разом; этап без пройденной автопроверки не публикуется, и тогда ничего."""
    path = db.get(ProjectPath, req.result.get("path_id")) if req.result.get("path_id") else None
    if path is None:
        raise GenError("Черновика пути нет")
    stages = list(db.scalars(select(Assignment).where(Assignment.path_id == path.id).order_by(Assignment.position)))
    problems = [f"{a.title}: автопроверка тестов не пройдена ({'; '.join((a.check_report or {}).get('problems', [])) or a.check_status})"
                for a in stages if a.check_status != "passed"]
    problems += [f"{a.title}: нет развилок — нечего сверять с кодом" for a in stages if not a.forks]
    if problems:
        return PublishOut(published=[], problems=problems)
    for a in stages:
        a.published = True
    path.published = True
    db.commit()
    return PublishOut(published=[f"путь «{path.title}»", f"этапов: {len(stages)}"], problems=[])


def is_published(db: Session, req: GenRequest) -> bool:
    if req.what is GenWhat.path:
        path = db.get(ProjectPath, req.result.get("path_id")) if req.result.get("path_id") else None
        return bool(path and path.published)
    if not req.result.get("lessons"):
        return False
    if req.result.get("course_id"):
        course = db.get(Course, req.result["course_id"])
        return bool(course and course.published_version and not course.draft_version)
    tasks = db.scalars(select(Task).where(Task.id.in_(task_ids(req)))).all()
    topics = db.scalars(select(QuizTopic).where(QuizTopic.id.in_(topic_ids(req)))).all()
    return all(t.published_version and not t.draft_version for t in tasks) and all(t.published for t in topics)


# ---------- Ответы API ----------


def title_of(req: GenRequest) -> str:
    if req.plan:
        return req.plan["title"]
    if req.topic:
        return req.topic
    return f"{req.project}{'/' + req.focus if req.focus else ''}"


def _author(db: Session, req: GenRequest) -> str | None:
    user = db.get(User, req.created_by) if req.created_by else None
    return user.login if user else None


def to_card(db: Session, req: GenRequest) -> RequestCard:
    return RequestCard(
        id=req.id, status=req.status, what=req.what, origin=req.origin, title=title_of(req), project=req.project,
        author=_author(db, req), busy=busy(db, req), published=is_published(db, req), updated_at=req.updated_at,
    )


def _task_out(db: Session, task: Task) -> CreatedTask:
    version = practice.get_version(db, task.id, task.draft_version or task.published_version)
    report = version.check_report or {}
    if version.check_status is CheckStatus.passed:
        summary = "эталон проходит тесты, стартовый код — нет"
    elif version.check_status is CheckStatus.failed:
        summary = "; ".join(report.get("problems", []))[:400]
    elif version.check_status is CheckStatus.queued:
        summary = "проверка в очереди runner"
    else:
        summary = "ещё не проверялось"
    review = review_service.reference_review(db, task)
    if review is None:
        review_summary = "ещё не проверял"
    elif review.status.value in ("queued", "running"):
        review_summary = "проверяет…"
    elif review.status.value == "failed":
        review_summary = f"не удалось: {review.error}"
    else:
        c = review_service.counts(review)
        review_summary = ("замечаний нет" if not review.findings else f"blocker {c['blocker']}, major {c['major']}, minor {c['minor']}") + (
            " — приняты админом" if review.accepted_by else "")
    return CreatedTask(
        id=task.id, slug=task.slug, title=version.spec.get("title", ""), kind=version.spec["kind"],
        draft_version=task.draft_version, published=bool(task.published_version),
        check_status=version.check_status.value, check_summary=summary,
        review_verdict=review.verdict if review else None, review_summary=review_summary,
    )


def to_out(db: Session, req: GenRequest) -> RequestOut:
    plan = Plan.model_validate(req.plan) if req.plan else None
    records = req.result.get("lessons", {})
    tasks = {t.id: t for t in db.scalars(select(Task).where(Task.id.in_(task_ids(req))))}
    question_status = dict(db.execute(select(Question.id, Question.status).where(Question.id.in_(question_ids(req)))).all())
    all_fragments = {f for rec in records.values() for f in rec.get("theory", [])}
    if plan:
        all_fragments |= {f for m in plan.modules for l in m.lessons for f in l.fragment_ids}
    fragments = {
        f.id: f for f in db.scalars(select(Fragment).options(joinedload(Fragment.source)).where(Fragment.id.in_(all_fragments)))
    }

    lessons = []
    for module in plan.modules if plan else []:
        for lesson in module.lessons:
            rec = records.get(lesson.id)
            if rec is None:
                continue
            qs = [q for q in rec.get("question_ids", []) if q in question_status]
            task = tasks.get(rec.get("task_id"))
            stage = None
            if rec.get("assignment_id") and (a := db.get(Assignment, rec["assignment_id"])):
                report = a.check_report or {}
                stage = {
                    "assignment_id": a.id, "slug": a.slug, "check_status": a.check_status, "forks": [f["question"] for f in a.forks],
                    "check_summary": "; ".join(report.get("problems", [])) or (
                        f"на оригинале проходят {report.get('passed')} из {report.get('total')}, на пустой папке — нет" if a.check_status == "passed" else a.check_status),
                }
            lessons.append(CreatedLesson(
                id=lesson.id, title=lesson.title, task=_task_out(db, task) if task else None, stage=stage,
                questions=len(qs), questions_published=sum(question_status[q] is QuestionStatus.published for q in qs),
                theory=[{"id": f, "title": fragments[f].title} for f in rec.get("theory", []) if f in fragments],
                notes=rec.get("notes", []),
            ))

    course = None
    if req.result.get("course_id") and (c := db.get(Course, req.result["course_id"])):
        version = courses.editing_version(db, c)
        course = CreatedCourse(id=c.id, slug=c.slug, title=version.title, draft_version=c.draft_version, published_version=c.published_version)
    topics = []
    for topic in db.scalars(select(QuizTopic).where(QuizTopic.id.in_(topic_ids(req)))):
        n = sum(1 for q in db.scalars(select(Question.id).where(Question.topic_id == topic.id)))
        topics.append({"id": topic.id, "title": topic.title, "published": topic.published, "questions": n})

    return RequestOut(
        id=req.id, status=req.status, what=req.what, origin=req.origin, project=req.project, focus=req.focus,
        topic=req.topic, level=req.level, notes=req.notes, author=_author(db, req), plan=plan,
        fragments={f.id: f"{f.title} · {f.source.title}" for f in fragments.values()},
        steps=[Step.model_validate(s) for s in req.steps], error=req.error, busy=busy(db, req), pause=req.pause,
        published=is_published(db, req), course=course, topics=topics, lessons=lessons,
        path=({"slug": pth.slug, "title": pth.title, "published": pth.published}
              if req.result.get("path_id") and (pth := db.get(ProjectPath, req.result["path_id"])) else None),
        created_at=req.created_at, updated_at=req.updated_at,
    )
