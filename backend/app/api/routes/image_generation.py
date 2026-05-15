from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.image_generation import ImageGenerationRequest, ImageGenerationResult
from app.services.chat_service import save_message
from app.services.image_generation_service import (
    count_generated_images,
    ImageGenerationNotConfiguredError,
    ImageGenerationProviderError,
    ImageGenerationValidationError,
    generate_image,
    save_generated_image,
)
from app.services.thread_service import auto_name_thread, get_thread

router = APIRouter()


@router.get('/count')
async def count_for_thread(
    thread_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, int | str]:
    thread = await get_thread(db, thread_id, current_user.id)
    if not thread:
        raise HTTPException(status_code=404, detail='Thread not found.')

    count = await count_generated_images(db, user_id=current_user.id, thread_id=thread_id)
    return {'thread_id': thread_id, 'generated_images_count': count}


@router.post('/generate', response_model=ImageGenerationResult)
async def generate(
    payload: ImageGenerationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ImageGenerationResult:
    try:
        if payload.thread_id:
            thread = await get_thread(db, payload.thread_id, current_user.id)
            if not thread:
                raise HTTPException(status_code=404, detail='Thread not found.')

            # Persist as a normal user chat turn so prompt remains visible on RHS history.
            await save_message(db, current_user.id, 'user', payload.prompt, payload.thread_id)
            if thread.name == 'New Chat':
                await auto_name_thread(db, thread, payload.prompt)

        result = await generate_image(payload)
        if payload.thread_id:
            await save_generated_image(
                db,
                user=current_user,
                thread_id=payload.thread_id,
                prompt=payload.prompt,
                result=result,
            )
        return result
    except ImageGenerationValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ImageGenerationNotConfiguredError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except ImageGenerationProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
