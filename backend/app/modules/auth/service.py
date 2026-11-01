from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password, new_session_token, token_digest, verify_password
from app.modules.auth.models import Role, User, UserSession

# Хэш для несуществующего логина: проверка занимает столько же времени,
# и по задержке ответа нельзя узнать, есть ли такой пользователь.
_DUMMY_HASH = hash_password("timing-equalizer")


def authenticate(db: Session, login: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.login == login.strip().lower()))
    if user is None:
        verify_password(_DUMMY_HASH, password)
        return None
    return user if verify_password(user.password_hash, password) else None


def open_session(db: Session, user: User) -> str:
    token = new_session_token()
    expires = datetime.now(UTC) + timedelta(days=settings.session_days)
    db.add(UserSession(token_hash=token_digest(token), user_id=user.id, expires_at=expires))
    db.commit()
    return token


def close_session(db: Session, token: str) -> None:
    db.execute(delete(UserSession).where(UserSession.token_hash == token_digest(token)))
    db.commit()


def user_by_token(db: Session, token: str) -> User | None:
    row = db.get(UserSession, token_digest(token))
    if row is None:
        return None
    if row.expires_at <= datetime.now(UTC):
        db.delete(row)
        db.commit()
        return None
    return db.get(User, row.user_id)


def create_user(db: Session, login: str, password: str, role: Role, display_name: str | None = None) -> User:
    user = User(
        login=login.strip().lower(),
        display_name=display_name or login,
        password_hash=hash_password(password),
        role=role,
    )
    db.add(user)
    db.commit()
    return user


def ensure_bootstrap_users(db: Session) -> None:
    """Создаёт учётки из .env, если таких логинов ещё нет. Существующие пароли не трогает."""
    pairs = [
        (settings.admin_login, settings.admin_password, Role.admin),
        (settings.user_login, settings.user_password, Role.user),
    ]
    for login, password, role in pairs:
        if not login or not password:
            continue
        if db.scalar(select(User.id).where(User.login == login.strip().lower())) is None:
            create_user(db, login, password, role)
