from fastapi import APIRouter, HTTPException, Request, Response, status

from app.core.config import settings
from app.modules.auth import service
from app.modules.auth.deps import CurrentUser, Db
from app.modules.auth.schemas import LoginIn, SessionOut, UserOut
from app.modules.auth.service import user_by_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=UserOut)
def login(payload: LoginIn, response: Response, db: Db):
    user = service.authenticate(db, payload.login, payload.password)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный логин или пароль")
    token = service.open_session(db, user)
    response.set_cookie(
        settings.session_cookie,
        token,
        max_age=settings.session_days * 86400,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: Db):
    token = request.cookies.get(settings.session_cookie)
    if token:
        service.close_session(db, token)
    response.delete_cookie(settings.session_cookie, path="/")


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser):
    return user


@router.get("/session", response_model=SessionOut)
def session(request: Request, db: Db):
    """Кто вошёл — для старта интерфейса. Без входа — 200 и user: null, а не 401 в консоли браузера."""
    token = request.cookies.get(settings.session_cookie)
    return SessionOut(user=user_by_token(db, token) if token else None)

