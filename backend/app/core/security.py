from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from app.core.config import get_settings

settings = get_settings()


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())

settings = get_settings()


class AuthError(Exception):
    pass


def create_access_token(subject: str, email: str) -> str:
    if not settings.secret_key:
        raise AuthError('SECRET_KEY is required for authentication.')

    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload: dict[str, Any] = {
        'sub': subject,
        'email': email,
        'exp': expire,
    }
    return jwt.encode(payload, settings.secret_key, algorithm='HS256')


def decode_access_token(token: str) -> dict[str, Any]:
    if not settings.secret_key:
        raise AuthError('SECRET_KEY is required for authentication.')

    try:
        return jwt.decode(token, settings.secret_key, algorithms=['HS256'])
    except jwt.PyJWTError as exc:
        raise AuthError('Invalid authentication token.') from exc
