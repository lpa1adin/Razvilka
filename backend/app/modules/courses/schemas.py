from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.modules.courses.models import VersionStatus
from app.modules.library.schemas import FragmentBrief, FragmentOut

# id частей курса создаёт интерфейс; они стабильны между версиями
ItemId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9-]{4,40}$")]
Title = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1500)]


class TheoryBlock(BaseModel):
    id: ItemId
    type: Literal["theory"] = "theory"
    fragment_id: int
    why: Note = ""  # заметка админа «зачем читать» — это не теория, теория берётся из источника


class PracticeBlock(BaseModel):
    id: ItemId
    type: Literal["practice"] = "practice"
    task_id: int


class QuizBlock(BaseModel):
    id: ItemId
    type: Literal["quiz"] = "quiz"
    topic_id: int


Block = Annotated[TheoryBlock | PracticeBlock | QuizBlock, Field(discriminator="type")]


class Lesson(BaseModel):
    id: ItemId
    title: Title
    goal: Note = ""
    blocks: list[Block] = Field(default_factory=list, max_length=30)


class Module(BaseModel):
    id: ItemId
    title: Title
    lessons: list[Lesson] = Field(default_factory=list, max_length=50)


class CourseContent(BaseModel):
    modules: list[Module] = Field(default_factory=list, max_length=30)


# ---------- Мастерская ----------


class CourseCreate(BaseModel):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    description: Note = ""


class DraftIn(BaseModel):
    number: int  # какую версию черновика правили — защита от перезаписи чужих правок
    title: Title
    description: Note = ""
    content: CourseContent


class PublishIn(BaseModel):
    change_note: Note = ""


class VersionOut(BaseModel):
    number: int
    status: VersionStatus
    title: str
    description: str
    content: CourseContent
    change_note: str
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None

    model_config = {"from_attributes": True}


class VersionBrief(BaseModel):
    number: int
    status: VersionStatus
    title: str
    change_note: str
    created_at: datetime
    published_at: datetime | None

    model_config = {"from_attributes": True}


class AdminCourseBrief(BaseModel):
    id: int
    slug: str
    title: str
    published_version: int | None
    draft_version: int | None
    archived: bool
    lessons: int
    updated_at: datetime


class AdminCourseOut(BaseModel):
    id: int
    slug: str
    published_version: int | None
    draft_version: int | None
    archived: bool
    editing: VersionOut
    fragments: dict[int, FragmentBrief]
    tasks: dict[int, dict]  # задания, на которые ссылаются уроки: название, вид, опубликовано ли
    quiz_topics: dict[int, dict]  # темы тестов из уроков


# ---------- Учёба ----------


class CourseCard(BaseModel):
    slug: str
    title: str
    description: str
    version: int
    lessons_total: int
    lessons_done: int
    next_lesson_id: str | None
    has_update: bool


class LessonRef(BaseModel):
    id: str
    title: str
    done: bool


class ModuleOut(BaseModel):
    id: str
    title: str
    lessons: list[LessonRef]


class CourseDetail(CourseCard):
    modules: list[ModuleOut]
    published_version: int | None
    preview: bool


class TheoryBlockOut(BaseModel):
    id: str
    type: Literal["theory"]
    why: str
    fragment: FragmentOut | None  # None — фрагмент удалили из библиотеки


class PracticeTaskRef(BaseModel):
    slug: str
    title: str
    kind: str
    solved: bool


class PracticeBlockOut(BaseModel):
    id: str
    type: Literal["practice"]
    task: PracticeTaskRef | None  # None — задание сняли с публикации


class QuizRef(BaseModel):
    id: str
    topic: dict | None  # {slug, title, questions} — None, если тему сняли с публикации


class LessonDetail(BaseModel):
    course_slug: str
    course_title: str
    version: int
    preview: bool
    module_title: str
    id: str
    title: str
    goal: str
    blocks: list[TheoryBlockOut]
    practice: list[PracticeBlockOut]
    quizzes: list[QuizRef]
    done: bool
    prev_lesson: LessonRef | None
    next_lesson: LessonRef | None
