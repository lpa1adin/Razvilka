from fastapi import APIRouter
from sqlalchemy import func, select

from app.modules.auth.deps import AdminUser, Db
from app.modules.auth.models import User
from app.modules.jobs.models import Job

# Весь роутер Мастерской закрыт require_admin: пользователь получает 403 даже по прямому запросу.
router = APIRouter(prefix="/api/workshop", tags=["workshop"])


@router.get("/overview")
def overview(db: Db, _: AdminUser):
    users = dict(db.execute(select(User.role, func.count()).group_by(User.role)).all())
    jobs = dict(db.execute(select(Job.status, func.count()).group_by(Job.status)).all())
    return {
        "users": {role.value: count for role, count in users.items()},
        "jobs": {status.value: count for status, count in jobs.items()},
    }
