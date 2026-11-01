from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.modules.auth.models import Role, User
from app.modules.auth.service import user_by_token

Db = Annotated[Session, Depends(get_db)]


def current_user(request: Request, db: Db) -> User:
    token = request.cookies.get(settings.session_cookie)
    user = user_by_token(db, token) if token else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Войдите, чтобы продолжить")
    return user


def require_admin(user: Annotated[User, Depends(current_user)]) -> User:
    # Права проверяются здесь, на сервере: скрытая кнопка в интерфейсе — не защита.
    if user.role is not Role.admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Раздел доступен только администратору")
    return user


CurrentUser = Annotated[User, Depends(current_user)]
AdminUser = Annotated[User, Depends(require_admin)]
