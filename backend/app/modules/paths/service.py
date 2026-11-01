"""Пути «напиши заново сам»: рабочая папка, этапы по порядку, карта проекта и превью (BRIEF §5.5)."""

import hashlib
import hmac
import mimetypes
import os
import secrets
import time
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.assess.models import Assignment, Submission, SubmissionStatus
from app.modules.auth.models import User
from app.modules.library.models import Fragment
from app.modules.paths.models import ProjectPath
from app.modules.projectmap.graph import SECRET, build

PREVIEW_TTL = 4 * 3600
# Ключ подписи ссылок превью живёт в памяти процесса api: после перезапуска ссылки просто выдаются заново
_KEY = secrets.token_bytes(32)


class PathError(Exception):
    pass


def stages(db: Session, path: ProjectPath) -> list[Assignment]:
    return list(db.scalars(select(Assignment).where(Assignment.path_id == path.id).order_by(Assignment.position)))


# ---------- Рабочая папка ----------


def workspace_dir(user: User, path: ProjectPath) -> Path:
    return Path(settings.workspace_root) / user.login / path.slug


def workspace_info(user: User, path: ProjectPath) -> dict:
    folder = workspace_dir(user, path)
    files = [p for p in folder.rglob("*") if p.is_file() and ".git" not in p.parts] if folder.is_dir() else []
    return {
        "exists": folder.is_dir(), "files": len(files),
        "host_path": f"{settings.workspace_host}/{user.login}/{path.slug}",
        "list": sorted(str(p.relative_to(folder)) for p in files)[:60],
    }


def create_workspace(user: User, path: ProjectPath, stage_titles: list[str]) -> dict:
    """Пустая папка с README: оригинал не копируется — проект пишется заново, с нуля."""
    folder = workspace_dir(user, path)
    folder.mkdir(parents=True, exist_ok=True)
    readme = folder / "README.md"
    if not readme.exists():
        lines = [f"# {path.title}", "", f"Рабочая папка пути «напиши заново сам» по проекту {path.project}.",
                 "Оригинал не копируется: проект пишется заново, этап за этапом.", "", "## Этапы", ""]
        lines += [f"{n}. {t}" for n, t in enumerate(stage_titles, 1)]
        readme.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return workspace_info(user, path)


# ---------- Этапы по порядку ----------


def stage_states(db: Session, user: User, path: ProjectPath) -> list[dict]:
    """passed — этап засчитан; open — текущий; locked — ждёт предыдущий. Этапы строятся друг на друге."""
    out, previous_passed = [], True
    for a in stages(db, path):
        subs = list(db.scalars(select(Submission).where(Submission.user_id == user.id, Submission.assignment_id == a.id).order_by(Submission.id.desc())))
        passed = any(s.passed for s in subs)
        running = any(s.status not in (SubmissionStatus.done, SubmissionStatus.failed) for s in subs)
        state = "passed" if passed else ("open" if previous_passed else "locked")
        best = max((s.score for s in subs if s.score is not None), default=None)
        out.append({"assignment": a, "state": state, "attempts": len(subs), "best": best, "running": running, "last_id": subs[0].id if subs else None})
        previous_passed = previous_passed and passed
    return out


def check_order(db: Session, user: User, a: Assignment) -> None:
    path = db.get(ProjectPath, a.path_id)
    for st in stage_states(db, user, path):
        if st["assignment"].id == a.id:
            if st["state"] == "locked":
                raise PathError("Сначала сдайте предыдущий этап: каждый следующий строится поверх него.")
            return


# ---------- Карта проекта ----------


def project_map(path: ProjectPath) -> dict:
    """Граф оригинала без Claude (файлы и связи) + роли частей от Claude. Код оригинала ученику не показываем —
    только устройство: проект пишется заново."""
    root = Path(settings.projects_root) / path.project
    if not root.is_dir():
        return {"nodes": [], "edges": [], "roles": path.roles, "languages": {}}
    graph = build(root)
    kind = {"HTML": "html", "CSS": "css", "JavaScript": "js", "TypeScript": "js", "Python": "py", "Markdown": "md", "JSON": "data"}
    nodes = [{"id": p, "label": p, "kind": kind.get(n["lang"], "data"), "detail": f"{n['lang']}, {n['lines']} строк"} for p, n in graph["nodes"].items()]
    nodes += [{"id": v, "label": v, "kind": "external", "detail": "библиотека"} for v in graph["vendor"]]
    edges = [{"from": a, "to": b, "kind": k} for a, b, k in graph["edges"]]
    return {"nodes": nodes, "edges": edges, "roles": path.roles, "languages": graph["languages"]}


def fragments(db: Session, ids: list[int]) -> list[dict]:
    rows = db.scalars(select(Fragment).where(Fragment.id.in_(ids)))
    return [{"id": f.id, "title": f.title} for f in rows]


# ---------- Превью рабочей папки ----------


def preview_token(user: User, path: ProjectPath) -> str:
    expires = int(time.time()) + PREVIEW_TTL
    payload = f"{user.id}.{path.id}.{expires}"
    sig = hmac.new(_KEY, payload.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{payload}.{sig}"


def preview_file(db: Session, token: str, rel: str) -> tuple[bytes, str]:
    """Файл рабочей папки по подписанной ссылке. Отдаётся с CSP sandbox: код ученика выполняется в
    изолированном источнике и не может обратиться к API платформы от имени пользователя."""
    try:
        user_id, path_id, expires, sig = token.split(".")
        payload = f"{user_id}.{path_id}.{expires}"
        good = hmac.compare_digest(sig, hmac.new(_KEY, payload.encode(), hashlib.sha256).hexdigest()[:32])
    except ValueError:
        good = False
    if not good or int(expires) < time.time():
        raise PathError("Ссылка превью устарела — обновите страницу")
    user = db.get(User, int(user_id))
    path = db.get(ProjectPath, int(path_id))
    folder = workspace_dir(user, path).resolve()
    target = (folder / (rel or "index.html")).resolve()
    if target.is_dir():
        target = target / "index.html"
    if not str(target).startswith(str(folder) + os.sep) or not target.is_file() or SECRET.match(target.name):
        raise FileNotFoundError(rel)
    media = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    return target.read_bytes(), media
