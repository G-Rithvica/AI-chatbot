import base64
import os
from dataclasses import dataclass
from typing import Any

import httpx
from openai import AsyncOpenAI

from app.core.config import get_settings
from .models import ImageGenerationRequest, ImageGenerationResult


class ImageGenerationNotConfiguredError(RuntimeError):
    pass


class ImageGenerationValidationError(ValueError):
    pass


class ImageGenerationProviderError(RuntimeError):
    pass


_ALLOWED_SIZES = {
    '1024x1024',
    '1024x1536',
    '1536x1024',
    '512x512',
    '256x256',
}

_ALLOWED_STYLES = {'vivid', 'natural'}
_ALLOWED_RESPONSE_FORMATS = {'b64_json', 'url'}


@dataclass(frozen=True)
class ImageGenerationSettings:
    api_key: str | None
    model: str
    base_url: str | None
    timeout_seconds: float


def _load_settings() -> ImageGenerationSettings:
    settings = get_settings()
    return ImageGenerationSettings(
        api_key=(
            os.getenv('PROJECT6_IMAGE_API_KEY')
            or os.getenv('LITELLM_API_KEY')
            or os.getenv('OPENAI_API_KEY')
        ),
        model=os.getenv('PROJECT6_IMAGE_MODEL') or settings.image_gen_model or 'gpt-image-1',
        base_url=os.getenv('PROJECT6_IMAGE_BASE_URL') or settings.litellm_proxy_url,
        timeout_seconds=float(os.getenv('PROJECT6_IMAGE_TIMEOUT_SECONDS', '60')),
    )


def _build_client(settings: ImageGenerationSettings) -> AsyncOpenAI:
    if not settings.api_key:
        raise ImageGenerationNotConfiguredError(
            'PROJECT6_IMAGE_API_KEY (or LITELLM_API_KEY / OPENAI_API_KEY) is required for Project 6 image generation.'
        )

    kwargs: dict[str, Any] = {
        'api_key': settings.api_key,
        'timeout': settings.timeout_seconds,
    }
    if settings.base_url:
        kwargs['base_url'] = settings.base_url
    return AsyncOpenAI(**kwargs)


def _validate_request(request: ImageGenerationRequest) -> None:
    if request.size not in _ALLOWED_SIZES:
        raise ImageGenerationValidationError(
            f'Unsupported image size: {request.size}. Allowed values: {", ".join(sorted(_ALLOWED_SIZES))}'
        )

    if request.style and request.style not in _ALLOWED_STYLES:
        raise ImageGenerationValidationError(
            f'Unsupported style: {request.style}. Allowed values: {", ".join(sorted(_ALLOWED_STYLES))}'
        )

    if request.response_format not in _ALLOWED_RESPONSE_FORMATS:
        raise ImageGenerationValidationError(
            'Unsupported response format: '
            f'{request.response_format}. Allowed values: {", ".join(sorted(_ALLOWED_RESPONSE_FORMATS))}'
        )


def _extract_field(obj: Any, key: str) -> Any:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


async def _download_image_as_b64(url: str, timeout_seconds: float) -> str:
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        response = await client.get(url)
        response.raise_for_status()
        return base64.b64encode(response.content).decode('ascii')


async def generate_image(request: ImageGenerationRequest) -> ImageGenerationResult:
    """Generate an image using OpenAI-compatible image generation APIs.

    This service is intentionally isolated under next_projects and not wired to production routes.
    """
    _validate_request(request)
    settings = _load_settings()
    client = _build_client(settings)

    payload: dict[str, Any] = {
        'model': settings.model,
        'prompt': request.prompt,
        'size': request.size,
        'response_format': request.response_format,
    }
    if request.style:
        payload['style'] = request.style

    try:
        response = await client.images.generate(**payload)
    except Exception as exc:  # noqa: BLE001
        raise ImageGenerationProviderError(f'Image provider request failed: {exc}') from exc

    data_items = _extract_field(response, 'data') or []
    if not data_items:
        raise ImageGenerationProviderError('Image provider returned no image data.')

    first = data_items[0]
    b64 = _extract_field(first, 'b64_json')
    revised_prompt = _extract_field(first, 'revised_prompt')

    if not b64:
        # Some OpenAI-compatible providers return URL instead of b64.
        image_url = _extract_field(first, 'url')
        if not image_url:
            raise ImageGenerationProviderError('Image provider returned neither b64_json nor url.')
        try:
            b64 = await _download_image_as_b64(image_url, settings.timeout_seconds)
        except Exception as exc:  # noqa: BLE001
            raise ImageGenerationProviderError(f'Failed to download provider image URL: {exc}') from exc

    return ImageGenerationResult(
        mime_type='image/png',
        image_base64=b64,
        revised_prompt=revised_prompt,
    )
