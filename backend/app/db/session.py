from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.models.attachment import Attachment
from app.models.generated_image import GeneratedImage
from app.models.base import Base
from app.models.message import Message
from app.models.n8n_webhook_event import N8nWebhookEvent
from app.models.thread import Thread
from app.models.user import User

settings = get_settings()

if not settings.async_database_url:
    raise RuntimeError('DATABASE_URL is required to initialize the database engine.')

engine = create_async_engine(
    settings.async_database_url,
    echo=False,
    pool_pre_ping=True,
    pool_recycle=300,
    pool_use_lifo=True,
)
AsyncSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:  # noqa: BLE001
            # Reset broken transactions before returning session to the pool.
            await session.rollback()
            raise


async def init_db() -> None:
    """Verify connectivity and reconcile minimal schema drift at startup.

    This project currently runs without Alembic revisions, so startup ensures
    required tables exist and backfills the thread-aware messages schema for
    databases created before thread support was added.
    """
    import logging
    logger = logging.getLogger(__name__)
    try:
        async with engine.connect() as connection:
            await connection.execute(text('SELECT 1'))
            await connection.run_sync(Base.metadata.create_all)
            await _ensure_messages_thread_schema(connection)
            await connection.commit()
            logger.info('Database connection verified and schema reconciled.')
    except Exception as exc:  # noqa: BLE001
        logger.warning('Database unreachable at startup: %s', exc)


async def _ensure_messages_thread_schema(connection) -> None:
    column_exists = await connection.scalar(
        text(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'messages'
              AND column_name = 'thread_id'
            """
        )
    )

    if not column_exists:
        await connection.execute(text('ALTER TABLE messages ADD COLUMN thread_id VARCHAR(36)'))
        await connection.execute(
            text(
                'ALTER TABLE messages ADD CONSTRAINT fk_messages_thread_id '
                'FOREIGN KEY (thread_id) REFERENCES threads (id) ON DELETE CASCADE'
            )
        )

    await connection.execute(text('CREATE INDEX IF NOT EXISTS ix_messages_thread_id ON messages (thread_id)'))
