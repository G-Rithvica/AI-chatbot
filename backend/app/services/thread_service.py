from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.thread import Thread


async def list_threads(db: AsyncSession, user_id: str) -> list[Thread]:
    stmt = (
        select(Thread)
        .where(Thread.user_id == user_id)
        .order_by(Thread.updated_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def create_thread(db: AsyncSession, user_id: str, name: str = 'New Chat') -> Thread:
    thread = Thread(user_id=user_id, name=name)
    db.add(thread)
    await db.commit()
    await db.refresh(thread)
    return thread


async def get_thread(db: AsyncSession, thread_id: str, user_id: str) -> Thread | None:
    result = await db.execute(
        select(Thread).where(Thread.id == thread_id, Thread.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def rename_thread(db: AsyncSession, thread: Thread, name: str) -> Thread:
    thread.name = name
    thread.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(thread)
    return thread


async def auto_name_thread(db: AsyncSession, thread: Thread, first_message: str) -> None:
    """Set thread name from first user message (first 50 chars, word-boundary)."""
    words = first_message.strip().split()
    name = ' '.join(words[:8])
    if len(name) > 50:
        name = name[:47] + '...'
    thread.name = name or 'New Chat'
    thread.updated_at = datetime.now(timezone.utc)
    await db.commit()


async def delete_thread(db: AsyncSession, thread: Thread) -> None:
    await db.delete(thread)
    await db.commit()
