from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.thread import ThreadCreateIn, ThreadListOut, ThreadOut, ThreadRenameIn
from app.services.thread_service import (
    auto_name_thread,
    create_thread,
    delete_thread,
    get_thread,
    list_threads,
    rename_thread,
)

router = APIRouter()


@router.get('', response_model=ThreadListOut)
async def get_threads(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ThreadListOut:
    threads = await list_threads(db, current_user.id)
    return ThreadListOut(
        threads=[
            ThreadOut(id=t.id, name=t.name, created_at=t.created_at, updated_at=t.updated_at)
            for t in threads
        ]
    )


@router.post('', response_model=ThreadOut, status_code=201)
async def new_thread(
    payload: ThreadCreateIn = ThreadCreateIn(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ThreadOut:
    thread = await create_thread(db, current_user.id, payload.name)
    return ThreadOut(id=thread.id, name=thread.name, created_at=thread.created_at, updated_at=thread.updated_at)


@router.patch('/{thread_id}', response_model=ThreadOut)
async def update_thread(
    thread_id: str,
    payload: ThreadRenameIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ThreadOut:
    thread = await get_thread(db, thread_id, current_user.id)
    if not thread:
        raise HTTPException(status_code=404, detail='Thread not found.')
    thread = await rename_thread(db, thread, payload.name)
    return ThreadOut(id=thread.id, name=thread.name, created_at=thread.created_at, updated_at=thread.updated_at)


@router.delete('/{thread_id}', status_code=204)
async def remove_thread(
    thread_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    thread = await get_thread(db, thread_id, current_user.id)
    if not thread:
        raise HTTPException(status_code=404, detail='Thread not found.')
    await delete_thread(db, thread)
