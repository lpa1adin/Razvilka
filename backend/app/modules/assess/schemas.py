from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.modules.assess.models import SubmissionStatus

Short = Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)]
Long = Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)]
ForkId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9-]{1,40}$")]


# ---------- Рубрика, эталоны, практикумы (Мастерская) ----------


class Criterion(BaseModel):
    id: Annotated[str, StringConstraints(pattern=r"^R\d{1,2}$")]
    block: Literal["reasoning", "implementation"]
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=200)]
    description: Long = ""


class RubricIn(BaseModel):
    criteria: list[Criterion] = Field(min_length=2, max_length=20)
    mismatch_penalty: float = Field(0.75, ge=0, le=5)
    note: Short = ""


class RubricOut(RubricIn):
    version: int
    created_at: datetime


class ReferenceIn(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=200)]
    url: Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] = ""
    about: Long = ""


class ReferenceOut(ReferenceIn):
    id: int


class Fork(BaseModel):
    id: ForkId
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=500)]
    context: Long = ""
    reference: Long = ""  # как решено в эталоне — ученик увидит только после оценки


class AssignmentIn(BaseModel):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=200)]
    statement: Annotated[str, StringConstraints(max_length=12000)] = ""
    kind: Literal["web", "python", "any"] = "any"
    forks: list[Fork] = Field(default_factory=list, max_length=12)
    tests: Annotated[str, StringConstraints(max_length=40000)] = ""
    reference_ids: list[int] = Field(default_factory=list, max_length=10)
    threshold: float = Field(3.0, ge=0, le=5)
    published: bool = False


class AssignmentAdminOut(AssignmentIn):
    id: int
    slug: str
    submissions: int


class AssignmentCard(BaseModel):
    slug: str
    title: str
    kind: str
    forks: int
    attempts: int
    best_score: float | None
    passed: bool


class AssignmentForLearner(BaseModel):
    slug: str
    title: str
    statement_html: str
    kind: str
    forks: list[dict]  # {id, question, context} — без ответа эталона
    has_tests: bool
    threshold: float
    references: list[ReferenceOut]
    projects: list[str]  # папки ProjectsWithClaude, которые можно сдать
    path: dict | None = None  # этап пути «напиши заново сам»: путь, номер, рабочая папка
    submissions: list["SubmissionCard"]


# ---------- Сдача ----------


class ForkAnswer(BaseModel):
    """Ответ на развилку в формате ADR (BRIEF §5.6)."""

    choice: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=500)]
    alternatives: Long = ""
    reasons: Annotated[str, StringConstraints(strip_whitespace=True, min_length=10, max_length=4000)]
    risks: Long = ""
    revisit: Long = ""  # когда пересмотреть


class SubmissionCard(BaseModel):
    id: int
    assignment_slug: str
    assignment_title: str
    attempt: int
    status: SubmissionStatus
    score: float | None
    passed: bool | None
    mismatches: int
    created_at: datetime


class SubmissionOut(BaseModel):
    id: int
    assignment_slug: str
    assignment_title: str
    attempt: int
    source: str
    source_name: str
    status: SubmissionStatus
    steps: list[dict]
    warnings: list[str]
    files: dict[str, str]
    forks: list[dict]  # {id, question, answer, reference (после оценки)}
    summary: str
    tests: dict | None
    review: dict | None  # ReviewOut
    evaluation: dict | None
    score: float | None
    passed: bool | None
    threshold: float
    rubric_version: int
    error: str | None
    created_at: datetime
    finished_at: datetime | None


# ---------- Ответ Оценщика (строгий JSON) ----------


class Evidence(BaseModel):
    file: str
    line: int
    note: str = Field(description="Что именно видно в этой строке")


class CriterionScore(BaseModel):
    id: str = Field(description="id критерия рубрики: R1…")
    score: int = Field(ge=0, le=5)
    explanation: str = Field(description="Почему такой балл: со ссылками на ответы и код")
    evidence: list[Evidence] = Field(default_factory=list, max_length=6)


class Mismatch(BaseModel):
    fork_id: str = Field(description="id развилки, где ученик это заявил")
    claim: str = Field(description="Дословная цитата из ответа ученика")
    file: str = Field(description="Файл, где реализация говорит другое")
    line: int = Field(description="Номер строки из входа")
    code_says: str = Field(description="Что на самом деле в коде, коротко")
    why: str = Field(description="Почему это расхождение важно")


class ReferenceView(BaseModel):
    fork_id: str
    reference: str = Field(description="Как это решено в эталонных проектах и почему; что сделали бы в эталоне")


class EvaluatorReport(BaseModel):
    criteria: list[CriterionScore] = Field(max_length=20)
    mismatches: list[Mismatch] = Field(default_factory=list, max_length=12)
    contradictions: list[str] = Field(default_factory=list, max_length=8, description="Противоречия с прошлыми сдачами этого практикума")
    reference_view: list[ReferenceView] = Field(default_factory=list, max_length=12)
    summary: str = Field(description="Итог для ученика, 2–4 предложения")


AssignmentForLearner.model_rebuild()
