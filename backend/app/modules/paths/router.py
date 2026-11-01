from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import select

from app.modules.auth.deps import CurrentUser, Db
from app.modules.auth.models import Role, User
from app.modules.library.render import render_markdown
from app.modules.paths import service
from app.modules.paths.models import ProjectPath

router = APIRouter(prefix="/api/paths", tags=["paths"])
preview_router = APIRouter(prefix="/api/preview", tags=["paths"])


def _path(db: Db, slug: str, user: User) -> ProjectPath:
    path = db.scalar(select(ProjectPath).where(ProjectPath.slug == slug))
    # Черновик пути видит только админ (предпросмотр); пользователь — только опубликованное
    if path is None or (not path.published and user.role is not Role.admin):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Путь не найден")
    return path


@router.get("")
def paths(db: Db, user: CurrentUser):
    out = []
    for path in db.scalars(select(ProjectPath).where(ProjectPath.published.is_(True)).order_by(ProjectPath.id)):
        states = service.stage_states(db, user, path)
        out.append({
            "slug": path.slug, "title": path.title, "description": path.description, "project": path.project,
            "stages": len(states), "passed": sum(s["state"] == "passed" for s in states),
            "workspace": service.workspace_info(user, path)["exists"],
        })
    return out


@router.get("/{slug}")
def path_detail(slug: str, db: Db, user: CurrentUser):
    path = _path(db, slug, user)
    states = service.stage_states(db, user, path)
    return {
        "slug": path.slug, "title": path.title, "description": path.description, "project": path.project, "kind": path.kind,
        "published": path.published, "map": service.project_map(path), "workspace": service.workspace_info(user, path),
        "stages": [
            {
                "n": i, "slug": s["assignment"].slug, "title": s["assignment"].title, "goal": s["assignment"].goal,
                "goal_html": render_markdown(s["assignment"].goal), "files": s["assignment"].files_hint,
                "theory": service.fragments(db, s["assignment"].fragment_ids), "forks": len(s["assignment"].forks),
                "state": s["state"], "attempts": s["attempts"], "best": s["best"], "running": s["running"], "last_submission": s["last_id"],
            }
            for i, s in enumerate(states, 1)
        ],
    }


@router.post("/{slug}/workspace")
def create_workspace(slug: str, db: Db, user: CurrentUser):
    path = _path(db, slug, user)
    return service.create_workspace(user, path, [a.title for a in service.stages(db, path)])


@router.get("/{slug}/preview")
def preview_link(slug: str, db: Db, user: CurrentUser):
    path = _path(db, slug, user)
    return {"url": f"/api/preview/{service.preview_token(user, path)}/index.html"}


@preview_router.get("/{token}/{rel:path}")
def preview(token: str, rel: str, db: Db):
    try:
        data, media = service.preview_file(db, token, rel)
    except service.PathError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Файла нет в рабочей папке") from exc
    return Response(data, media_type=media, headers={
        # Страница ученика — в изолированном источнике: без доступа к cookie и API платформы
        "Content-Security-Policy": "sandbox allow-scripts allow-forms allow-popups; default-src 'self' 'unsafe-inline' data: blob:; connect-src 'none'",
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    })
