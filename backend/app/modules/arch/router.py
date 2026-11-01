from fastapi import APIRouter, HTTPException, status

from app.modules.arch import service
from app.modules.arch.exercises import BY_SLUG
from app.modules.arch.models import ArchAttempt
from app.modules.auth.deps import CurrentUser, Db

router = APIRouter(prefix="/api/arch", tags=["arch"])


@router.get("")
def exercises(db: Db, user: CurrentUser):
    return service.overview(db, user)


@router.get("/{slug}")
def exercise(slug: str, db: Db, user: CurrentUser):
    ex = BY_SLUG.get(slug)
    if ex is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Задание не найдено")
    mine = service.attempts(db, user, slug)
    first = service.counted_attempt(db, user, slug)
    return {
        "exercise": service.public(ex), "attempts": [service.attempt_out(a) for a in mine[:10]],
        "counted": service.attempt_out(first) if first else None, "next": service.next_slug(slug),
    }


@router.post("/{slug}/attempts", status_code=status.HTTP_201_CREATED)
def submit(slug: str, payload: dict, db: Db, user: CurrentUser):
    try:
        return service.attempt_out(service.submit(db, user, slug, payload))
    except service.ArchError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.get("/attempts/{attempt_id}")
def attempt(attempt_id: int, db: Db, user: CurrentUser):
    a = db.get(ArchAttempt, attempt_id)
    if a is None or a.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Попытка не найдена")
    return service.attempt_out(a)
