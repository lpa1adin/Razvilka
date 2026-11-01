from sqlalchemy import Select, case, func, select
from sqlalchemy.orm import Session, joinedload

from app.modules.library.models import Fragment, FragmentStatus, Source
from app.modules.library.schemas import FragmentBrief, FragmentOut, SearchOut, SourceOut

_HEADLINE = "StartSel=\x01, StopSel=\x02, MaxWords=28, MinWords=12, MaxFragments=1"


def fragment_brief(fragment: Fragment, snippet: str | None = None) -> FragmentBrief:
    return FragmentBrief(
        id=fragment.id,
        title=fragment.title,
        section=fragment.section,
        url=fragment.url,
        status=fragment.status,
        source=SourceOut.model_validate(fragment.source),
        excerpt=fragment.excerpt,
        snippet=snippet,
    )


def search(db: Session, q: str, source: str | None, limit: int, offset: int) -> SearchOut:
    base: Select = select(Fragment).join(Source).where(Fragment.status == FragmentStatus.active)
    if source:
        base = base.where(Source.slug == source)

    query = q.strip()
    if not query:
        total = db.scalar(select(func.count()).select_from(base.subquery()))
        rows = db.scalars(
            base.options(joinedload(Fragment.source)).order_by(Source.slug, Fragment.external_id).limit(limit).offset(offset)
        )
        return SearchOut(total=total or 0, items=[fragment_brief(f) for f in rows])

    # websearch_to_tsquery понимает «кавычки» и -исключения, как поисковики
    ts_query = func.websearch_to_tsquery("russian", query)
    matched = base.where(Fragment.search.op("@@")(ts_query))
    total = db.scalar(select(func.count()).select_from(matched.subquery()))
    # Совпадение в названии статьи важнее, чем десяток упоминаний в тексте
    title_hit = case((func.to_tsvector("russian", Fragment.title).op("@@")(ts_query), 1.0), else_=0.0)
    rank = func.ts_rank_cd(Fragment.search, ts_query) + title_hit
    snippet = func.ts_headline("russian", Fragment.plain_text, ts_query, _HEADLINE)
    rows = db.execute(
        matched.add_columns(snippet).options(joinedload(Fragment.source)).order_by(rank.desc(), Fragment.id).limit(limit).offset(offset)
    ).all()
    return SearchOut(total=total or 0, items=[fragment_brief(f, s or None) for f, s in rows])


def fragment_out(fragment: Fragment) -> FragmentOut:
    return FragmentOut(
        id=fragment.id,
        title=fragment.title,
        section=fragment.section,
        url=fragment.url,
        status=fragment.status,
        content_html=fragment.content_html,
        outline=fragment.outline,
        source=SourceOut.model_validate(fragment.source),
        source_commit=fragment.source_commit,
        imported_at=fragment.imported_at,
        changed_at=fragment.changed_at,
    )


def get_fragment(db: Session, fragment_id: int) -> Fragment | None:
    return db.scalar(select(Fragment).options(joinedload(Fragment.source)).where(Fragment.id == fragment_id))
