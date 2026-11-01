from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.modules.jobs.models import Job
from app.modules.library.importer import LicenseChanged, apply_articles, check_license, ensure_source
from app.modules.library.models import Fragment, FragmentStatus, ImportRun, Source
from app.modules.library.parsers import Article
from app.modules.library.sources import SOURCES
from app.modules.auth.models import Role
from tests.conftest import login_as, make_fragment, make_user


def test_search_uses_russian_morphology_and_marks_matches(client):
    make_user("anna", Role.user)
    login_as(client, "anna")
    make_fragment("Flexbox", "Элементы располагаются вдоль главной оси контейнера")
    make_fragment("Grid", "Сетка из строк и колонок")

    result = client.get("/api/library/fragments", params={"q": "элемент"}).json()
    assert result["total"] == 1
    item = result["items"][0]
    assert item["title"] == "Flexbox"
    assert "\x01Элементы\x02" in item["snippet"]
    assert item["source"]["license_name"] == "CC BY-SA 2.5"


def test_removed_fragments_are_hidden_from_search(client):
    make_user("anna", Role.user)
    login_as(client, "anna")
    make_fragment("Старое", "устаревшая статья", status=FragmentStatus.removed)
    assert client.get("/api/library/fragments", params={"q": "статья"}).json()["total"] == 0


def _article(path: str, title: str, text: str) -> Article:
    return Article(external_id=path, title=title, url="https://x/" + path, parent_key="", content_html=f"<p>{text}</p>", plain_text=text)


def test_reimport_counts_added_changed_removed_and_flags_review():
    with SessionLocal() as db:
        source = ensure_source(db, SOURCES["mdn-ru"])
        run1 = ImportRun(source_id=source.id)
        db.add(run1)
        apply_articles(db, source, [_article("a", "A", "один"), _article("b", "B", "два")], "c1", run1)
        db.commit()
        assert (run1.added, run1.changed, run1.removed) == (2, 0, 0)

        run2 = ImportRun(source_id=source.id)
        db.add(run2)
        apply_articles(db, source, [_article("a", "A", "один"), _article("c", "C", "три")], "c2", run2)
        db.commit()
        # «a» не изменилась, «c» новая, «b» пропала из источника
        assert (run2.added, run2.changed, run2.removed, run2.unchanged) == (1, 0, 1, 1)
        b = db.scalar(select(Fragment).where(Fragment.external_id == "b"))
        assert b.status is FragmentStatus.removed and b.needs_review

        run3 = ImportRun(source_id=source.id)
        db.add(run3)
        apply_articles(db, source, [_article("a", "A", "один, но новее"), _article("c", "C", "три")], "c3", run3)
        db.commit()
        a = db.scalar(select(Fragment).where(Fragment.external_id == "a"))
        assert run3.changed == 1 and a.needs_review and a.source_commit == "c3"


def test_license_change_stops_import(tmp_path: Path):
    spec = SOURCES["mdn-ru"]
    (tmp_path / spec.license_file).write_text("prose under CC-BY-SA 2.5", encoding="utf-8")
    with SessionLocal() as db:
        source = ensure_source(db, spec)
        check_license(source, spec, tmp_path)  # первый раз — запоминаем
        assert source.license_hash

        (tmp_path / spec.license_file).write_text("prose under CC-BY-SA 2.5, now with extra terms", encoding="utf-8")
        with pytest.raises(LicenseChanged):
            check_license(source, spec, tmp_path)

        (tmp_path / spec.license_file).write_text("All rights reserved", encoding="utf-8")
        with pytest.raises(LicenseChanged):
            check_license(source, spec, tmp_path)


def test_admin_can_queue_import_once(admin_client):
    assert admin_client.post("/api/workshop/sources/mdn-ru/import").status_code == 202
    assert admin_client.post("/api/workshop/sources/mdn-ru/import").status_code == 409
    assert admin_client.post("/api/workshop/sources/evil/import").status_code == 404
    with SessionLocal() as db:
        assert db.scalar(select(Job.payload)) == {"type": "import_source", "source": "mdn-ru"}
    sources = admin_client.get("/api/workshop/sources").json()
    assert {s["slug"] for s in sources} == set(SOURCES)
    assert next(s for s in sources if s["slug"] == "mdn-ru")["import_pending"] is True


def test_user_cannot_manage_sources(client):
    make_user("anna", Role.user)
    login_as(client, "anna")
    assert client.post("/api/workshop/sources/mdn-ru/import").status_code == 403
    assert client.get("/api/workshop/fragments/review").status_code == 403
