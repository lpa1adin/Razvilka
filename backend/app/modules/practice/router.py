from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import select

from app.modules.auth.deps import AdminUser, CurrentUser, Db
from app.modules.auth.models import Role, User
from app.modules.courses.schemas import PublishIn
from app.modules.practice import service
from app.modules.practice.models import Task, TaskVersion
from app.modules.practice.schemas import (
    AdminTaskBrief,
    AdminTaskOut,
    AttemptIn,
    TaskCard,
    TaskCreate,
    TaskDraftIn,
    TaskForLearner,
    WorkIn,
)
from app.modules.review import service as review_service

router = APIRouter(prefix="/api/practice", tags=["practice"])
admin_router = APIRouter(prefix="/api/workshop/tasks", tags=["workshop"])

HARNESS_DIR = Path(__file__).parent / "harness"
HARNESS = {"web": "web_harness.js", "python": "py_harness.py"}


def _preview(user: User, version: int | None) -> int | None:
    if version is not None and user.role is not Role.admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Предпросмотр версий доступен только администратору")
    return version


def _task_or_404(db: Db, slug: str, preview: int | None = None) -> Task:
    task = service.visible_task(db, slug, preview)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Задание не найдено или снято с публикации")
    return task


@router.get("/harness/{name}", response_class=PlainTextResponse)
def harness(name: str, _: CurrentUser):
    """Код проверок отдаётся интерфейсу из одного места — тем же файлом пользуется runner."""
    if name not in HARNESS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Нет такого набора проверок")
    return (HARNESS_DIR / HARNESS[name]).read_text(encoding="utf-8")


@router.get("/tasks", response_model=list[TaskCard])
def list_tasks(db: Db, user: CurrentUser):
    return service.list_tasks(db, user)


@router.get("/tasks/{slug}", response_model=TaskForLearner)
def get_task(slug: str, db: Db, user: CurrentUser, version: int | None = Query(None)):
    preview = _preview(user, version)
    try:
        return service.for_learner(db, user, _task_or_404(db, slug, preview), preview)
    except service.TaskError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.put("/tasks/{slug}/work", status_code=status.HTTP_204_NO_CONTENT)
def save_work(slug: str, payload: WorkIn, db: Db, user: CurrentUser):
    service.save_work(db, user, _task_or_404(db, slug), payload.files)


@router.post("/tasks/{slug}/hint")
def hint(slug: str, db: Db, user: CurrentUser):
    text = service.reveal_hint(db, user, _task_or_404(db, slug))
    if text is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Подсказок больше нет")
    return {"hint": text}


@router.post("/tasks/{slug}/attempts", status_code=status.HTTP_204_NO_CONTENT)
def attempt(slug: str, payload: AttemptIn, db: Db, user: CurrentUser):
    service.record_attempt(db, user, _task_or_404(db, slug), payload)


@router.post("/tasks/{slug}/reset", status_code=status.HTTP_204_NO_CONTENT)
def reset(slug: str, db: Db, user: CurrentUser):
    service.reset_work(db, user, _task_or_404(db, slug))


@router.post("/tasks/{slug}/upgrade", status_code=status.HTTP_204_NO_CONTENT)
def upgrade(slug: str, db: Db, user: CurrentUser):
    service.upgrade(db, user, _task_or_404(db, slug))


# ---------- Мастерская ----------


def _admin_task(db: Db, task_id: int) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Задание не найдено")
    return task


def _out(db: Db, task: Task) -> AdminTaskOut:
    return AdminTaskOut(
        id=task.id, slug=task.slug, published_version=task.published_version, draft_version=task.draft_version,
        archived=task.archived, editing=service.version_out(service.editing_version(db, task)),
    )


def _conflict(exc: Exception) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, str(exc))


@admin_router.get("", response_model=list[AdminTaskBrief])
def admin_list(db: Db, _: AdminUser):
    result = []
    for task in db.scalars(select(Task).order_by(Task.updated_at.desc())):
        version = service.editing_version(db, task)
        result.append(AdminTaskBrief(
            id=task.id, slug=task.slug, title=version.spec["title"], kind=version.spec["kind"],
            published_version=task.published_version, draft_version=task.draft_version, archived=task.archived,
            check_status=version.check_status, updated_at=version.updated_at,
        ))
    return result


@admin_router.post("", response_model=AdminTaskOut, status_code=status.HTTP_201_CREATED)
def admin_create(payload: TaskCreate, db: Db, admin: AdminUser):
    return _out(db, service.create_task(db, payload.title, payload.kind, admin))


@admin_router.get("/{task_id}", response_model=AdminTaskOut)
def admin_get(task_id: int, db: Db, _: AdminUser):
    return _out(db, _admin_task(db, task_id))


@admin_router.post("/{task_id}/draft", response_model=AdminTaskOut)
def admin_start_draft(task_id: int, db: Db, admin: AdminUser):
    task = _admin_task(db, task_id)
    service.start_draft(db, task, admin)
    return _out(db, task)


@admin_router.put("/{task_id}/draft", response_model=AdminTaskOut)
def admin_save(task_id: int, payload: TaskDraftIn, db: Db, _: AdminUser):
    task = _admin_task(db, task_id)
    try:
        service.save_draft(db, task, payload)
    except service.TaskError as exc:
        raise _conflict(exc) from exc
    return _out(db, task)


@admin_router.delete("/{task_id}/draft", response_model=AdminTaskOut)
def admin_discard(task_id: int, db: Db, _: AdminUser):
    task = _admin_task(db, task_id)
    if not task.draft_version:
        return _out(db, task)
    if not task.published_version:
        raise _conflict("Задание ещё не публиковалось — удалите его целиком, если оно не нужно")
    db.delete(service.get_version(db, task.id, task.draft_version))
    task.draft_version = None
    db.commit()
    return _out(db, task)


@admin_router.post("/{task_id}/check", response_model=AdminTaskOut)
def admin_check(task_id: int, db: Db, _: AdminUser):
    task = _admin_task(db, task_id)
    try:
        service.request_check(db, task)
    except service.TaskError as exc:
        raise _conflict(exc) from exc
    return _out(db, task)


@admin_router.post("/{task_id}/publish", response_model=AdminTaskOut)
def admin_publish(task_id: int, payload: PublishIn, db: Db, _: AdminUser):
    task = _admin_task(db, task_id)
    if not task.draft_version:
        raise _conflict("Публиковать нечего: черновика нет")
    problems = service.publish_problems(db, service.get_version(db, task.id, task.draft_version))
    # Автопроверка эталона Ревьюером (BRIEF §5.10, п. 4): эталон не должен учить плохому
    problems += review_service.reference_problems(db, task)
    if problems:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"detail": "Задание пока нельзя опубликовать", "problems": problems},
        )
    service.publish(db, task, payload.change_note)
    return _out(db, task)


@admin_router.post("/{task_id}/archive", response_model=AdminTaskOut)
def admin_archive(task_id: int, db: Db, _: AdminUser, archived: bool = Query(True)):
    task = _admin_task(db, task_id)
    task.archived = archived
    db.commit()
    return _out(db, task)


@admin_router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_delete(task_id: int, db: Db, _: AdminUser):
    task = _admin_task(db, task_id)
    if task.published_version or db.scalar(select(TaskVersion.id).where(TaskVersion.task_id == task.id, TaskVersion.published_at.is_not(None))):
        raise _conflict("Задание уже публиковалось, у пользователей может быть решение. Снимите его с публикации вместо удаления.")
    db.delete(task)
    db.commit()
