from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models.user import User

ALLOWED_DOMAIN = 'amzur.com'


class AuthServiceError(Exception):
    """Raised for expected auth failures (bad credentials, domain, etc.)."""


async def register_email_user(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    name: str | None = None,
) -> User:
    domain = email.split('@', 1)[-1].lower()
    if domain != ALLOWED_DOMAIN:
        raise AuthServiceError(f'Only @{ALLOWED_DOMAIN} email addresses are allowed.')

    result = await db.execute(select(User).where(User.email == email))
    existing = result.scalar_one_or_none()

    if existing is not None:
        # Account exists via Google — link a password so both methods work.
        existing.hashed_password = hash_password(password)
        if name:
            existing.name = name
        await db.commit()
        await db.refresh(existing)
        return existing

    user = User(
        email=email,
        name=name or email.split('@')[0],
        hashed_password=hash_password(password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def login_email_user(
    db: AsyncSession,
    *,
    email: str,
    password: str,
) -> User:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None or not user.hashed_password:
        raise AuthServiceError('Invalid email or password.')

    if not verify_password(password, user.hashed_password):
        raise AuthServiceError('Invalid email or password.')

    return user


async def upsert_google_user(
    db: AsyncSession,
    *,
    google_id: str,
    email: str,
    name: str | None,
    picture: str | None,
) -> User:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            email=email,
            google_id=google_id,
            name=name,
            picture=picture,
        )
        db.add(user)
    else:
        if not user.google_id:
            user.google_id = google_id
        user.name = name
        user.picture = picture

    await db.commit()
    await db.refresh(user)
    return user


async def get_user_by_id(db: AsyncSession, user_id: str) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()
