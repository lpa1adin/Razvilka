"""Сводка «что сейчас в работе и что ждёт решения» — коротко, одним вызовом.

Нужна, чтобы продолжить работу после перерыва, не перебирая базу по частям: `python -m app.cli status`.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.agent import claude
from app.modules.generation.models import GenRequest, GenStatus
from app.modules.jobs.models import Job, JobStatus
from app.modules.practice import service as practice
from app.modules.practice.models import Task
from app.modules.quiz.models import Question, QuizTopic
from app.modules.quiz.service import BANK_MAX, BANK_MIN
from app.modules.review import service as review_service


def _jobs(db: Session) -> list[str]:
    since = datetime.now(UTC) - timedelta(days=1)
    lines = []
    for job in db.scalars(select(Job).where(Job.status.in_([JobStatus.queued, JobStatus.running])).order_by(Job.id)):
        lines.append(f"  #{job.id} {job.kind}/{job.payload.get('type', '')} {job.status.value} {_target(job)}")
    for job in db.scalars(select(Job).where(Job.status == JobStatus.failed, Job.finished_at >= since).order_by(Job.id)):
        lines.append(f"  #{job.id} {job.kind}/{job.payload.get('type', '')} упала {_target(job)}: {(job.error or '')[:90]}")
    return lines


def _target(job: Job) -> str:
    p = job.payload
    return " ".join(f"{k}={p[k]}" for k in ("request_id", "task_id", "topic_id", "review_id", "source") if p.get(k))


def _requests(db: Session) -> list[str]:
    lines = []
    for req in db.scalars(select(GenRequest).where(GenRequest.status.not_in([GenStatus.rejected])).order_by(GenRequest.id)):
        lessons = [s for s in req.steps if s["key"].startswith("lesson:")]
        done = sum(s["state"] == "done" for s in lessons)
        tail = {s["key"]: f"{s['state']} {s.get('detail', '')[:60]}" for s in req.steps if s["key"] in ("checks", "review")}
        title = (req.plan or {}).get("title") or req.topic or req.project
        lines.append(f"  #{req.id} {req.status.value}{' пауза:' + req.pause if req.pause else ''} «{title[:50]}» уроков {done}/{len(lessons)}"
                     + (f" | проверки: {tail.get('checks', '—')} | ревью: {tail.get('review', '—')}" if tail else ""))
    return lines


def _tasks(db: Session) -> list[str]:
    """Только то, что требует внимания: замечания Ревьюера, правки на одобрение, упавшие автопроверки."""
    lines = []
    for task in db.scalars(select(Task).where(Task.draft_version.is_not(None)).order_by(Task.id)):
        version = practice.editing_version(db, task)
        review = review_service.reference_review(db, task)
        notes = []
        if version.check_status.value != "passed":
            notes.append(f"автопроверка: {version.check_status.value}")
        if review is None:
            notes.append("ревью нет")
        elif review.status.value != "done":
            notes.append(f"ревью: {review.status.value}")
        elif review.verdict == "changes_requested":
            c = review_service.counts(review)
            notes.append(f"Ревьюер: blocker {c['blocker']}, major {c['major']}")
        if version.proposal:
            notes.append("ждёт решения правка: " + ",".join(version.proposal["fields"]))
        if notes:
            pub = "опубл.+черновик" if task.published_version else "черновик"
            lines.append(f"  #{task.id} [{pub}] {version.spec.get('title', '')[:45]} — " + "; ".join(notes))
    return lines


def _banks(db: Session) -> list[str]:
    rows = db.execute(
        select(QuizTopic.id, QuizTopic.title, QuizTopic.size, func.count(Question.id))
        .join(Question, Question.topic_id == QuizTopic.id, isouter=True).group_by(QuizTopic.id).order_by(QuizTopic.id)
    ).all()
    return [f"  #{tid} «{title[:55]}» вопросов {n}, тест {size}" for tid, title, size, n in rows if not BANK_MIN <= n <= BANK_MAX]


def report(db: Session) -> str:
    claude_state = "подключён" if claude.configured() else "НЕ подключён"
    sections = [
        f"Claude: {claude_state}; код — {settings.agent_model}, текст — {settings.text_model}, второй взгляд — {settings.reviewer_second_model}",
        ("Задачи в очереди / упавшие за сутки:", _jobs(db)),
        ("Заявки генерации:", _requests(db)),
        ("Задания, которые ждут внимания:", _tasks(db)),
        (f"Банки вопросов вне {BANK_MIN}–{BANK_MAX}:", _banks(db)),
    ]
    out = []
    for section in sections:
        if isinstance(section, str):
            out.append(section)
        else:
            title, lines = section
            out.append(title)
            out += lines or ["  —"]
    return "\n".join(out)
