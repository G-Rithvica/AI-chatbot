from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, URL, make_url

from app.core.config import BASE_DIR, ENV_FILE, get_settings
from app.database.tabular_source import materialize_tabular_source
from app.schemas.database_chat import DatabaseConnectionInput

_SUPPORTED_TYPES = {
    'mysql': 'mysql',
    'mysql+pymysql': 'mysql',
    'postgres': 'postgresql',
    'postgresql': 'postgresql',
    'postgresql+asyncpg': 'postgresql',
    'postgresql+psycopg2': 'postgresql',
    'sqlite': 'sqlite',
    'sqlite+aiosqlite': 'sqlite',
    'supabase': 'supabase',
}


class DatabaseConnectionError(ValueError):
    pass


@dataclass(frozen=True)
class ResolvedDatabaseConfig:
    db_type: str
    url: str
    database: str
    schema: str | None
    timeout_seconds: int
    max_rows: int
    ssl_required: bool

    @property
    def dialect_name(self) -> str:
        if self.db_type == 'supabase':
            return 'postgresql'
        return self.db_type


def _normalize_db_type(raw: str | None) -> str:
    normalized = (raw or '').strip().lower()
    if normalized not in _SUPPORTED_TYPES:
        raise DatabaseConnectionError('Unsupported database type. Use mysql, postgresql, sqlite, or supabase.')
    return _SUPPORTED_TYPES[normalized]


def _absolute_sqlite_path(candidate: str) -> Path:
    path = Path(candidate)
    if not path.is_absolute():
        path = BASE_DIR / path
    return path


def _read_dotenv_value(key: str) -> str | None:
    if not ENV_FILE.exists():
        return None

    for raw_line in ENV_FILE.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        current_key, value = line.split('=', 1)
        if current_key.strip().upper() == key.upper():
            stripped = value.strip()
            return stripped or None
    return None


def _build_url(config: DatabaseConnectionInput | None) -> tuple[str, str, str | None, bool]:
    settings = get_settings()
    payload = config or DatabaseConnectionInput()
    dotenv_db_url = _read_dotenv_value('DB_URL')
    dotenv_database_url = _read_dotenv_value('DATABASE_URL')
    dotenv_db_type = _read_dotenv_value('DB_TYPE')
    dotenv_db_host = _read_dotenv_value('DB_HOST')
    dotenv_db_name = _read_dotenv_value('DB_NAME')
    dotenv_db_user = _read_dotenv_value('DB_USER')
    dotenv_db_password = _read_dotenv_value('DB_PASSWORD')
    dotenv_db_schema = _read_dotenv_value('DB_SCHEMA')

    effective_db_url = dotenv_db_url or settings.db_url
    effective_database_url = dotenv_database_url or settings.database_url
    effective_db_type = dotenv_db_type or settings.db_type
    effective_db_host = dotenv_db_host or settings.db_host
    effective_db_name = dotenv_db_name or settings.db_name
    effective_db_user = dotenv_db_user or settings.db_user
    effective_db_password = dotenv_db_password if dotenv_db_password is not None else settings.db_password
    effective_db_schema = dotenv_db_schema or settings.db_schema

    explicit_db_type = (payload.db_type or '').strip()
    if explicit_db_type and _normalize_db_type(explicit_db_type) == 'sqlite':
        sqlite_path = payload.sqlite_path or payload.database or effective_db_name
        if not sqlite_path:
            raise DatabaseConnectionError('SQLite requires sqlite_path or DB_NAME in the environment.')
        path = _absolute_sqlite_path(sqlite_path)
        return f'sqlite:///{path.as_posix()}', str(path), None, False

    has_manual_components = any(
        value not in {None, ''}
        for value in (
            payload.db_type,
            payload.host,
            payload.port,
            payload.database,
            payload.username,
            payload.password,
            payload.schema_name,
            payload.sqlite_path,
        )
    )

    raw_url = (
        payload.url
        or effective_db_url
        or (effective_database_url if not has_manual_components else '')
        or ''
    ).strip()
    if raw_url:
        parsed_url = urlparse(raw_url)
        if parsed_url.scheme in {'http', 'https'}:
            sqlite_path, database_name = materialize_tabular_source(raw_url)
            return f'sqlite:///{sqlite_path.as_posix()}', database_name, None, False

        parsed = make_url(raw_url)

        # Normalize async URLs to sync drivers for the read-only query engine.
        if parsed.drivername == 'postgresql+asyncpg':
            parsed = parsed.set(drivername='postgresql+psycopg2')
            raw_url = parsed.render_as_string(hide_password=False)
        elif parsed.drivername == 'sqlite+aiosqlite':
            parsed = parsed.set(drivername='sqlite')
            raw_url = parsed.render_as_string(hide_password=False)

        backend = parsed.get_backend_name()
        db_type = _normalize_db_type('supabase' if 'supabase' in raw_url else backend)
        database = parsed.database or effective_db_name or ''
        default_schema = 'public' if db_type in {'postgresql', 'supabase'} else None
        schema = payload.schema_name or effective_db_schema or default_schema
        ssl_required = bool(payload.ssl_required) if payload.ssl_required is not None else db_type == 'supabase'
        return raw_url, database, schema, ssl_required

    db_type = _normalize_db_type(payload.db_type or effective_db_type)
    if db_type == 'sqlite':
        sqlite_path = payload.sqlite_path or payload.database or effective_db_name
        if not sqlite_path:
            raise DatabaseConnectionError('SQLite requires sqlite_path or DB_NAME in the environment.')
        path = _absolute_sqlite_path(sqlite_path)
        return f'sqlite:///{path.as_posix()}', str(path), None, False

    host = payload.host or effective_db_host
    port = payload.port or settings.db_port
    database = payload.database or effective_db_name
    username = payload.username or effective_db_user
    password = payload.password or effective_db_password
    schema = payload.schema_name or effective_db_schema or ('public' if db_type in {'postgresql', 'supabase'} else None)
    ssl_required = bool(payload.ssl_required) if payload.ssl_required is not None else db_type == 'supabase'

    if not host or not database or not username:
        raise DatabaseConnectionError('Database host, database name, and username are required.')
    if password is None:
        raise DatabaseConnectionError('Database password is required.')

    if db_type in {'postgresql', 'supabase'}:
        drivername = 'postgresql+psycopg2'
        query = {'sslmode': 'require'} if ssl_required else None
    else:
        drivername = 'mysql+pymysql'
        query = None

    url = URL.create(
        drivername=drivername,
        username=username,
        password=password,
        host=host,
        port=port,
        database=database,
        query=query,
    )
    return url.render_as_string(hide_password=False), database, schema, ssl_required


def resolve_database_config(config: DatabaseConnectionInput | None) -> ResolvedDatabaseConfig:
    settings = get_settings()
    url, database, schema, ssl_required = _build_url(config)
    payload = config or DatabaseConnectionInput()
    parsed_url = urlparse((payload.url or settings.db_url or settings.database_url or '').strip())
    if parsed_url.scheme in {'http', 'https'}:
        db_type = 'sqlite'
    else:
        inferred_backend = make_url(url).get_backend_name()
        db_type = _normalize_db_type(payload.db_type or inferred_backend or settings.db_type)
    return ResolvedDatabaseConfig(
        db_type=db_type,
        url=url,
        database=database,
        schema=schema,
        timeout_seconds=max(1, settings.db_query_timeout_seconds),
        max_rows=max(1, settings.db_max_rows),
        ssl_required=ssl_required,
    )


def redacted_database_url(url: str) -> str:
    try:
        parsed = make_url(url)
    except Exception:  # noqa: BLE001
        return url
    return parsed.render_as_string(hide_password=True)


def create_database_engine(config: ResolvedDatabaseConfig) -> Engine:
    connect_args: dict[str, object] = {}
    if config.db_type == 'sqlite':
        connect_args['check_same_thread'] = False
    return create_engine(config.url, future=True, pool_pre_ping=True, connect_args=connect_args)
