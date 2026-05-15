from fastapi import APIRouter, HTTPException

from .models import ImageGenerationRequest, ImageGenerationResult
from .service import (
    ImageGenerationNotConfiguredError,
    ImageGenerationProviderError,
    ImageGenerationValidationError,
    generate_image,
)

router = APIRouter(prefix='/project6/image-generation', tags=['project6'])


@router.post('/generate', response_model=ImageGenerationResult)
async def generate(payload: ImageGenerationRequest) -> ImageGenerationResult:
    try:
        return await generate_image(payload)
    except ImageGenerationValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ImageGenerationNotConfiguredError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except ImageGenerationProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
