from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.security import AuthError, create_access_token
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import AuthStatusOut, LoginIn, RegisterIn, UserOut
from app.services.auth_service import AuthServiceError, login_email_user, register_email_user, upsert_google_user

settings = get_settings()
router = APIRouter()

oauth = OAuth()
oauth.register(
    name='google',
    client_id=settings.google_client_id,
    client_secret=settings.google_client_secret,
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'},
)


@router.get('/google/login')
async def google_login(request: Request) -> Response:
    if not settings.google_redirect_uri:
        raise HTTPException(
            status_code=500,
            detail={'error': 'misconfigured', 'message': 'GOOGLE_REDIRECT_URI is not configured.'},
        )

    return await oauth.google.authorize_redirect(request, settings.google_redirect_uri)


@router.get('/google/callback')
async def google_callback(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    token = await oauth.google.authorize_access_token(request)
    user_info = token.get('userinfo')

    if not user_info:
        user_info = await oauth.google.parse_id_token(request, token)

    if not user_info:
        raise HTTPException(
            status_code=400,
            detail={'error': 'oauth_failed', 'message': 'Unable to read user profile from Google.'},
        )

    google_id = user_info.get('sub')
    email = user_info.get('email')

    if not isinstance(google_id, str) or not isinstance(email, str):
        raise HTTPException(
            status_code=400,
            detail={'error': 'oauth_failed', 'message': 'Google response did not include required identity fields.'},
        )

    try:
        user = await upsert_google_user(
            db,
            google_id=google_id,
            email=email,
            name=user_info.get('name'),
            picture=user_info.get('picture'),
        )
    except SQLAlchemyError:
        return RedirectResponse(url=f"{settings.frontend_url}/?error=database_unavailable")

    try:
        access_token = create_access_token(subject=user.id, email=user.email)
    except AuthError as exc:
        raise HTTPException(
            status_code=500,
            detail={'error': 'misconfigured', 'message': str(exc)},
        ) from exc

    response = RedirectResponse(url=f"{settings.frontend_url}/chat")
    response.set_cookie(
        key='access_token',
        value=access_token,
        httponly=True,
        secure=settings.environment != 'development',
        samesite='lax',
        max_age=settings.jwt_expire_minutes * 60,
        path='/',
    )
    return response


@router.get('/me', response_model=AuthStatusOut)
async def me(current_user: User = Depends(get_current_user)) -> AuthStatusOut:
    return AuthStatusOut(
        authenticated=True,
        user=UserOut(
            id=current_user.id,
            email=current_user.email,
            name=current_user.name,
            picture=current_user.picture,
        ),
    )


@router.post('/logout', status_code=204)
async def logout() -> Response:
    response = Response(status_code=204)
    response.delete_cookie(key='access_token', path='/')
    return response


def _set_auth_cookie(response: Response, user: User) -> None:
    """Attach a JWT httpOnly cookie to an outgoing response."""
    try:
        token = create_access_token(subject=user.id, email=user.email)
    except AuthError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    response.set_cookie(
        key='access_token',
        value=token,
        httponly=True,
        secure=settings.environment != 'development',
        samesite='lax',
        max_age=settings.jwt_expire_minutes * 60,
        path='/',
    )


@router.post('/register', response_model=UserOut, status_code=201)
async def register(
    payload: RegisterIn,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    try:
        user = await register_email_user(
            db,
            email=str(payload.email),
            password=payload.password,
            name=payload.name,
        )
    except AuthServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _set_auth_cookie(response, user)
    return UserOut(id=user.id, email=user.email, name=user.name, picture=user.picture)


@router.post('/login', response_model=UserOut)
async def email_login(
    payload: LoginIn,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    try:
        user = await login_email_user(
            db,
            email=str(payload.email),
            password=payload.password,
        )
    except AuthServiceError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    _set_auth_cookie(response, user)
    return UserOut(id=user.id, email=user.email, name=user.name, picture=user.picture)
