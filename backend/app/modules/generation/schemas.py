from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.modules.generation.models import GenStatus, GenWhat
from app.modules.practice.schemas import Kind, SqlCheck

Short = Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)]
Long = Annotated[str, StringConstraints(strip_whitespace=True, max_length=3000)]

# ---------- План: его предлагает Claude, правит и утверждает админ ----------


class PlanPractice(BaseModel):
    kind: Kind = Field(description="web — HTML/CSS/JS, python, sql")
    idea: Long = Field(description="Что ученик сделает руками и как это проверят автотесты, 1–3 предложения")


class PlanFork(BaseModel):
    question: Short = Field(description="Развилка: какое решение автор проекта принимал на этом этапе")
    context: Long = Field("", description="Что известно о задаче: масштаб, ограничения — без ответа автора")


class PlanLesson(BaseModel):
    id: str = Field("", description="Оставь пустым — заполнит платформа")
    title: Short
    goal: Long = Field(description="Что ученик поймёт и сможет после урока")
    files: list[Short] = Field(default_factory=list, max_length=12, description="Файлы проекта, на которых построен урок")
    fragment_ids: list[int] = Field(default_factory=list, max_length=6, description="id статей из library_search")
    practice: PlanPractice | None = Field(None, description="Практическое задание урока, если оно нужно")
    quiz: int = Field(0, ge=0, le=15, description="Сколько вопросов в банк теста модуля написать по теории урока")
    forks: list[PlanFork] = Field(default_factory=list, max_length=3, description="Только для пути: развилки этапа")


class PlanModule(BaseModel):
    id: str = Field("", description="Оставь пустым — заполнит платформа")
    title: Short
    lessons: list[PlanLesson] = Field(min_length=1, max_length=12)


class RoleNote(BaseModel):
    path: Short = Field(description="Файл или папка проекта")
    role: Long = Field(description="Какую роль играет в проекте, одно-два предложения")


class Plan(BaseModel):
    title: Short
    description: Long = Field(description="Описание для ученика: о чём курс и что он умеет после")
    summary: Long = Field("", description="Для админа: что в проекте, на чём построен план и чего в нём нет")
    modules: list[PlanModule] = Field(min_length=1, max_length=8)
    roles: list[RoleNote] = Field(default_factory=list, max_length=40, description="Только для пути: роль каждой важной части проекта")


# ---------- Черновик урока: ответ Claude по одному уроку ----------


class DraftTheory(BaseModel):
    fragment_id: int
    why: Short = Field(description="Зачем читать эту статью именно в этом уроке, одно предложение")


class DraftOption(BaseModel):
    id: Annotated[str, StringConstraints(pattern=r"^[a-z0-9_-]{1,20}$")]
    text: Annotated[str, StringConstraints(max_length=500)]


class DraftOptions(BaseModel):
    items: list[DraftOption] | None = Field(None, description="single / multiple / order")
    left: list[DraftOption] | None = Field(None, description="match: левый столбец")
    right: list[DraftOption] | None = Field(None, description="match: правый столбец")


class DraftAnswer(BaseModel):
    correct: list[str] | None = Field(None, description="single / multiple: id верных вариантов")
    order: list[str] | None = Field(None, description="order: id пунктов в правильном порядке")
    pairs: dict[str, str] | None = Field(None, description="match: id слева → id справа")


class DraftQuestion(BaseModel):
    type: Literal["single", "multiple", "order", "match"]
    prompt: Annotated[str, StringConstraints(max_length=2000)]
    code: Annotated[str, StringConstraints(max_length=6000)] = ""
    code_lang: Annotated[str, StringConstraints(max_length=20)] = ""
    options: DraftOptions
    answer: DraftAnswer
    explanation: Annotated[str, StringConstraints(max_length=2000)]
    fragment_id: int = Field(description="Статья, где разобран ответ на вопрос")
    difficulty: int = Field(2, ge=1, le=3)


class DraftTask(BaseModel):
    kind: Kind
    title: Short
    statement: Annotated[str, StringConstraints(max_length=8000)] = Field(description="Условие в markdown")
    starter: dict[str, str]
    solution: dict[str, str]
    tests: str = ""
    sql_setup: str = ""
    sql_checks: list[SqlCheck] = Field(default_factory=list, max_length=30)
    hints: list[Annotated[str, StringConstraints(max_length=1500)]] = Field(default_factory=list, max_length=5)


class LessonDraft(BaseModel):
    theory: list[DraftTheory] = Field(min_length=1, max_length=6)
    task: DraftTask | None = None
    questions: list[DraftQuestion] = Field(default_factory=list, max_length=15)


class TaskFix(BaseModel):
    task: DraftTask
    note: Short = Field(description="Что исправлено, одной фразой")


# ---------- API ----------


class RequestIn(BaseModel):
    what: GenWhat = GenWhat.course
    project: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] = ""
    focus: Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] = ""
    topic: Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] = ""
    level: int = Field(2, ge=1, le=3)
    notes: Annotated[str, StringConstraints(strip_whitespace=True, max_length=3000)] = ""


class TopicProposalIn(BaseModel):
    """Заявка пользователя на тему — из чата с наставником."""

    topic: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=300)]
    notes: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1500)] = ""


class ReplanIn(BaseModel):
    feedback: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=3000)]


class RedoIn(BaseModel):
    instruction: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=1500)]


class Step(BaseModel):
    key: str
    label: str
    state: Literal["pending", "running", "done", "failed", "skipped"]
    detail: str = ""


class CreatedTask(BaseModel):
    id: int
    slug: str
    title: str
    kind: str
    draft_version: int | None
    published: bool
    check_status: str
    check_summary: str
    review_verdict: str | None = None  # pass | changes_requested — ревью эталона этой редакции
    review_summary: str = ""


class CreatedLesson(BaseModel):
    id: str
    title: str
    task: CreatedTask | None
    questions: int
    questions_published: int
    theory: list[dict]  # [{id, title, source}]
    notes: list[str]
    stage: dict | None = None  # этап пути «напиши заново сам»: практикум и автопроверка тестов


class CreatedCourse(BaseModel):
    id: int
    slug: str
    title: str
    draft_version: int | None
    published_version: int | None


class RequestOut(BaseModel):
    id: int
    status: GenStatus
    what: GenWhat
    origin: str
    project: str
    focus: str
    topic: str
    level: int
    notes: str
    author: str | None
    plan: Plan | None
    fragments: dict[int, str]  # названия статей из плана: id → «Название · источник»
    steps: list[Step]
    error: str | None
    pause: str = ""  # запрошенная пауза: after | now — пока воркер не остановился
    busy: bool
    published: bool  # всё созданное опубликовано
    course: CreatedCourse | None
    topics: list[dict]  # [{id, title, published, questions}]
    path: dict | None = None  # путь «напиши заново сам»: {slug, title, published}
    lessons: list[CreatedLesson]
    created_at: datetime
    updated_at: datetime


class RequestCard(BaseModel):
    id: int
    status: GenStatus
    what: GenWhat
    origin: str
    title: str
    project: str
    author: str | None
    busy: bool
    published: bool
    updated_at: datetime


class PublishOut(BaseModel):
    published: list[str]
    problems: list[str]


class ProjectOut(BaseModel):
    name: str
    files: int
    languages: list[str]


# ---------- Этап пути «напиши заново сам» ----------


class StageFork(BaseModel):
    question: Short
    context: Long = ""
    reference: Long = Field(description="Как решил автор проекта и почему — со ссылками на файлы; ученик увидит после оценки")


class StageDraft(BaseModel):
    statement: Annotated[str, StringConstraints(max_length=8000)] = Field(description="Условие этапа в markdown: что сделать в рабочей папке")
    tests: str = Field(description="Автотесты этапа: web — test(...) на JavaScript, python — функции test_*")
    forks: list[StageFork] = Field(default_factory=list, max_length=3)


class StageFix(BaseModel):
    tests: str
    note: Short


class PauseIn(BaseModel):
    mode: Literal["after", "now"] = "after"


class QuizTopup(BaseModel):
    questions: list[DraftQuestion] = Field(max_length=30)
