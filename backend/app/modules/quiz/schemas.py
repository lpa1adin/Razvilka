from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints, model_validator

from app.modules.quiz.models import AttemptStatus, QuestionStatus, QuestionType

OptionId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9_-]{1,20}$")]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class Option(BaseModel):
    id: OptionId
    text: Text


class QuestionIn(BaseModel):
    type: QuestionType
    prompt: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=2000)]
    code: Annotated[str, StringConstraints(max_length=6000)] = ""
    code_lang: Annotated[str, StringConstraints(max_length=20)] = ""
    options: dict
    answer: dict
    explanation: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] = ""
    fragment_id: int | None = None
    subtopic: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] = ""
    difficulty: int = Field(2, ge=1, le=3)
    status: QuestionStatus = QuestionStatus.draft

    @model_validator(mode="after")
    def consistent(self):
        """Ответ должен ссылаться на существующие варианты — иначе вопрос нельзя решить."""
        if self.type is QuestionType.match:
            left = [Option.model_validate(o) for o in self.options.get("left", [])]
            right = [Option.model_validate(o) for o in self.options.get("right", [])]
            if not 2 <= len(left) <= 6 or not 2 <= len(right) <= 8:
                raise ValueError("Сопоставление: слева 2–6 пунктов, справа 2–8")
            pairs = self.answer.get("pairs", {})
            if set(pairs) != {o.id for o in left}:
                raise ValueError("Сопоставление: для каждого пункта слева нужна пара")
            if not set(pairs.values()) <= {o.id for o in right}:
                raise ValueError("Сопоставление: пара ссылается на несуществующий пункт справа")
            ids = [o.id for o in left] + [o.id for o in right]
        else:
            items = [Option.model_validate(o) for o in self.options.get("items", [])]
            if not 2 <= len(items) <= 8:
                raise ValueError("Нужно от 2 до 8 вариантов")
            ids = [o.id for o in items]
            known = set(ids)
            if self.type is QuestionType.order:
                if sorted(self.answer.get("order", [])) != sorted(known):
                    raise ValueError("Порядок: перечислите все пункты ровно по одному разу")
            else:
                correct = self.answer.get("correct", [])
                if not correct or not set(correct) <= known:
                    raise ValueError("Отметьте правильный вариант")
                if self.type is QuestionType.single and len(correct) != 1:
                    raise ValueError("В вопросе с одним ответом правильный вариант ровно один")
        if len(ids) != len(set(ids)):
            raise ValueError("id вариантов повторяются")
        if self.status is QuestionStatus.published and self.fragment_id is None:
            raise ValueError("Без источника вопрос не публикуется — привяжите статью из библиотеки")
        return self


class QuestionOut(QuestionIn):
    id: int
    topic_id: int
    fragment_title: str | None
    updated_at: datetime


class TopicIn(BaseModel):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    description: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)] = ""
    size: int = Field(10, ge=3, le=30)
    published: bool = False


class TopicAdminOut(TopicIn):
    id: int
    slug: str
    counts: dict[str, int]  # по статусам вопросов


class SimilarQuestion(BaseModel):
    id: int
    prompt: str
    similarity: float


# ---------- Учёба ----------


class TopicCard(BaseModel):
    slug: str
    title: str
    description: str
    questions: int
    size: int
    unseen: int  # сколько вопросов вы ещё не видели
    active_attempt_id: int | None
    last_score: int | None
    last_total: int | None
    attempts: int


class AnswerIn(BaseModel):
    response: dict


class Source(BaseModel):
    fragment_id: int
    title: str
    source: str


class AttemptItemOut(BaseModel):
    position: int
    type: QuestionType
    prompt_html: str
    code: str
    code_lang: str
    options: dict
    response: dict | None
    # только после завершения теста:
    correct: bool | None = None
    answer: dict | None = None
    explanation_html: str | None = None
    source: Source | None = None


class AttemptOut(BaseModel):
    id: int
    topic_slug: str
    topic_title: str
    status: AttemptStatus
    mistakes_only: bool
    score: int
    total: int
    created_at: datetime
    finished_at: datetime | None
    note: str | None  # например: «в теме только 8 вопросов — тест короче»
    items: list[AttemptItemOut]
