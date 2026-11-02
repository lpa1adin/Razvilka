from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.modules.auth.models import User
from app.modules.courses.models import VersionStatus
from app.modules.courses.service import CourseError, slugify
from app.modules.jobs.queue import enqueue, has_pending
from app.modules.library.models import Fragment
from app.modules.library.render import render_markdown
from app.modules.practice.models import CheckStatus, Task, TaskAttempt, TaskVersion, TaskWork
from app.modules.practice.runner import spec_hash
from app.modules.practice.schemas import (
    FILES,
    AttemptIn,
    TaskCard,
    TaskDraftIn,
    TaskForLearner,
    TaskSpec,
    TaskVersionOut,
)

TaskError = CourseError  # те же правила: сообщение можно показать админу как есть


def get_version(db: Session, task_id: int, number: int | None) -> TaskVersion | None:
    if number is None:
        return None
    return db.scalar(select(TaskVersion).where(TaskVersion.task_id == task_id, TaskVersion.number == number))


def editing_version(db: Session, task: Task) -> TaskVersion:
    version = get_version(db, task.id, task.draft_version or task.published_version)
    if version is None:
        raise TaskError("У задания нет ни черновика, ни опубликованной версии")
    return version


def version_out(version: TaskVersion) -> TaskVersionOut:
    return TaskVersionOut(
        number=version.number,
        status=version.status,
        spec=TaskSpec.model_validate(version.spec),
        check_status=version.check_status,
        proposal=version.proposal,
        check_report=version.check_report,
        check_is_current=version.checked_hash == spec_hash(version.spec),
        change_note=version.change_note,
        created_at=version.created_at,
        updated_at=version.updated_at,
        published_at=version.published_at,
    )


# ---------- Мастерская ----------


def empty_spec(title: str, kind: str) -> TaskSpec:
    files = {name: "" for name in FILES[kind]}
    if kind == "web":
        files["index.html"] = '<!doctype html>\n<html lang="ru">\n<head>\n  <meta charset="utf-8">\n  <link rel="stylesheet" href="style.css">\n</head>\n<body>\n\n  <script src="script.js"></script>\n</body>\n</html>\n'
    return TaskSpec(title=title, kind=kind, starter=files, solution=dict(files))


def create_task(db: Session, title: str, kind: str, admin: User, spec: TaskSpec | None = None) -> Task:
    task = Task(slug=unique_slug(db, title), draft_version=1)
    db.add(task)
    db.flush()
    db.add(TaskVersion(
        task_id=task.id, number=1, status=VersionStatus.draft,
        spec=(spec or empty_spec(title, kind)).model_dump(), created_by=admin.id,
    ))
    db.commit()
    return task


def unique_slug(db: Session, title: str) -> str:
    slug = base = slugify(title)
    n = 2
    while db.scalar(select(Task.id).where(Task.slug == slug)):
        slug, n = f"{base}-{n}", n + 1
    return slug


def start_draft(db: Session, task: Task, admin: User) -> None:
    if task.draft_version:
        return
    published = editing_version(db, task)
    last = db.scalar(select(TaskVersion.number).where(TaskVersion.task_id == task.id).order_by(TaskVersion.number.desc()))
    db.add(TaskVersion(task_id=task.id, number=last + 1, status=VersionStatus.draft, spec=published.spec, created_by=admin.id))
    task.draft_version = last + 1
    db.commit()


def save_draft(db: Session, task: Task, payload: TaskDraftIn) -> None:
    if not task.draft_version:
        raise TaskError("Черновика нет — сначала нажмите «Редактировать»")
    if payload.number != task.draft_version:
        raise TaskError("Черновик уже изменился в другой вкладке. Обновите страницу.")
    current = get_version(db, task.id, task.draft_version)
    spec = payload.spec
    if spec.kind != current.spec["kind"]:
        raise TaskError("Вид задания (веб / Python / SQL) после создания не меняется — создайте новое задание")
    current.spec = spec.model_dump()
    db.commit()


def request_check(db: Session, task: Task) -> None:
    version = get_version(db, task.id, task.draft_version)
    if version is None:
        raise TaskError("Проверять нечего: черновика нет")
    if has_pending(db, "runner", version_id=str(version.id)):
        raise TaskError("Проверка уже идёт")
    version.check_status = CheckStatus.queued
    db.commit()
    enqueue(db, "runner", {"type": "verify_task", "version_id": str(version.id)})


def publish_problems(db: Session, version: TaskVersion) -> list[str]:
    spec = TaskSpec.model_validate(version.spec)
    problems = []
    if not spec.title:
        problems.append("У задания нет названия.")
    if not spec.statement.strip():
        problems.append("Нет условия задания.")
    if version.check_status is not CheckStatus.passed:
        problems.append("Автопроверка не пройдена: нажмите «Проверить задание» и дождитесь результата.")
    elif version.checked_hash != spec_hash(version.spec):
        problems.append("Задание изменилось после автопроверки — запустите её ещё раз.")
    if version.proposal:
        problems.append("Claude предложил изменить условие или стартовый код — примите или отклоните правку в редакторе задания.")
    return problems


PROPOSABLE = ("statement", "starter", "hints", "sql_setup")


def resolve_proposal(db: Session, task: Task, accept: bool) -> None:
    """Админ принимает или отклоняет правку, предложенную при исправлении эталона по замечаниям Ревьюера."""
    version = get_version(db, task.id, task.draft_version)
    if version is None or not version.proposal:
        raise TaskError("Предложенной правки нет")
    if accept:
        version.spec = {**version.spec, **{k: v for k, v in version.proposal["fields"].items() if k in PROPOSABLE}}
    version.proposal = None
    db.commit()
    if accept:
        request_check(db, task)


def publish(db: Session, task: Task, change_note: str) -> None:
    draft = get_version(db, task.id, task.draft_version)
    if task.published_version:
        get_version(db, task.id, task.published_version).status = VersionStatus.superseded
    draft.status = VersionStatus.published
    draft.published_at = datetime.now(UTC)
    draft.change_note = change_note
    task.published_version = draft.number
    task.draft_version = None
    db.commit()


# ---------- Учёба ----------


def visible_task(db: Session, slug: str, preview: int | None) -> Task | None:
    task = db.scalar(select(Task).where(Task.slug == slug))
    if task is None:
        return None
    if preview is not None:
        return task
    return task if task.published_version and not task.archived else None


def _work(db: Session, user: User, task: Task) -> TaskWork | None:
    return db.get(TaskWork, (user.id, task.id))


def list_tasks(db: Session, user: User) -> list[TaskCard]:
    cards = []
    tasks = db.scalars(select(Task).where(Task.published_version.is_not(None), Task.archived.is_(False)).order_by(Task.id))
    for task in tasks:
        work = _work(db, user, task)
        version = get_version(db, task.id, work.version_number if work else task.published_version)
        cards.append(TaskCard(
            slug=task.slug, title=version.spec["title"], kind=version.spec["kind"], version=version.number,
            started=work is not None, solved=bool(work and work.solved_at),
            has_update=bool(work and work.version_number < task.published_version),
        ))
    return cards


def for_learner(db: Session, user: User, task: Task, preview: int | None) -> TaskForLearner:
    work = None if preview is not None else _work(db, user, task)
    number = preview if preview is not None else (work.version_number if work else task.published_version)
    version = get_version(db, task.id, number)
    if version is None:
        raise TaskError("Нет такой версии задания")
    spec = TaskSpec.model_validate(version.spec)
    hints_used = work.hints_used if work else 0
    fragments = db.scalars(select(Fragment).options(joinedload(Fragment.source)).where(Fragment.id.in_(spec.fragment_ids))).all()
    return TaskForLearner(
        slug=task.slug,
        title=spec.title,
        kind=spec.kind,
        version=version.number,
        preview=preview is not None,
        statement_html=render_markdown(spec.statement),
        files=work.files if work else spec.starter,
        starter=spec.starter,
        tests=spec.tests,
        sql_setup=spec.sql_setup,
        sql_checks=spec.sql_checks,
        sql_expected=(version.check_report or {}).get("sql_expected", []),
        hints=spec.hints[:hints_used],
        hints_total=len(spec.hints),
        solved=bool(work and work.solved_at),
        has_update=bool(work and task.published_version and work.version_number < task.published_version),
        fragments=[{"id": f.id, "title": f.title, "source": f.source.title} for f in fragments],
    )


def _ensure_work(db: Session, user: User, task: Task) -> TaskWork:
    work = _work(db, user, task)
    if work is None:
        # Первое действие закрепляет за пользователем текущую версию задания
        spec = get_version(db, task.id, task.published_version).spec
        work = TaskWork(user_id=user.id, task_id=task.id, version_number=task.published_version, files=spec["starter"])
        db.add(work)
    return work


def save_work(db: Session, user: User, task: Task, files: dict) -> None:
    work = _ensure_work(db, user, task)
    allowed = set(get_version(db, task.id, work.version_number).spec["starter"])
    work.files = {name: code for name, code in files.items() if name in allowed}
    db.commit()


def reveal_hint(db: Session, user: User, task: Task) -> str | None:
    work = _ensure_work(db, user, task)
    hints = get_version(db, task.id, work.version_number).spec["hints"]
    if work.hints_used >= len(hints):
        return None
    work.hints_used += 1
    db.commit()
    return hints[work.hints_used - 1]


def record_attempt(db: Session, user: User, task: Task, payload: AttemptIn) -> None:
    work = _ensure_work(db, user, task)
    db.add(TaskAttempt(
        user_id=user.id, task_id=task.id, version_number=work.version_number,
        passed=payload.passed, results=payload.results, hints_used=work.hints_used, mentor_hints=work.mentor_hints,
    ))
    if payload.passed and not work.solved_at:
        work.solved_at = datetime.now(UTC)
    db.commit()


def reset_work(db: Session, user: User, task: Task) -> None:
    work = _ensure_work(db, user, task)
    work.files = get_version(db, task.id, work.version_number).spec["starter"]
    db.commit()


def upgrade(db: Session, user: User, task: Task) -> None:
    """Переход на новую версию задания: код остаётся, решённость сбрасывается — проверки могли поменяться."""
    work = _work(db, user, task)
    if work and task.published_version and work.version_number < task.published_version:
        work.version_number = task.published_version
        work.solved_at = None
        db.commit()
