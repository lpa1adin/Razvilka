from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.modules.auth.deps import AdminUser, CurrentUser, Db
from app.modules.auth.models import Role, User
from app.modules.courses import service
from app.modules.courses.models import Course, CourseVersion
from app.modules.courses.schemas import (
    AdminCourseBrief,
    AdminCourseOut,
    CourseCard,
    CourseCreate,
    CourseDetail,
    DraftIn,
    LessonDetail,
    PublishIn,
    VersionBrief,
    VersionOut,
)
from app.modules.library.models import Fragment
from app.modules.practice.models import Task
from app.modules.practice.service import editing_version as task_editing_version
from app.modules.quiz.models import QuizTopic
from app.modules.library.service import fragment_brief

router = APIRouter(prefix="/api/courses", tags=["courses"])
admin_router = APIRouter(prefix="/api/workshop/courses", tags=["workshop"])


def _preview(user: User, version: int | None) -> int | None:
    # Смотреть черновики и старые версии «глазами пользователя» может только админ
    if version is not None and user.role is not Role.admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Предпросмотр версий доступен только администратору")
    return version


def _course_or_404(db: Db, slug: str, user: User, preview: int | None) -> Course:
    course = service.visible_course(db, slug, user, preview)
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Курс не найден или снят с публикации")
    return course


def _error(exc: service.CourseError, code: int = status.HTTP_409_CONFLICT) -> HTTPException:
    return HTTPException(code, str(exc))


@router.get("", response_model=list[CourseCard])
def list_courses(db: Db, user: CurrentUser):
    return service.list_courses(db, user)


@router.get("/{slug}", response_model=CourseDetail)
def get_course(slug: str, db: Db, user: CurrentUser, version: int | None = Query(None)):
    preview = _preview(user, version)
    try:
        return service.course_detail(db, user, _course_or_404(db, slug, user, preview), preview)
    except service.CourseError as exc:
        raise _error(exc, status.HTTP_404_NOT_FOUND) from exc


@router.get("/{slug}/lessons/{lesson_id}", response_model=LessonDetail)
def get_lesson(slug: str, lesson_id: str, db: Db, user: CurrentUser, version: int | None = Query(None)):
    preview = _preview(user, version)
    try:
        lesson = service.lesson_detail(db, user, _course_or_404(db, slug, user, preview), lesson_id, preview)
    except service.CourseError as exc:
        raise _error(exc, status.HTTP_404_NOT_FOUND) from exc
    if lesson is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Такого урока нет в курсе")
    return lesson


@router.put("/{slug}/lessons/{lesson_id}/done", status_code=status.HTTP_204_NO_CONTENT)
def mark_done(slug: str, lesson_id: str, db: Db, user: CurrentUser):
    try:
        service.set_done(db, user, _course_or_404(db, slug, user, None), lesson_id, True)
    except service.CourseError as exc:
        raise _error(exc, status.HTTP_404_NOT_FOUND) from exc


@router.delete("/{slug}/lessons/{lesson_id}/done", status_code=status.HTTP_204_NO_CONTENT)
def unmark_done(slug: str, lesson_id: str, db: Db, user: CurrentUser):
    try:
        service.set_done(db, user, _course_or_404(db, slug, user, None), lesson_id, False)
    except service.CourseError as exc:
        raise _error(exc, status.HTTP_404_NOT_FOUND) from exc


@router.post("/{slug}/upgrade", status_code=status.HTTP_204_NO_CONTENT)
def upgrade(slug: str, db: Db, user: CurrentUser):
    service.upgrade(db, user, _course_or_404(db, slug, user, None))


# ---------- Мастерская ----------


def _admin_course(db: Db, course_id: int) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Курс не найден")
    return course


def _admin_out(db: Db, course: Course) -> AdminCourseOut:
    version = service.editing_version(db, course)
    ids = service.fragment_ids(version.content)
    fragments = db.scalars(select(Fragment).where(Fragment.id.in_(ids))).all() if ids else []
    return AdminCourseOut(
        id=course.id,
        slug=course.slug,
        published_version=course.published_version,
        draft_version=course.draft_version,
        archived=course.archived,
        editing=VersionOut.model_validate(version),
        fragments={f.id: fragment_brief(f) for f in fragments},
        tasks=_task_briefs(db, service.task_ids(version.content)),
        quiz_topics={
            t.id: {"title": t.title, "published": t.published}
            for t in db.scalars(select(QuizTopic).where(QuizTopic.id.in_(service.quiz_topic_ids(version.content))))
        },
    )


def _task_briefs(db: Db, ids: set[int]) -> dict[int, dict]:
    result = {}
    for task in db.scalars(select(Task).where(Task.id.in_(ids))) if ids else []:
        spec = task_editing_version(db, task).spec
        result[task.id] = {"title": spec["title"], "kind": spec["kind"], "published": bool(task.published_version and not task.archived)}
    return result


@admin_router.get("", response_model=list[AdminCourseBrief])
def admin_list(db: Db, _: AdminUser):
    result = []
    for course in db.scalars(select(Course).order_by(Course.updated_at.desc())):
        version = service.editing_version(db, course)
        result.append(AdminCourseBrief(
            id=course.id, slug=course.slug, title=version.title, published_version=course.published_version,
            draft_version=course.draft_version, archived=course.archived,
            lessons=sum(1 for _ in service.lessons(version.content)), updated_at=version.updated_at,
        ))
    return result


@admin_router.post("", response_model=AdminCourseOut, status_code=status.HTTP_201_CREATED)
def admin_create(payload: CourseCreate, db: Db, admin: AdminUser):
    return _admin_out(db, service.create_course(db, payload.title, payload.description, admin))


@admin_router.get("/{course_id}", response_model=AdminCourseOut)
def admin_get(course_id: int, db: Db, _: AdminUser):
    return _admin_out(db, _admin_course(db, course_id))


@admin_router.post("/{course_id}/draft", response_model=AdminCourseOut)
def admin_start_draft(course_id: int, db: Db, admin: AdminUser):
    course = _admin_course(db, course_id)
    service.start_draft(db, course, admin)
    return _admin_out(db, course)


@admin_router.put("/{course_id}/draft", response_model=AdminCourseOut)
def admin_save_draft(course_id: int, payload: DraftIn, db: Db, _: AdminUser):
    course = _admin_course(db, course_id)
    try:
        service.save_draft(db, course, payload)
    except service.CourseError as exc:
        raise _error(exc) from exc
    return _admin_out(db, course)


@admin_router.delete("/{course_id}/draft", response_model=AdminCourseOut)
def admin_discard_draft(course_id: int, db: Db, _: AdminUser):
    course = _admin_course(db, course_id)
    try:
        service.discard_draft(db, course)
    except service.CourseError as exc:
        raise _error(exc) from exc
    return _admin_out(db, course)


@admin_router.post("/{course_id}/publish", response_model=AdminCourseOut)
def admin_publish(course_id: int, payload: PublishIn, db: Db, admin: AdminUser):
    course = _admin_course(db, course_id)
    if not course.draft_version:
        raise HTTPException(status.HTTP_409_CONFLICT, "Публиковать нечего: черновика нет")
    problems = service.publish_problems(db, service.get_version(db, course.id, course.draft_version))
    if problems:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"detail": "Курс пока нельзя опубликовать", "problems": problems},
        )
    service.publish(db, course, admin, payload.change_note)
    return _admin_out(db, course)


@admin_router.post("/{course_id}/archive", response_model=AdminCourseOut)
def admin_archive(course_id: int, db: Db, _: AdminUser, archived: bool = Query(True)):
    course = _admin_course(db, course_id)
    course.archived = archived
    db.commit()
    return _admin_out(db, course)


@admin_router.delete("/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_delete(course_id: int, db: Db, _: AdminUser):
    try:
        service.delete_course(db, _admin_course(db, course_id))
    except service.CourseError as exc:
        raise _error(exc) from exc


@admin_router.get("/{course_id}/versions", response_model=list[VersionBrief])
def admin_versions(course_id: int, db: Db, _: AdminUser):
    _admin_course(db, course_id)
    return db.scalars(select(CourseVersion).where(CourseVersion.course_id == course_id).order_by(CourseVersion.number.desc())).all()


# ---------- Мастерская: статьи, изменившиеся в источнике ----------

review_router = APIRouter(prefix="/api/workshop/fragments", tags=["workshop"])


@review_router.get("/review")
def fragments_to_review(db: Db, _: AdminUser):
    usage = service.fragment_usage(db)
    rows = db.scalars(select(Fragment).where(Fragment.needs_review.is_(True)).order_by(Fragment.changed_at.desc()))
    return [{**fragment_brief(f).model_dump(), "changed_at": f.changed_at, "used_in": usage.get(f.id, [])} for f in rows]


@review_router.post("/{fragment_id}/reviewed", status_code=status.HTTP_204_NO_CONTENT)
def mark_reviewed(fragment_id: int, db: Db, _: AdminUser):
    fragment = db.get(Fragment, fragment_id)
    if fragment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Такого фрагмента нет")
    fragment.needs_review = False
    db.commit()
