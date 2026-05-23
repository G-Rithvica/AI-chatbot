import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BASE_DIR / '.env'


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue

        key, value = line.split('=', 1)
        os.environ[key.strip()] = value.strip()


_load_env_file(ENV_FILE)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        extra='ignore',
        case_sensitive=False,
    )

    secret_key: str | None = None
    jwt_expire_minutes: int = 480
    app_name: str = 'amzur-ai-chat'
    environment: str = 'development'

    database_url: str | None = None

    litellm_proxy_url: str | None = None
    litellm_api_key: str | None = None
    llm_model: str | None = None
    litellm_embedding_model: str | None = None
    image_gen_model: str | None = None

    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str | None = None
    google_service_account_json: str | None = None

    chroma_persist_dir: str = './chroma_db'

    max_upload_mb: int = 20
    upload_dir: str = './uploads'
    accepted_upload_mime_types: list[str] = []

    frontend_url: str = 'http://localhost:5173'

    n8n_webhook_url: str | None = None
    n8n_api_key: str | None = None
    n8n_status_webhook_url: str | None = None

    db_type: str | None = None
    db_host: str | None = None
    db_port: int | None = None
    db_name: str | None = None
    db_user: str | None = None
    db_password: str | None = None
    db_schema: str | None = None
    db_url: str | None = None
    db_query_timeout_seconds: int = 15
    db_max_rows: int = 100

    @property
    def cookie_secure(self) -> bool:
        return self.environment.lower() not in {'development', 'dev', 'local'}

    @property
    def async_database_url(self) -> str | None:
        if not self.database_url:
            return None
        if self.database_url.startswith('postgresql+asyncpg://'):
            return self.database_url
        if self.database_url.startswith('postgresql://'):
            return self.database_url.replace('postgresql://', 'postgresql+asyncpg://', 1)
        return self.database_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
