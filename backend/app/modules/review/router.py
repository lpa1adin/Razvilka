from fastapi import APIRouter, HTTPException, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import select

from app.modules.auth.deps import AdminUser, CurrentUser, Db
from app.modules.practice import service as practice
from app.modules.practice.models import Task
from app.modules.review import service
from app.modules.review.models import Review, ReviewRuleSet
from app.modules.review.schemas import AcceptIn, LearnerReviewIn, ReviewCard, ReviewOut, RulesIn, RulesOut

router = APIRouter(prefix="/api/reviews", tags=["review"])
admin_router = APIRouter(prefix="/api/workshop", tags=["workshop"])


def _bad(exc: service.ReviewError) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, str(exc))


# ---------- Ученик: «Ревью кода» и история проверок ----------


@router.post("", response_model=ReviewOut, status_code=status.HTTP_202_ACCEPTED)
def request_review(payload: LearnerReviewIn, db: Db, user: CurrentUser):
    task = practice.visible_task(db, payload.task_slug, None)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Задание не найдено или снято с публикации")
    try:
        return service.to_out(db, service.request_learner(db, user, task, payload.files))
    except service.ReviewError as exc:
        raise _bad(exc) from exc


@router.get("", response_model=list[ReviewCard])
def my_reviews(db: Db, user: CurrentUser, task: str | None = None):
    query = select(Review).where(Review.requested_by == user.id, Review.kind == "learner")
    if task:
        query = query.join(Task, Task.id == Review.task_id).where(Task.slug == task)
    return [service.to_card(db, r) for r in db.scalars(query.order_by(Review.id.desc()).limit(100))]


@router.get("/{review_id}", response_model=ReviewOut)
def get_review(review_id: int, db: Db, user: CurrentUser):
    review = db.get(Review, review_id)
    # Свои ревью видит автор; ревью эталонов — только админ
    if review is None or (review.requested_by != user.id and user.role.value != "admin"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ревью не найдено")
    return service.to_out(db, review)


# ---------- Мастерская: правила, ревью эталонов, экспорт агента ----------


@admin_router.get("/review-rules", response_model=RulesOut)
def get_rules(db: Db, _: AdminUser):
    return service.rules_out(db, service.active_rules(db))


@admin_router.put("/review-rules", response_model=RulesOut)
def put_rules(payload: RulesIn, db: Db, admin: AdminUser):
    try:
        return service.rules_out(db, service.save_rules(db, admin, payload.rules, payload.note))
    except service.ReviewError as exc:
        raise _bad(exc) from exc


@admin_router.get("/review-rules/versions", response_model=list[RulesOut])
def rule_versions(db: Db, _: AdminUser):
    service.active_rules(db)
    return [service.rules_out(db, rs) for rs in db.scalars(select(ReviewRuleSet).order_by(ReviewRuleSet.version.desc()))]


@admin_router.get("/review-rules/agent.md", response_class=PlainTextResponse)
def export_agent(db: Db, _: AdminUser):
    return PlainTextResponse(
        service.agent_markdown(service.active_rules(db)),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="reviewer.md"'},
    )


def _task(db: Db, task_id: int) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Задание не найдено")
    return task


@admin_router.get("/tasks/{task_id}/review", response_model=ReviewOut | None)
def reference_review(task_id: int, db: Db, _: AdminUser):
    review = service.reference_review(db, _task(db, task_id))
    return service.to_out(db, review) if review else None


@admin_router.post("/tasks/{task_id}/review", response_model=ReviewOut, status_code=status.HTTP_202_ACCEPTED)
def request_reference(task_id: int, db: Db, admin: AdminUser):
    try:
        return service.to_out(db, service.request_reference(db, admin, _task(db, task_id)))
    except service.ReviewError as exc:
        raise _bad(exc) from exc


@admin_router.post("/reviews/{review_id}/accept", response_model=ReviewOut)
def accept(review_id: int, payload: AcceptIn, db: Db, admin: AdminUser):
    review = db.get(Review, review_id)
    if review is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ревью не найдено")
    try:
        service.accept(db, admin, review, payload.note)
    except service.ReviewError as exc:
        raise _bad(exc) from exc
    return service.to_out(db, review)
