from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.modules.auth.deps import AdminUser, CurrentUser, Db
from app.modules.generation import service
from app.modules.generation.models import GenRequest
from app.modules.generation.schemas import (
    PauseIn,
    Plan,
    ProjectOut,
    PublishOut,
    RedoIn,
    ReplanIn,
    RequestCard,
    RequestIn,
    RequestOut,
    TopicProposalIn,
)

router = APIRouter(prefix="/api/workshop/generate", tags=["workshop"])
# Пользователь может только предложить тему — из чата с наставником
proposals_router = APIRouter(prefix="/api/proposals", tags=["mentor"])


def _req(db: Db, request_id: int) -> GenRequest:
    req = db.get(GenRequest, request_id)
    if req is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Заявка не найдена")
    return req


def _do(db: Db, req: GenRequest, action) -> RequestOut:
    try:
        action()
    except service.GenError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    db.refresh(req)
    return service.to_out(db, req)


@router.get("/projects", response_model=list[ProjectOut])
def projects(_: AdminUser):
    return service.list_projects()


@router.get("/requests", response_model=list[RequestCard])
def list_requests(db: Db, _: AdminUser):
    rows = db.scalars(select(GenRequest).order_by(GenRequest.updated_at.desc()))
    return [service.to_card(db, r) for r in rows]


@router.post("/requests", response_model=RequestOut, status_code=status.HTTP_201_CREATED)
def create_request(payload: RequestIn, db: Db, admin: AdminUser):
    try:
        req = service.create_request(db, admin, payload)
    except service.GenError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return service.to_out(db, req)


@router.get("/requests/{request_id}", response_model=RequestOut)
def get_request(request_id: int, db: Db, _: AdminUser):
    return service.to_out(db, _req(db, request_id))


@router.put("/requests/{request_id}", response_model=RequestOut)
def update_request(request_id: int, payload: RequestIn, db: Db, _: AdminUser):
    req = _req(db, request_id)
    return _do(db, req, lambda: service.update_request(db, req, payload))


@router.post("/requests/{request_id}/reject", response_model=RequestOut)
def reject(request_id: int, db: Db, _: AdminUser):
    req = _req(db, request_id)
    return _do(db, req, lambda: service.reject(db, req))


@router.delete("/requests/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_request(request_id: int, db: Db, _: AdminUser):
    """Удаляется только заявка. Созданные курсы и задания остаются в Контенте."""
    req = db.get(GenRequest, request_id)
    if req is None:
        return
    if service.busy(db, req):
        raise HTTPException(status.HTTP_409_CONFLICT, "Наставник ещё работает над заявкой")
    db.delete(req)
    db.commit()


@router.post("/requests/{request_id}/plan", response_model=RequestOut)
def build_plan(request_id: int, db: Db, _: AdminUser):
    req = _req(db, request_id)
    return _do(db, req, lambda: service.start_plan(db, req))


@router.post("/requests/{request_id}/replan", response_model=RequestOut)
def replan(request_id: int, payload: ReplanIn, db: Db, _: AdminUser):
    req = _req(db, request_id)
    return _do(db, req, lambda: service.start_plan(db, req, payload.feedback))


@router.put("/requests/{request_id}/plan", response_model=RequestOut)
def save_plan(request_id: int, plan: Plan, db: Db, _: AdminUser):
    req = _req(db, request_id)
    return _do(db, req, lambda: service.save_plan(db, req, plan))


@router.post("/requests/{request_id}/draft", response_model=RequestOut)
def build_draft(request_id: int, db: Db, admin: AdminUser):
    req = _req(db, request_id)
    return _do(db, req, lambda: service.start_draft(db, req, admin))


@router.post("/requests/{request_id}/pause", response_model=RequestOut)
def pause(request_id: int, payload: PauseIn, db: Db, _: AdminUser):
    req = _req(db, request_id)
    return _do(db, req, lambda: service.pause(db, req, payload.mode))


@router.post("/requests/{request_id}/resume", response_model=RequestOut)
def resume(request_id: int, db: Db, admin: AdminUser):
    req = _req(db, request_id)
    return _do(db, req, lambda: service.resume(db, req, admin))


@router.post("/requests/{request_id}/lessons/{lesson_id}/redo", response_model=RequestOut)
def redo_lesson(request_id: int, lesson_id: str, payload: RedoIn, db: Db, admin: AdminUser):
    req = _req(db, request_id)
    return _do(db, req, lambda: service.redo_lesson(db, req, lesson_id, payload.instruction, admin))


@router.post("/requests/{request_id}/checks", response_model=RequestOut)
def recheck(request_id: int, db: Db, _: AdminUser):
    req = _req(db, request_id)
    return _do(db, req, lambda: service.recheck(db, req))


@router.post("/requests/{request_id}/publish", response_model=PublishOut)
def publish(request_id: int, db: Db, admin: AdminUser):
    req = _req(db, request_id)
    try:
        return service.publish_all(db, req, admin)
    except service.GenError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@proposals_router.post("", status_code=status.HTTP_201_CREATED)
def propose(payload: TopicProposalIn, db: Db, user: CurrentUser):
    req = service.propose(db, user, payload)
    return {"id": req.id, "message": "Заявка отправлена администратору — она появится в Мастерской → Генерация."}
