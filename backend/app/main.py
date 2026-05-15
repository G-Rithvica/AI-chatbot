from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.db.session import init_db

settings = get_settings()

app = FastAPI(title=settings.app_name)


def _build_allowed_origins(frontend_url: str | None) -> list[str]:
    candidates = {
        'http://localhost:5173',
        'http://127.0.0.1:5173',
    }

    if frontend_url:
        normalized = frontend_url.strip().rstrip('/')
        if normalized:
            candidates.add(normalized)

            parsed = urlparse(normalized)
            if parsed.scheme in {'http', 'https'} and parsed.hostname and parsed.port:
                if parsed.hostname == 'localhost':
                    candidates.add(f'{parsed.scheme}://127.0.0.1:{parsed.port}')
                elif parsed.hostname == '127.0.0.1':
                    candidates.add(f'{parsed.scheme}://localhost:{parsed.port}')

    return sorted(candidates)

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
        allow_origins=_build_allowed_origins(settings.frontend_url),
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
    )

app.include_router(api_router, prefix='/api')

upload_dir = Path(settings.upload_dir)
if not upload_dir.is_absolute():
    upload_dir = Path(__file__).resolve().parents[1] / upload_dir
upload_dir.mkdir(parents=True, exist_ok=True)
app.mount('/uploads', StaticFiles(directory=str(upload_dir)), name='uploads')


@app.on_event('startup')
async def on_startup() -> None:
    await init_db()


@app.get('/healthz', tags=['health'])
async def healthz() -> dict[str, str]:
    return {'status': 'ok'}
