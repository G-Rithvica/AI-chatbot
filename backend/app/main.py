from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.db.session import init_db

settings = get_settings()

app = FastAPI(title=settings.app_name)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key or 'dev-session-secret',
    https_only=False,
    same_site='lax',
    max_age=300,
)

if settings.frontend_url:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_url],
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
    )

app.include_router(api_router, prefix='/api')


@app.on_event('startup')
async def on_startup() -> None:
    await init_db()


@app.get('/healthz', tags=['health'])
async def healthz() -> dict[str, str]:
    return {'status': 'ok'}
