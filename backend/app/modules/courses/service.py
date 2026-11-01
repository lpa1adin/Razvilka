import re
from collections.abc import Iterator
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.modules.auth.models import User
from app.modules.courses.models import Course, CourseVersion, Enrollment, LessonProgress, VersionStatus
from app.modules.courses.schemas import (
    CourseCard,
    CourseContent,
    CourseDetail,
    DraftIn,
    LessonDetail,
    LessonRef,
    ModuleOut,
    PracticeBlockOut,
    PracticeTaskRef,
    QuizRef,
    TheoryBlockOut,
)
from app.modules.library.models import Fragment, FragmentStatus
from app.modules.library.service import fragment_out
from app.modules.practice.models import Task, TaskVersion, TaskWork
from app.modules.quiz.models import Question, QuestionStatus, QuizTopic


class CourseError(Exception):
    """Ошибка, которую можно показать админу как есть."""


# ---------- общее ----------

_TRANSLIT = dict(zip(
    "абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
    ["a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r", "s", "t", "u", "f",
     "h", "ts", "ch", "sh", "sch", "", "y", "", "e", "yu", "ya"],
))


def slugify(title: str) -> str:
    text = "".join(_TRANSLIT.get(ch, ch) for ch in title.lower())
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:60] or "course"


def unique_slug(db: Session, title: str) -> str:
    base = slugify(title)
    slug, n = base, 2
    while db.scalar(select(Course.id).where(Course.slug == slug)):
        slug, n = f"{base}-{n}", n + 1
    return slug


def get_version(db: Session, course_id: int, number: int) -> CourseVersion | None:
    return db.scalar(select(CourseVersion).where(CourseVersion.course_id == course_id, CourseVersion.number == number))


def lessons(content: dict) -> Iterator[tuple[dict, dict]]:
    for module in content.get("modules", []):
        for lesson in module.get("lessons", []):
            yield module, lesson


def task_ids(content: dict) -> set[int]:
    return {b["task_id"] for _, lesson in lessons(content) for b in lesson.get("blocks", []) if b.get("type") == "practice"}


def quiz_topic_ids(content: dict) -> set[int]:
    return {b["topic_id"] for _, lesson in lessons(content) for b in lesson.get("blocks", []) if b.get("type") == "quiz"}


def fragment_ids(content: dict) -> set[int]:
    return {b["fragment_id"] for _, lesson in lessons(content) for b in lesson.get("blocks", []) if b.get("type") == "theory"}


# ---------- Мастерская ----------


def create_course(db: Session, title: str, description: str, admin: User) -> Course:
    course = Course(slug=unique_slug(db, title), draft_version=1)
    db.add(course)
    db.flush()
    db.add(CourseVersion(
        course_id=course.id, number=1, status=VersionStatus.draft, title=title, description=description,
        content=CourseContent().model_dump(), created_by=admin.id,
    ))
    db.commit()
    return course


def editing_version(db: Session, course: Course) -> CourseVersion:
    number = course.draft_version or course.published_version
    version = get_version(db, course.id, number) if number else None
    if version is None:
        raise CourseError("У курса нет ни черновика, ни опубликованной версии")
    return version


def start_draft(db: Session, course: Course, admin: User) -> CourseVersion:
    """Правка опубликованного курса начинается с копии — опубликованная версия не меняется."""
    if course.draft_version:
        return get_version(db, course.id, course.draft_version)
    published = editing_version(db, course)
    last = db.scalar(select(CourseVersion.number).where(CourseVersion.course_id == course.id).order_by(CourseVersion.number.desc()))
    draft = CourseVersion(
        course_id=course.id, number=last + 1, status=VersionStatus.draft, title=published.title,
        description=published.description, content=published.content, created_by=admin.id,
    )
    db.add(draft)
    course.draft_version = draft.number
    db.commit()
    return draft


def save_draft(db: Session, course: Course, payload: DraftIn) -> CourseVersion:
    if not course.draft_version:
        raise CourseError("Черновика нет — сначала нажмите «Редактировать»")
    if payload.number != course.draft_version:
        raise CourseError("Черновик уже изменился в другой вкладке. Обновите страницу, чтобы не потерять чужие правки.")
    draft = get_version(db, course.id, course.draft_version)
    draft.title = payload.title or "Без названия"
    draft.description = payload.description
    draft.content = payload.content.model_dump()
    db.commit()
    return draft


def publish_problems(db: Session, version: CourseVersion) -> list[str]:
    """Что мешает публикации — человеческими словами, с адресом места."""
    problems = []
    content = CourseContent.model_validate(version.content)
    if not version.title.strip():
        problems.append("У курса нет названия.")
    if not content.modules:
        problems.append("В курсе нет ни одного модуля.")

    ids = [m.id for m in content.modules] + [l.id for m in content.modules for l in m.lessons]
    if len(ids) != len(set(ids)):
        problems.append("Повторяются внутренние id модулей или уроков — пересоздайте повторяющийся элемент.")

    fragments = {
        f.id: f for f in db.scalars(select(Fragment).where(Fragment.id.in_(fragment_ids(version.content))))
    }
    tasks = {t.id: t for t in db.scalars(select(Task).where(Task.id.in_(task_ids(version.content))))}
    topics = {t.id: t for t in db.scalars(select(QuizTopic).where(QuizTopic.id.in_(quiz_topic_ids(version.content))))}
    for mi, module in enumerate(content.modules, 1):
        where = f"Модуль {mi} «{module.title or 'без названия'}»"
        if not module.title:
            problems.append(f"{where}: нет названия.")
        if not module.lessons:
            problems.append(f"{where}: нет ни одного урока.")
        for li, lesson in enumerate(module.lessons, 1):
            at = f"{where}, урок {li} «{lesson.title or 'без названия'}»"
            if not lesson.title:
                problems.append(f"{at}: нет названия.")
            if not any(b.type == "theory" for b in lesson.blocks):
                problems.append(f"{at}: нет ни одного блока теории.")
            for block in lesson.blocks:
                if block.type == "quiz":
                    topic = topics.get(block.topic_id)
                    if topic is None or not topic.published:
                        problems.append(f"{at}: тема теста №{block.topic_id} не опубликована.")
                    continue
                if block.type == "practice":
                    task = tasks.get(block.task_id)
                    if task is None or not task.published_version or task.archived:
                        problems.append(f"{at}: задание №{block.task_id} не опубликовано — опубликуйте его или уберите из урока.")
                    continue
                fragment = fragments.get(block.fragment_id)
                if fragment is None:
                    problems.append(f"{at}: фрагмент №{block.fragment_id} не найден в библиотеке.")
                elif fragment.status is FragmentStatus.removed:
                    problems.append(f"{at}: статья «{fragment.title}» удалена из источника — замените её.")
    return problems


def publish(db: Session, course: Course, admin: User, change_note: str) -> CourseVersion:
    if not course.draft_version:
        raise CourseError("Публиковать нечего: черновика нет")
    draft = get_version(db, course.id, course.draft_version)
    if course.published_version:
        get_version(db, course.id, course.published_version).status = VersionStatus.superseded
    draft.status = VersionStatus.published
    draft.published_at = datetime.now(UTC)
    draft.published_by = admin.id
    draft.change_note = change_note
    course.published_version = draft.number
    course.draft_version = None
    db.commit()
    return draft


def discard_draft(db: Session, course: Course) -> None:
    if not course.draft_version:
        return
    if not course.published_version:
        raise CourseError("Курс ещё не публиковался — удалите его целиком, если он не нужен")
    db.delete(get_version(db, course.id, course.draft_version))
    course.draft_version = None
    db.commit()


def delete_course(db: Session, course: Course) -> None:
    ever_published = db.scalar(
        select(CourseVersion.id).where(CourseVersion.course_id == course.id, CourseVersion.status != VersionStatus.draft)
    )
    if ever_published:
        raise CourseError("Курс уже публиковался, у пользователей может быть прогресс. Снимите его с публикации вместо удаления.")
    db.delete(course)
    db.commit()


def fragment_usage(db: Session) -> dict[int, list[dict]]:
    """Где используется каждый фрагмент: в опубликованных версиях и черновиках."""
    usage: dict[int, list[dict]] = {}
    rows = db.execute(
        select(CourseVersion, Course)
        .join(Course, Course.id == CourseVersion.course_id)
        .where(CourseVersion.status.in_([VersionStatus.draft, VersionStatus.published]))
    ).all()
    for version, course in rows:
        for _, lesson in lessons(version.content):
            for block in lesson.get("blocks", []):
                if block.get("type") != "theory":
                    continue
                usage.setdefault(block["fragment_id"], []).append({
                    "course_id": course.id,
                    "course_title": version.title,
                    "lesson_title": lesson["title"],
                    "draft": version.status is VersionStatus.draft,
                })
    return usage


# ---------- Учёба ----------


def _version_for(db: Session, user: User, course: Course, preview: int | None) -> tuple[CourseVersion, Enrollment | None]:
    if preview is not None:
        version = get_version(db, course.id, preview)
        if version is None:
            raise CourseError("Нет такой версии курса")
        return version, None
    enrollment = db.get(Enrollment, (user.id, course.id))
    number = enrollment.version_number if enrollment else course.published_version
    return get_version(db, course.id, number), enrollment


def _done_ids(db: Session, user: User, course: Course) -> set[str]:
    return set(db.scalars(select(LessonProgress.lesson_id).where(
        LessonProgress.user_id == user.id, LessonProgress.course_id == course.id
    )))


def _card(course: Course, version: CourseVersion, enrollment: Enrollment | None, done: set[str]) -> CourseCard:
    lesson_ids = [lesson["id"] for _, lesson in lessons(version.content)]
    return CourseCard(
        slug=course.slug,
        title=version.title,
        description=version.description,
        version=version.number,
        lessons_total=len(lesson_ids),
        lessons_done=sum(1 for i in lesson_ids if i in done),
        next_lesson_id=next((i for i in lesson_ids if i not in done), None),
        has_update=bool(enrollment and course.published_version and enrollment.version_number < course.published_version),
    )


def visible_course(db: Session, slug: str, user: User, preview: int | None) -> Course | None:
    course = db.scalar(select(Course).where(Course.slug == slug))
    if course is None:
        return None
    if preview is not None:
        return course  # предпросмотр проверяется на админа в роутере
    return course if course.published_version and not course.archived else None


def list_courses(db: Session, user: User) -> list[CourseCard]:
    cards = []
    for course in db.scalars(select(Course).where(Course.published_version.is_not(None), Course.archived.is_(False)).order_by(Course.id)):
        version, enrollment = _version_for(db, user, course, None)
        cards.append(_card(course, version, enrollment, _done_ids(db, user, course)))
    return cards


def course_detail(db: Session, user: User, course: Course, preview: int | None) -> CourseDetail:
    version, enrollment = _version_for(db, user, course, preview)
    done = _done_ids(db, user, course)
    card = _card(course, version, enrollment, done)
    modules = [
        ModuleOut(id=m["id"], title=m["title"], lessons=[LessonRef(id=l["id"], title=l["title"], done=l["id"] in done) for l in m["lessons"]])
        for m in version.content.get("modules", [])
    ]
    return CourseDetail(**card.model_dump(), modules=modules, published_version=course.published_version, preview=preview is not None)


def lesson_detail(db: Session, user: User, course: Course, lesson_id: str, preview: int | None) -> LessonDetail | None:
    version, _ = _version_for(db, user, course, preview)
    flat = list(lessons(version.content))
    index = next((i for i, (_, l) in enumerate(flat) if l["id"] == lesson_id), None)
    if index is None:
        return None
    module, lesson = flat[index]
    done = _done_ids(db, user, course)

    theory = [b for b in lesson.get("blocks", []) if b.get("type") == "theory"]
    practice = [b for b in lesson.get("blocks", []) if b.get("type") == "practice"]
    quiz_blocks = [b for b in lesson.get("blocks", []) if b.get("type") == "quiz"]
    quiz_topics = {t.id: t for t in db.scalars(select(QuizTopic).where(QuizTopic.id.in_([b["topic_id"] for b in quiz_blocks]), QuizTopic.published.is_(True)))}

    def quiz_ref(block: dict) -> QuizRef:
        topic = quiz_topics.get(block["topic_id"])
        if topic is None:
            return QuizRef(id=block["id"], topic=None)
        count = db.scalar(select(func.count()).select_from(Question).where(Question.topic_id == topic.id, Question.status == QuestionStatus.published))
        return QuizRef(id=block["id"], topic={"slug": topic.slug, "title": topic.title, "questions": count, "size": topic.size})
    ids = [b["fragment_id"] for b in theory]
    fragments = {f.id: f for f in db.scalars(select(Fragment).options(joinedload(Fragment.source)).where(Fragment.id.in_(ids)))}
    tasks = {
        t.id: t for t in db.scalars(select(Task).where(Task.id.in_([b["task_id"] for b in practice])))
        if t.published_version and not t.archived
    }

    def task_ref(task_id: int) -> PracticeTaskRef | None:
        task = tasks.get(task_id)
        if task is None:
            return None
        work = db.get(TaskWork, (user.id, task.id))
        number = work.version_number if work else task.published_version
        spec = db.scalar(select(TaskVersion.spec).where(TaskVersion.task_id == task.id, TaskVersion.number == number))
        return PracticeTaskRef(slug=task.slug, title=spec["title"], kind=spec["kind"], solved=bool(work and work.solved_at))

    def ref(i: int) -> LessonRef | None:
        if 0 <= i < len(flat):
            item = flat[i][1]
            return LessonRef(id=item["id"], title=item["title"], done=item["id"] in done)
        return None

    return LessonDetail(
        course_slug=course.slug,
        course_title=version.title,
        version=version.number,
        preview=preview is not None,
        module_title=module["title"],
        id=lesson["id"],
        title=lesson["title"],
        goal=lesson.get("goal", ""),
        blocks=[
            TheoryBlockOut(
                id=b["id"], type="theory", why=b.get("why", ""),
                fragment=fragment_out(fragments[b["fragment_id"]]) if b["fragment_id"] in fragments else None,
            )
            for b in theory
        ],
        practice=[PracticeBlockOut(id=b["id"], type="practice", task=task_ref(b["task_id"])) for b in practice],
        quizzes=[quiz_ref(b) for b in quiz_blocks],
        done=lesson["id"] in done,
        prev_lesson=ref(index - 1),
        next_lesson=ref(index + 1),
    )


def set_done(db: Session, user: User, course: Course, lesson_id: str, done: bool) -> None:
    version, enrollment = _version_for(db, user, course, None)
    if lesson_id not in {l["id"] for _, l in lessons(version.content)}:
        raise CourseError("В вашей версии курса нет такого урока")
    if enrollment is None:
        # Первое действие в курсе закрепляет за пользователем текущую версию
        db.add(Enrollment(user_id=user.id, course_id=course.id, version_number=version.number))
    existing = db.get(LessonProgress, (user.id, course.id, lesson_id))
    if done and existing is None:
        db.add(LessonProgress(user_id=user.id, course_id=course.id, lesson_id=lesson_id))
    elif not done and existing is not None:
        db.delete(existing)
    db.commit()


def upgrade(db: Session, user: User, course: Course) -> None:
    enrollment = db.get(Enrollment, (user.id, course.id))
    if enrollment and course.published_version:
        enrollment.version_number = course.published_version
        db.commit()
