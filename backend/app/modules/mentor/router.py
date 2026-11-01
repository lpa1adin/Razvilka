import json
import time
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from app.core.db import SessionLocal
from app.modules.agent import claude
from app.modules.auth.deps import CurrentUser, Db
from app.modules.jobs.models import WorkerHeartbeat
from app.modules.mentor import service
from app.modules.mentor.models import MentorMessage, MentorThread, MessageStatus

router = APIRouter(prefix="/api/mentor", tags=["mentor"])
STREAM_POLL = 0.25
STREAM_LIMIT = 300  # секунд: дольше ответ не ждём


def _message_out(m: MentorMessage) -> dict:
    return {"id": m.id, "role": m.role, "content": m.content, "status": m.status.value, "hint": m.hint, "error": m.error, "created_at": m.created_at}


@router.get("/status")
def mentor_status(db: Db, _: CurrentUser):
    beat = db.get(WorkerHeartbeat, "chat")
    alive = bool(beat and beat.seen_at > datetime.now(UTC) - timedelta(seconds=60))
    configured = claude.configured()
    if not configured:
        reason = "Наставник не подключён: администратор ещё не добавил токен Claude."
    elif not alive:
        reason = "Наставник сейчас не на связи (agent-worker не запущен)."
    else:
        reason = None
    return {"available": configured and alive, "reason": reason}


@router.get("/thread")
def get_thread(db: Db, user: CurrentUser, kind: str = Query(pattern="^(lesson|task|general)$"), ref: str = ""):
    thread = service.thread_for(db, user, kind, ref)
    return {"messages": [_message_out(m) for m in service.messages(db, thread)]}


@router.delete("/thread", status_code=status.HTTP_204_NO_CONTENT)
def clear_thread(db: Db, user: CurrentUser, kind: str = Query(pattern="^(lesson|task|general)$"), ref: str = ""):
    thread = service.thread_for(db, user, kind, ref)
    if thread is not None:
        db.delete(thread)
        db.commit()


@router.post("/messages", status_code=status.HTTP_202_ACCEPTED)
def send(payload: service.MessageIn, db: Db, user: CurrentUser):
    try:
        answer = service.send(db, user, payload)
    except service.MentorUnavailable as exc:
        raise HTTPException(status.HTTP_409_CONFLICT if claude.configured() else status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    return {"answer_id": answer.id}


@router.get("/messages/{message_id}/stream")
def stream(message_id: int, db: Db, user: CurrentUser):
    """Server-Sent Events: новый текст ответа по мере того, как воркер его дописывает."""
    message = db.get(MentorMessage, message_id)
    thread = db.get(MentorThread, message.thread_id) if message else None
    if thread is None or thread.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Сообщение не найдено")

    def events():
        sent = ticks = 0
        started = time.monotonic()
        with SessionLocal() as session:
            while True:
                current = session.get(MentorMessage, message_id)
                session.refresh(current)
                if len(current.content) > sent:
                    yield f"data: {json.dumps({'delta': current.content[sent:]}, ensure_ascii=False)}\n\n"
                    sent = len(current.content)
                if current.status in (MessageStatus.done, MessageStatus.failed):
                    yield f"data: {json.dumps({'status': current.status.value, 'error': current.error, 'content': current.content}, ensure_ascii=False)}\n\n"
                    return
                if time.monotonic() - started > STREAM_LIMIT:
                    yield f"data: {json.dumps({'status': 'failed', 'error': 'Наставник не ответил вовремя. Попробуйте ещё раз.'}, ensure_ascii=False)}\n\n"
                    return
                ticks += 1
                if ticks % 60 == 0:
                    yield ": ping\n\n"  # комментарий SSE: соединение живо, пока ответ в очереди
                session.commit()  # закрыть транзакцию, чтобы увидеть новые записи воркера
                time.sleep(STREAM_POLL)

    # X-Accel-Buffering: nginx не должен копить поток — иначе текст придёт одним куском в конце
    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/messages/{message_id}")
def get_message(message_id: int, db: Db, user: CurrentUser):
    message = db.get(MentorMessage, message_id)
    thread = db.get(MentorThread, message.thread_id) if message else None
    if thread is None or thread.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Сообщение не найдено")
    return _message_out(message)

