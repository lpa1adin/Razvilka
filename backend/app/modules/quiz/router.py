from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import func, select

from app.modules.auth.deps import AdminUser, CurrentUser, Db
from app.modules.auth.models import User
from app.modules.courses.service import slugify
from app.modules.jobs.models import Job
from app.modules.jobs.queue import enqueue, has_pending
from app.modules.library.models import Fragment
from app.modules.quiz import service
from app.modules.quiz.models import Question, QuestionStatus, QuizAttempt, QuizAttemptItem, QuizTopic
from app.modules.quiz.schemas import AnswerIn, AttemptOut, QuestionIn, QuestionOut, TopicAdminOut, TopicCard, TopicIn, TopupIn

router = APIRouter(prefix="/api/quiz", tags=["quiz"])
admin_router = APIRouter(prefix="/api/workshop/quiz", tags=["workshop"])


def _topic(db: Db, slug: str) -> QuizTopic:
    topic = db.scalar(select(QuizTopic).where(QuizTopic.slug == slug, QuizTopic.published.is_(True)))
    if topic is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Тема не найдена или снята с публикации")
    return topic


def _attempt(db: Db, attempt_id: int, user: User) -> QuizAttempt:
    attempt = db.get(QuizAttempt, attempt_id)
    if attempt is None or attempt.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Тест не найден")
    return attempt


def _bad(exc: service.QuizError) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, str(exc))


@router.get("/topics", response_model=list[TopicCard])
def topics(db: Db, user: CurrentUser):
    cards = [service.topic_card(db, user, t) for t in db.scalars(select(QuizTopic).where(QuizTopic.published.is_(True)).order_by(QuizTopic.id))]
    return [c for c in cards if c.questions > 0]


@router.get("/topics/{slug}", response_model=TopicCard)
def topic(slug: str, db: Db, user: CurrentUser):
    return service.topic_card(db, user, _topic(db, slug))


class StartIn(BaseModel):
    mistakes_only: bool = False


@router.post("/topics/{slug}/attempts", response_model=AttemptOut)
def start(slug: str, payload: StartIn, db: Db, user: CurrentUser):
    try:
        attempt = service.start(db, user, _topic(db, slug), payload.mistakes_only)
    except service.QuizError as exc:
        raise _bad(exc) from exc
    return service.attempt_out(db, attempt)


@router.get("/attempts/{attempt_id}", response_model=AttemptOut)
def get_attempt(attempt_id: int, db: Db, user: CurrentUser):
    return service.attempt_out(db, _attempt(db, attempt_id, user))


@router.put("/attempts/{attempt_id}/items/{position}", status_code=status.HTTP_204_NO_CONTENT)
def answer(attempt_id: int, position: int, payload: AnswerIn, db: Db, user: CurrentUser):
    try:
        service.save_answer(db, _attempt(db, attempt_id, user), position, payload.response)
    except service.QuizError as exc:
        raise _bad(exc) from exc


@router.post("/attempts/{attempt_id}/finish", response_model=AttemptOut)
def finish(attempt_id: int, db: Db, user: CurrentUser):
    attempt = _attempt(db, attempt_id, user)
    service.finish(db, attempt)
    return service.attempt_out(db, attempt)


# ---------- Мастерская ----------


def _admin_topic(db: Db, topic_id: int) -> QuizTopic:
    topic = db.get(QuizTopic, topic_id)
    if topic is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Тема не найдена")
    return topic


def _topic_out(db: Db, topic: QuizTopic) -> TopicAdminOut:
    counts = dict(db.execute(select(Question.status, func.count()).where(Question.topic_id == topic.id).group_by(Question.status)).all())
    return TopicAdminOut(
        id=topic.id, slug=topic.slug, title=topic.title, description=topic.description, size=topic.size,
        published=topic.published, counts={s.value: counts.get(s, 0) for s in QuestionStatus},
    )


def _question_out(db: Db, q: Question) -> QuestionOut:
    title = db.scalar(select(Fragment.title).where(Fragment.id == q.fragment_id)) if q.fragment_id else None
    return QuestionOut(
        id=q.id, topic_id=q.topic_id, type=q.type, prompt=q.prompt, code=q.code, code_lang=q.code_lang, options=q.options,
        answer=q.answer, explanation=q.explanation, fragment_id=q.fragment_id, subtopic=q.subtopic, difficulty=q.difficulty,
        status=q.status, fragment_title=title, updated_at=q.updated_at,
    )


def _unique_slug(db: Db, title: str) -> str:
    slug = base = slugify(title)
    n = 2
    while db.scalar(select(QuizTopic.id).where(QuizTopic.slug == slug)):
        slug, n = f"{base}-{n}", n + 1
    return slug


@admin_router.get("/topics", response_model=list[TopicAdminOut])
def admin_topics(db: Db, _: AdminUser):
    return [_topic_out(db, t) for t in db.scalars(select(QuizTopic).order_by(QuizTopic.id))]


@admin_router.post("/topics", response_model=TopicAdminOut, status_code=status.HTTP_201_CREATED)
def admin_create_topic(payload: TopicIn, db: Db, _: AdminUser):
    topic = QuizTopic(slug=_unique_slug(db, payload.title), **payload.model_dump())
    db.add(topic)
    db.commit()
    return _topic_out(db, topic)


@admin_router.put("/topics/{topic_id}", response_model=TopicAdminOut)
def admin_update_topic(topic_id: int, payload: TopicIn, db: Db, _: AdminUser):
    topic = _admin_topic(db, topic_id)
    for name, value in payload.model_dump().items():
        setattr(topic, name, value)
    db.commit()
    return _topic_out(db, topic)


@admin_router.get("/topics/{topic_id}/questions", response_model=list[QuestionOut])
def admin_questions(topic_id: int, db: Db, _: AdminUser):
    _admin_topic(db, topic_id)
    rows = db.scalars(select(Question).where(Question.topic_id == topic_id).order_by(Question.subtopic, Question.id))
    return [_question_out(db, q) for q in rows]


def _duplicates_response(similar) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": "Похожий вопрос уже есть в этой теме", "similar": [s.model_dump() for s in similar]},
    )


@admin_router.post("/topics/{topic_id}/questions", response_model=QuestionOut, status_code=status.HTTP_201_CREATED)
def admin_create_question(topic_id: int, payload: QuestionIn, db: Db, _: AdminUser, force: bool = Query(False)):
    _admin_topic(db, topic_id)
    similar = service.similar_questions(db, topic_id, payload.prompt, payload.code)
    if similar and not force:
        return _duplicates_response(similar)
    question = Question(topic_id=topic_id)
    service.apply(question, payload)
    db.add(question)
    db.commit()
    return _question_out(db, question)


@admin_router.put("/questions/{question_id}", response_model=QuestionOut)
def admin_update_question(question_id: int, payload: QuestionIn, db: Db, _: AdminUser, force: bool = Query(False)):
    question = db.get(Question, question_id)
    if question is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Вопрос не найден")
    similar = service.similar_questions(db, question.topic_id, payload.prompt, payload.code, exclude=question.id)
    if similar and not force:
        return _duplicates_response(similar)
    # Уже пройденные тесты хранят снимок вопроса — правка их не меняет
    service.apply(question, payload)
    db.commit()
    return _question_out(db, question)


@admin_router.delete("/questions/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_delete_question(question_id: int, db: Db, _: AdminUser):
    question = db.get(Question, question_id)
    if question is None:
        return
    used = db.scalar(select(QuizAttemptItem.id).where(QuizAttemptItem.question_id == question.id).limit(1))
    if used:
        # Вопрос уже был в чьих-то тестах: не удаляем, а убираем из подбора — история остаётся честной
        question.status = QuestionStatus.archived
    else:
        db.delete(question)
    db.commit()


# ---------- Дописать банк (Claude, agent-worker) ----------

TOPUP_JOB = "gen_quiz_topup"


def _topup_state(db, topic_id: int) -> dict:
    job = db.scalar(
        select(Job).where(Job.kind == "agent", Job.payload["type"].astext == TOPUP_JOB, Job.payload["topic_id"].astext == str(topic_id))
        .order_by(Job.id.desc()).limit(1)
    )
    if job is None:
        return {"running": False, "error": None, "added": None, "notes": []}
    result = job.result or {}
    return {"running": job.status.value in ("queued", "running"), "error": job.error, "added": result.get("added"), "notes": result.get("notes", [])}


@admin_router.get("/topics/{topic_id}/topup")
def topup_state(topic_id: int, db: Db, _: AdminUser):
    return _topup_state(db, topic_id)


@admin_router.post("/topics/{topic_id}/topup", status_code=status.HTTP_202_ACCEPTED)
def topup(topic_id: int, payload: TopupIn, db: Db, _: AdminUser):
    if db.get(QuizTopic, topic_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Тема не найдена")
    if has_pending(db, "agent", type=TOPUP_JOB, topic_id=str(topic_id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Банк уже дописывается")
    enqueue(db, "agent", {"type": TOPUP_JOB, "topic_id": str(topic_id), "target": str(payload.target)})
    return _topup_state(db, topic_id)
