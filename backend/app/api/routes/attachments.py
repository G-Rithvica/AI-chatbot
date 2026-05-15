from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.attachment import AttachmentListOut, AttachmentOut
from app.services.attachment_service import create_attachment, delete_attachment, list_attachments, to_attachment_out
from app.services.thread_service import get_thread

router = APIRouter()


@router.post('/upload', response_model=AttachmentOut)
async def upload_attachment(
    thread_id: str = Query(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AttachmentOut:
    thread = await get_thread(db, thread_id, current_user.id)
    if not thread:
        raise HTTPException(status_code=404, detail='Thread not found.')

    attachment = await create_attachment(db, user_id=current_user.id, thread_id=thread_id, upload=file)
    return AttachmentOut(**to_attachment_out(attachment))


@router.get('', response_model=AttachmentListOut)
async def list_thread_attachments(
    thread_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AttachmentListOut:
    thread = await get_thread(db, thread_id, current_user.id)
    if not thread:
        raise HTTPException(status_code=404, detail='Thread not found.')

    attachments = await list_attachments(db, user_id=current_user.id, thread_id=thread_id)
    return AttachmentListOut(attachments=[AttachmentOut(**to_attachment_out(item)) for item in attachments])


@router.delete('/{attachment_id}', status_code=204)
async def remove_attachment(
    attachment_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    deleted = await delete_attachment(db, user_id=current_user.id, attachment_id=attachment_id)
    if not deleted:
        raise HTTPException(status_code=404, detail='Attachment not found.')
    return Response(status_code=204)
