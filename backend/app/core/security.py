import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerificationError:
        return False


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> str:
    # В БД лежит только хэш токена: утечка таблицы сессий не даёт войти под чужой сессией.
    return hashlib.sha256(token.encode()).hexdigest()
