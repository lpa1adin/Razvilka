from datetime import datetime

from pydantic import BaseModel

from app.modules.library.models import FragmentStatus, LicenseMode, LicenseStatus


class SourceOut(BaseModel):
    slug: str
    title: str
    author: str
    kind: str
    homepage: str
    license_name: str
    license_url: str
    license_mode: LicenseMode
    license_note: str
    last_commit: str | None
    last_commit_at: datetime | None

    model_config = {"from_attributes": True}


class FragmentBrief(BaseModel):
    id: int
    title: str
    section: str
    url: str
    status: FragmentStatus
    source: SourceOut
    excerpt: str
    # Фрагмент текста с совпадениями: части между \x01 и \x02 — найденные слова.
    # Не HTML, чтобы интерфейсу не пришлось вставлять разметку из базы.
    snippet: str | None = None


class FragmentOut(BaseModel):
    id: int
    title: str
    section: str
    url: str
    status: FragmentStatus
    content_html: str | None
    outline: list[dict]
    source: SourceOut
    source_commit: str
    imported_at: datetime
    changed_at: datetime | None


class SearchOut(BaseModel):
    total: int
    items: list[FragmentBrief]


class ImportRunOut(BaseModel):
    id: int
    status: str
    started_at: datetime
    finished_at: datetime | None
    commit: str | None
    added: int
    changed: int
    removed: int
    unchanged: int
    error: str | None

    model_config = {"from_attributes": True}


class SourceAdminOut(SourceOut):
    license_status: LicenseStatus
    last_import_at: datetime | None
    fragments: int
    needs_review: int
    runs: list[ImportRunOut]
    import_pending: bool
