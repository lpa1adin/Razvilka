from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, StringConstraints
from sqlalchemy import delete, select

from app.core.security import hash_password
from app.modules.auth.deps import AdminUser, Db
from app.modules.auth.models import Role, User, UserSession
from app.modules.auth.service import create_user

router = APIRouter(prefix="/api/workshop/users", tags=["workshop"])

Password = Annotated[str, StringConstraints(min_length=8, max_length=256)]


class UserRow(BaseModel):
    id: int
    login: str
    display_name: str
    role: Role
    created_at: datetime

    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    login: Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, pattern=r"^[A-Za-z0-9._-]{3,64}$")]
    display_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    role: Role = Role.user
    password: Password


class PasswordIn(BaseModel):
    password: Password


@router.get("", response_model=list[UserRow])
def list_users(db: Db, _: AdminUser):
    return db.scalars(select(User).order_by(User.role.desc(), User.login)).all()


@router.post("", response_model=UserRow, status_code=status.HTTP_201_CREATED)
def add_user(payload: UserCreate, db: Db, _: AdminUser):
    if db.scalar(select(User.id).where(User.login == payload.login)):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Логин {payload.login} уже занят")
    return create_user(db, payload.login, payload.password, payload.role, payload.display_name)


@router.post("/{user_id}/password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(user_id: int, payload: PasswordIn, db: Db, _: AdminUser):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Пользователь не найден")
    user.password_hash = hash_password(payload.password)
    # Старые сессии больше не действуют: с другого устройства по старому паролю не войти
    db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    db.commit()
