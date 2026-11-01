from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.modules.practice.schemas import Code
from app.modules.review.models import ReviewKind, ReviewStatus

RuleId = Annotated[str, StringConstraints(pattern=r"^[A-Z]{2,6}-\d{2}$")]
Severity = Literal["blocker", "major", "minor"]


class Rule(BaseModel):
    id: RuleId
    group: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=1000)]
    enabled: bool = True
    # Откуда правило: markdown-ссылки на OWASP, MDN, WCAG, PEP 8… Ссылку на источник даёт платформа, а не модель
    source: Annotated[str, StringConstraints(strip_whitespace=True, max_length=800)] = ""


class RulesIn(BaseModel):
    rules: list[Rule] = Field(min_length=1, max_length=120)
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] = ""


class RulesOut(BaseModel):
    version: int
    rules: list[Rule]
    note: str
    created_at: datetime
    author: str | None


# ---------- Ответ Ревьюера (строгий JSON по REVIEWER.md) ----------


class ModelFinding(BaseModel):
    rule: str = Field(description="id правила, например SEC-03")
    severity: Severity
    file: str = Field(description="Путь файла ровно как во входе")
    line: int = Field(description="Номер строки из входа (номера стоят слева)")
    problem: str = Field(description="Что не так — одно предложение")
    scenario: str = Field(description="Конкретные входные данные или действие → что сломается")
    fix_hint: str = Field(description="Направление исправления, без готового кода")
    source: str = Field("", description="Правило или источник: OWASP, MDN, WCAG, PEP 8…")


class ModelReport(BaseModel):
    findings: list[ModelFinding] = Field(default_factory=list, max_length=40)


class Finding(BaseModel):
    rule: str
    rule_text: str
    severity: Severity
    file: str
    line: int | None
    problem: str
    scenario: str
    fix_hint: str
    source: str
    by: str = ""  # какая модель нашла: основной Ревьюер или второй взгляд


# ---------- API ----------


class LearnerReviewIn(BaseModel):
    task_slug: Annotated[str, StringConstraints(max_length=80)]
    files: dict[str, Code]


class AcceptIn(BaseModel):
    note: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]


class ReviewOut(BaseModel):
    id: int
    kind: ReviewKind
    status: ReviewStatus
    title: str
    task_slug: str | None
    task_version: int | None
    rules_version: int
    verdict: str | None
    findings: list[Finding]
    counts: dict[str, int]
    dropped: int
    second_opinion: bool = False  # эталон дополнительно проверила вторая модель
    files: dict[str, str]
    error: str | None
    accepted: bool
    accepted_note: str
    created_at: datetime
    finished_at: datetime | None


class ReviewCard(BaseModel):
    id: int
    kind: ReviewKind
    status: ReviewStatus
    title: str
    task_slug: str | None
    verdict: str | None
    counts: dict[str, int]
    created_at: datetime
