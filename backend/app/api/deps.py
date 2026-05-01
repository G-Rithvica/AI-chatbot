from fastapi import Cookie, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import AuthError, decode_access_token
from app.db.session import get_db
from app.models.user import User
from app.services.auth_service import get_user_by_id


async def get_current_user(
    db: AsyncSession = Depends(get_db),
    access_token: str | None = Cookie(default=None),
) -> User:
    if not access_token:
        raise HTTPException(
            status_code=401,
            detail={'error': 'unauthorized', 'message': 'Authentication required.'},
        )

    try:
        payload = decode_access_token(access_token)
    except AuthError as exc:
        raise HTTPException(
            status_code=401,
            detail={'error': 'invalid_token', 'message': str(exc)},
        ) from exc

    user_id = payload.get('sub')
    if not isinstance(user_id, str):
        raise HTTPException(
            status_code=401,
            detail={'error': 'invalid_token', 'message': 'Token subject is invalid.'},
        )

    user = await get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=401,
            detail={'error': 'user_not_found', 'message': 'User no longer exists.'},
        )

    return user
