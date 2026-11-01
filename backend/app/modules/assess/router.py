import base64
import binascii
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import select

from app.modules.assess import service, sources
from app.modules.assess.models import Assignment, ReferenceProject, Submission
from app.modules.assess.schemas import (
    AssignmentAdminOut,
    AssignmentCard,
    AssignmentForLearner,
    AssignmentIn,
    ForkAnswer,
    ReferenceIn,
    ReferenceOut,
    RubricIn,
    RubricOut,
    SubmissionCard,
    SubmissionOut,
)
from app.modules.auth.deps import AdminUser, CurrentUser, Db
from app.modules.auth.models import Role, User
from app.modules.paths import service as paths_service
from app.modules.paths.models import ProjectPath

router = APIRouter(prefix="/api", tags=["assess"])
admin_router = APIRouter(prefix="/api/workshop", tags=["workshop"])


class SubmitIn(BaseModel):
    answers: dict[str, ForkAnswer]
    summary: Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)] = ""
    source: Literal["zip", "folder", "workspace"]
    project: Annotated[str, StringConstraints(max_length=200)] = ""
    focus: Annotated[str, StringConstraints(max_length=300)] = ""
    archive: str = Field("", description="zip в base64", max_length=30_000_000)
    archive_name: Annotated[str, StringConstraints(max_length=300)] = ""


def _bad(exc: Exception) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, str(exc))


def _assignment(db: Db, slug: str) -> Assignment:
    a = db.scalar(select(Assignment).where(Assignment.slug == slug, Assignment.published.is_(True)))
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Практикум не найден")
    return a


def _submission(db: Db, submission_id: int, user: User) -> Submission:
    s = db.get(Submission, submission_id)
    if s is None or (s.user_id != user.id and user.role is not Role.admin):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Сдача не найдена")
    return s


# ---------- Ученик ----------


@router.get("/assignments", response_model=list[AssignmentCard])
def assignments(db: Db, user: CurrentUser):
    return service.assignment_cards(db, user)


@router.get("/assignments/{slug}", response_model=AssignmentForLearner)
def assignment(slug: str, db: Db, user: CurrentUser):
    return service.assignment_for_learner(db, user, _assignment(db, slug))


@router.post("/assignments/{slug}/submissions", response_model=SubmissionOut, status_code=status.HTTP_202_ACCEPTED)
def submit(slug: str, payload: SubmitIn, db: Db, user: CurrentUser):
    a = _assignment(db, slug)
    try:
        if payload.source == "zip":
            try:
                data = base64.b64decode(payload.archive, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise sources.SourceError("Архив не прочитался — загрузите zip ещё раз") from exc
            files, vendor, warnings = sources.from_zip(data)
            name = payload.archive_name or "архив.zip"
        elif payload.source == "workspace":
            if a.path_id is None:
                raise sources.SourceError("Рабочая папка есть только у этапов пути «напиши заново сам»")
            path = db.get(ProjectPath, a.path_id)
            files, vendor, warnings = sources.from_workspace(paths_service.workspace_dir(user, path))
            name = paths_service.workspace_info(user, path)["host_path"]
        else:
            files, vendor, warnings = sources.from_folder(payload.project, payload.focus)
            name = payload.project + (f"/{payload.focus}" if payload.focus else "")
        s = service.submit(db, user, a, payload.answers, payload.summary, files, vendor, warnings, payload.source, name)
    except (sources.SourceError, service.AssessError, paths_service.PathError) as exc:
        raise _bad(exc) from exc
    return service.submission_out(db, s)


@router.get("/submissions", response_model=list[SubmissionCard])
def my_submissions(db: Db, user: CurrentUser):
    rows = db.scalars(select(Submission).where(Submission.user_id == user.id).order_by(Submission.id.desc()).limit(100))
    return [service.submission_card(db, s) for s in rows]


@router.get("/submissions/{submission_id}", response_model=SubmissionOut)
def get_submission(submission_id: int, db: Db, user: CurrentUser):
    return service.submission_out(db, _submission(db, submission_id, user))


@router.get("/forks")
def journal(db: Db, user: CurrentUser):
    return service.fork_journal(db, user)


@router.get("/forks/export.md", response_class=PlainTextResponse)
def journal_export(db: Db, user: CurrentUser):
    return PlainTextResponse(
        service.journal_markdown(service.fork_journal(db, user)), media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="DECISIONS.md"'},
    )


# ---------- Мастерская ----------


@admin_router.get("/rubric", response_model=RubricOut)
def get_rubric(db: Db, _: AdminUser):
    return service.rubric_out(service.active_rubric(db))


@admin_router.put("/rubric", response_model=RubricOut)
def put_rubric(payload: RubricIn, db: Db, admin: AdminUser):
    try:
        return service.rubric_out(service.save_rubric(db, admin, payload.criteria, payload.mismatch_penalty, payload.note))
    except service.AssessError as exc:
        raise _bad(exc) from exc


@admin_router.get("/references", response_model=list[ReferenceOut])
def references(db: Db, _: AdminUser):
    return [ReferenceOut(id=r.id, name=r.name, url=r.url, about=r.about) for r in db.scalars(select(ReferenceProject).order_by(ReferenceProject.id))]


@admin_router.post("/references", response_model=ReferenceOut, status_code=status.HTTP_201_CREATED)
def add_reference(payload: ReferenceIn, db: Db, _: AdminUser):
    r = ReferenceProject(**payload.model_dump())
    db.add(r)
    db.commit()
    return ReferenceOut(id=r.id, **payload.model_dump())


@admin_router.put("/references/{ref_id}", response_model=ReferenceOut)
def edit_reference(ref_id: int, payload: ReferenceIn, db: Db, _: AdminUser):
    r = db.get(ReferenceProject, ref_id)
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Эталон не найден")
    for k, v in payload.model_dump().items():
        setattr(r, k, v)
    db.commit()
    return ReferenceOut(id=r.id, **payload.model_dump())


@admin_router.delete("/references/{ref_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_reference(ref_id: int, db: Db, _: AdminUser):
    r = db.get(ReferenceProject, ref_id)
    if r is not None:
        db.delete(r)
        db.commit()


@admin_router.get("/assignments", response_model=list[AssignmentAdminOut])
def admin_assignments(db: Db, _: AdminUser):
    return [service.assignment_admin_out(db, a) for a in db.scalars(select(Assignment).order_by(Assignment.id))]


@admin_router.post("/assignments", response_model=AssignmentAdminOut, status_code=status.HTTP_201_CREATED)
def create_assignment(payload: AssignmentIn, db: Db, _: AdminUser):
    a = Assignment(slug=service.unique_slug(db, payload.title))
    try:
        service.apply_assignment(a, payload)
    except service.AssessError as exc:
        raise _bad(exc) from exc
    db.add(a)
    db.commit()
    return service.assignment_admin_out(db, a)


@admin_router.put("/assignments/{assignment_id}", response_model=AssignmentAdminOut)
def edit_assignment(assignment_id: int, payload: AssignmentIn, db: Db, _: AdminUser):
    a = db.get(Assignment, assignment_id)
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Практикум не найден")
    try:
        service.apply_assignment(a, payload)
    except service.AssessError as exc:
        raise _bad(exc) from exc
    db.commit()
    return service.assignment_admin_out(db, a)


@admin_router.get("/submissions", response_model=list[SubmissionCard])
def all_submissions(db: Db, _: AdminUser):
    rows = db.scalars(select(Submission).order_by(Submission.id.desc()).limit(200))
    return [service.submission_card(db, s) for s in rows]
