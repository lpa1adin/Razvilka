"""Сборщик: забирает источник из git, проверяет лицензию, разбирает статьи и обновляет библиотеку."""

import hashlib
import json
import logging
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.library import parsers
from app.modules.library.models import (
    Fragment,
    FragmentStatus,
    ImportRun,
    LicenseStatus,
    RunStatus,
    Source,
)
from app.modules.library.sources import SOURCES, SourceSpec

log = logging.getLogger("collector")


class ImportStopped(Exception):
    """Импорт остановлен намеренно — это не сбой кода."""


class LicenseChanged(ImportStopped):
    """Лицензия источника могла измениться: импорт ждёт проверки админом."""


def _git(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args[:2])}: {result.stderr.strip()[:500]}")
    return result.stdout


def sync_repo(spec: SourceSpec, cache: Path) -> tuple[Path, str, datetime]:
    """Неглубокая копия только нужных файлов (sparse checkout): без истории и картинок."""
    repo_dir = cache / spec.slug
    if not (repo_dir / ".git").exists():
        cache.mkdir(parents=True, exist_ok=True)
        _git("clone", "--depth", "1", "--filter=blob:none", "--sparse", spec.repo, str(repo_dir))
    else:
        _git("fetch", "--depth", "1", "origin", cwd=repo_dir)
        _git("reset", "--hard", "FETCH_HEAD", cwd=repo_dir)
    _git("sparse-checkout", "set", "--no-cone", *spec.patterns, cwd=repo_dir)
    sha, date = _git("log", "-1", "--format=%H%n%cI", cwd=repo_dir).split()
    return repo_dir, sha, datetime.fromisoformat(date)


def ensure_source(db: Session, spec: SourceSpec) -> Source:
    source = db.scalar(select(Source).where(Source.slug == spec.slug))
    if source is None:
        source = Source(slug=spec.slug)
        db.add(source)
    # Описание и лицензия берутся из кода (белый список) и обновляются при каждом импорте
    for name in ("title", "author", "kind", "homepage", "license_name", "license_url", "license_mode", "license_note"):
        setattr(source, name, getattr(spec, name))
    db.flush()
    return source


def check_license(source: Source, spec: SourceSpec, repo_dir: Path) -> None:
    text = (repo_dir / spec.license_file).read_text(encoding="utf-8")
    digest = hashlib.sha256(text.encode()).hexdigest()
    if spec.license_marker not in text:
        raise LicenseChanged(
            f"В {spec.license_file} больше нет «{spec.license_marker}». Лицензия могла смениться — "
            "проверьте её и обновите белый список в app/modules/library/sources.py."
        )
    if source.license_status is LicenseStatus.needs_review:
        raise LicenseChanged("Файл лицензии изменился. Прочитайте его и подтвердите в Мастерской → Источники.")
    if source.license_hash and source.license_hash != digest:
        raise LicenseChanged("Файл лицензии изменился с прошлого импорта. Прочитайте его и подтвердите в Мастерской → Источники.")
    source.license_hash = digest


def collect_articles(spec: SourceSpec, repo_dir: Path, commit: str) -> list[parsers.Article]:
    articles: list[parsers.Article] = []
    section_titles: dict[str, str] = {}

    if spec.parser == "mdn":
        raw_base = f"https://raw.githubusercontent.com/mdn/translated-content/{commit}/"
        # Список всех файлов берём из дерева git — сами картинки не скачиваем
        existing = set(_git("ls-tree", "-r", "--name-only", "HEAD", "files/ru", cwd=repo_dir).splitlines())
        for file in sorted(repo_dir.glob("files/ru/**/index.md")):
            path = file.relative_to(repo_dir).as_posix()
            article = parsers.parse_mdn(path, file.read_text(encoding="utf-8"), raw_base, existing)
            if article:
                articles.append(article)
                section_titles[path.rsplit("/", 1)[0]] = article.title
    elif spec.parser == "jsinfo":
        for file in sorted(repo_dir.glob("*/**/index.md")):
            title = parsers.jsinfo_section_title(file.read_text(encoding="utf-8"))
            if title:
                section_titles[file.relative_to(repo_dir).parent.as_posix()] = title
        for file in sorted(repo_dir.glob("*/**/article.md")):
            path = file.relative_to(repo_dir).as_posix()
            article = parsers.parse_jsinfo(path, file.read_text(encoding="utf-8"))
            if article:
                articles.append(article)
    elif spec.parser == "owasp":
        raw_base = f"https://raw.githubusercontent.com/OWASP/CheatSheetSeries/{commit}/"
        for file in sorted(repo_dir.glob("cheatsheets/*.md")):
            article = parsers.parse_owasp(file.relative_to(repo_dir).as_posix(), file.read_text(encoding="utf-8"), raw_base)
            if article:
                articles.append(article)
    elif spec.parser == "pydocs":
        for file in sorted(repo_dir.glob("Doc/*/*.rst")):
            article = parsers.parse_pydocs(file.relative_to(repo_dir).as_posix(), file.read_text(encoding="utf-8"))
            if article:
                articles.append(article)
                section_titles.setdefault(article.parent_key, article.section)
    else:
        raise ValueError(f"Нет парсера {spec.parser!r}")

    for article in articles:
        article.section = section_titles.get(article.parent_key, article.section)
    return articles


def _hash(article: parsers.Article) -> str:
    payload = json.dumps([article.title, article.content_html, article.outline, article.url], ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def apply_articles(db: Session, source: Source, articles: list[parsers.Article], commit: str, run: ImportRun) -> None:
    existing = {f.external_id: f for f in db.scalars(select(Fragment).where(Fragment.source_id == source.id))}
    now = datetime.now(UTC)
    seen = set()

    for article in articles:
        seen.add(article.external_id)
        digest = _hash(article)
        fragment = existing.get(article.external_id)
        if fragment is None:
            fragment = Fragment(source_id=source.id, external_id=article.external_id)
            db.add(fragment)
            run.added += 1
        elif fragment.content_hash == digest and fragment.status is FragmentStatus.active:
            run.unchanged += 1
            continue
        else:
            # Статья изменилась в источнике — админ должен перечитать уроки, где она используется
            run.changed += 1
            fragment.needs_review = True
            fragment.changed_at = now
        fragment.title = article.title[:300]
        fragment.section = article.section[:300]
        fragment.url = article.url
        fragment.content_html = article.content_html
        fragment.outline = article.outline
        fragment.excerpt = article.excerpt
        fragment.plain_text = article.plain_text
        fragment.content_hash = digest
        fragment.status = FragmentStatus.active
        fragment.source_commit = commit

    for external_id, fragment in existing.items():
        if external_id not in seen and fragment.status is FragmentStatus.active:
            fragment.status = FragmentStatus.removed
            fragment.needs_review = True
            fragment.changed_at = now
            run.removed += 1


def run_import(db: Session, slug: str) -> dict:
    spec = SOURCES.get(slug)
    if spec is None:
        raise ValueError(f"Источника {slug!r} нет в белом списке")

    source = ensure_source(db, spec)
    run = ImportRun(source_id=source.id)
    db.add(run)
    db.commit()

    try:
        repo_dir, commit, commit_at = sync_repo(spec, Path(settings.sources_cache))
        run.commit = commit
        check_license(source, spec, repo_dir)
        articles = collect_articles(spec, repo_dir, commit)
        if not articles:
            raise ImportStopped("В источнике не нашлось ни одной статьи — проверьте шаблоны путей.")
        apply_articles(db, source, articles, commit, run)
        source.last_commit, source.last_commit_at = commit, commit_at
        source.last_import_at = datetime.now(UTC)
        run.status = RunStatus.done
    except Exception as exc:
        db.rollback()  # частично применённые изменения библиотеки не сохраняем
        source = db.get(Source, source.id)
        run = db.get(ImportRun, run.id)
        if isinstance(exc, LicenseChanged):
            source.license_status = LicenseStatus.needs_review
        run.status = RunStatus.failed
        run.error = str(exc)[:2000]
        if not isinstance(exc, ImportStopped):
            log.exception("импорт %s упал", slug)
    finally:
        run.finished_at = datetime.now(UTC)
        db.commit()

    if run.status is RunStatus.failed:
        raise ImportStopped(run.error or "Импорт не удался")
    return {"added": run.added, "changed": run.changed, "removed": run.removed, "unchanged": run.unchanged}
