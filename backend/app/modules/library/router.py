from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.modules.auth.deps import AdminUser, CurrentUser, Db
from app.modules.jobs.queue import enqueue, has_pending
from app.modules.library import service
from app.modules.library.models import Fragment, ImportRun, LicenseStatus, Source
from app.modules.library.schemas import FragmentOut, ImportRunOut, SearchOut, SourceAdminOut, SourceOut
from app.modules.library.sources import SOURCES

router = APIRouter(prefix="/api/library", tags=["library"])
admin_router = APIRouter(prefix="/api/workshop/sources", tags=["workshop"])


@router.get("/sources", response_model=list[SourceOut])
def list_sources(db: Db, _: CurrentUser):
    return db.scalars(select(Source).order_by(Source.title)).all()


@router.get("/fragments", response_model=SearchOut)
def search_fragments(
    db: Db,
    _: CurrentUser,
    q: str = Query("", max_length=200),
    source: str | None = None,
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
):
    return service.search(db, q, source, limit, offset)


@router.get("/fragments/{fragment_id}", response_model=FragmentOut)
def get_fragment(fragment_id: int, db: Db, _: CurrentUser):
    fragment = service.get_fragment(db, fragment_id)
    if fragment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Такого фрагмента нет в библиотеке")
    return service.fragment_out(fragment)


# ---------- Мастерская ----------


@admin_router.get("", response_model=list[SourceAdminOut])
def admin_sources(db: Db, _: AdminUser):
    result = []
    by_slug = {s.slug: s for s in db.scalars(select(Source))}
    for slug, spec in SOURCES.items():
        source = by_slug.get(slug)
        counts = (0, 0)
        runs: list[ImportRun] = []
        if source is not None:
            counts = db.execute(
                select(func.count(), func.count().filter(Fragment.needs_review)).where(Fragment.source_id == source.id)
            ).one()
            runs = list(db.scalars(select(ImportRun).where(ImportRun.source_id == source.id).order_by(ImportRun.id.desc()).limit(5)))
        result.append(
            SourceAdminOut(
                slug=slug,
                title=spec.title,
                author=spec.author,
                kind=spec.kind,
                homepage=spec.homepage,
                license_name=spec.license_name,
                license_url=spec.license_url,
                license_mode=spec.license_mode,
                license_note=spec.license_note,
                last_commit=source.last_commit if source else None,
                last_commit_at=source.last_commit_at if source else None,
                license_status=source.license_status if source else LicenseStatus.ok,
                last_import_at=source.last_import_at if source else None,
                fragments=counts[0],
                needs_review=counts[1],
                runs=[ImportRunOut.model_validate(r) for r in runs],
                import_pending=has_pending(db, "collector", source=slug),
            )
        )
    return result


@admin_router.post("/{slug}/import", status_code=status.HTTP_202_ACCEPTED)
def start_import(slug: str, db: Db, _: AdminUser):
    if slug not in SOURCES:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Такого источника нет в белом списке")
    if has_pending(db, "collector", source=slug):
        raise HTTPException(status.HTTP_409_CONFLICT, "Импорт этого источника уже идёт")
    enqueue(db, "collector", {"type": "import_source", "source": slug})
    return {"queued": True}


@admin_router.post("/{slug}/confirm-license", status_code=status.HTTP_204_NO_CONTENT)
def confirm_license(slug: str, db: Db, _: AdminUser):
    source = db.scalar(select(Source).where(Source.slug == slug))
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Источник ещё не импортировался")
    # Новый файл лицензии запомнится при следующем импорте
    source.license_status = LicenseStatus.ok
    source.license_hash = None
    db.commit()
