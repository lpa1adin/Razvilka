from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, model_validator

from app.modules.courses.models import VersionStatus
from app.modules.practice.models import CheckStatus

Kind = Literal["web", "python", "sql"]

# Какие файлы бывают у задания каждого вида — по ним строятся вкладки редактора
FILES: dict[str, tuple[str, ...]] = {
    "web": ("index.html", "style.css", "script.js"),
    "python": ("main.py",),
    "sql": ("query.sql",),
}

MAX_FILE = 100_000
Code = Annotated[str, StringConstraints(max_length=MAX_FILE)]


class SqlCheck(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    # same_result — результат запроса совпадает с эталонным; assert — после кода ученика запрос вернёт «истину»
    type: Literal["same_result", "assert"] = "same_result"
    sql: Code = ""
    order_matters: bool = False
    message: Annotated[str, StringConstraints(max_length=500)] = ""


class TaskSpec(BaseModel):
    title: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] = ""
    kind: Kind
    statement: Annotated[str, StringConstraints(max_length=8000)] = ""  # условие (markdown) — пишет админ
    starter: dict[str, Code] = Field(default_factory=dict)
    solution: dict[str, Code] = Field(default_factory=dict)
    tests: Code = ""  # web — JavaScript, python — Python
    sql_setup: Code = ""  # sql — схема и данные
    sql_checks: list[SqlCheck] = Field(default_factory=list, max_length=30)
    hints: list[Annotated[str, StringConstraints(max_length=1500)]] = Field(default_factory=list, max_length=10)
    fragment_ids: list[int] = Field(default_factory=list, max_length=10)  # теория к заданию

    @model_validator(mode="after")
    def known_files_only(self):
        allowed = set(FILES[self.kind])
        for part in (self.starter, self.solution):
            extra = set(part) - allowed
            if extra:
                raise ValueError(f"Для задания вида {self.kind} нет файлов {sorted(extra)}; можно: {sorted(allowed)}")
        return self


# ---------- Учёба ----------


class TaskCard(BaseModel):
    slug: str
    title: str
    kind: Kind
    version: int
    started: bool
    solved: bool
    has_update: bool


class TaskForLearner(BaseModel):
    """Задание для решения. Эталонного решения здесь нет."""

    slug: str
    title: str
    kind: Kind
    version: int
    preview: bool
    statement_html: str
    files: dict[str, str]
    starter: dict[str, str]
    tests: str
    sql_setup: str
    sql_checks: list[SqlCheck]
    sql_expected: list  # ожидаемые результаты, посчитанные runner по эталону; сам эталонный запрос не отдаём
    hints: list[str]  # уже открытые подсказки
    hints_total: int
    solved: bool
    has_update: bool
    fragments: list[dict]


class WorkIn(BaseModel):
    files: dict[str, Code]


class AttemptIn(BaseModel):
    passed: bool
    results: list[dict] = Field(max_length=100)


# ---------- Мастерская ----------


class TaskCreate(BaseModel):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    kind: Kind


class TaskDraftIn(BaseModel):
    number: int
    spec: TaskSpec


class TaskVersionOut(BaseModel):
    number: int
    status: VersionStatus
    spec: TaskSpec
    check_status: CheckStatus
    check_report: dict | None
    check_is_current: bool  # проверяли именно этот текст задания, а не более раннюю правку
    change_note: str
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None


class AdminTaskBrief(BaseModel):
    id: int
    slug: str
    title: str
    kind: Kind
    published_version: int | None
    draft_version: int | None
    archived: bool
    check_status: CheckStatus
    updated_at: datetime


class AdminTaskOut(BaseModel):
    id: int
    slug: str
    published_version: int | None
    draft_version: int | None
    archived: bool
    editing: TaskVersionOut
