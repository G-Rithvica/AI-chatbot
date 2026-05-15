import base64
import struct
from pathlib import Path

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import BASE_DIR, get_settings
from app.models.attachment import Attachment
from app.models.generated_image import GeneratedImage


class ImageRuleRequest(BaseModel):
    image_id: str = Field(min_length=1)
    rule_names: list[str] = Field(default_factory=list)


class RuleOutcome(BaseModel):
    rule_name: str
    passed: bool
    detail: str


class ImageRuleReport(BaseModel):
    image_id: str
    outcomes: list[RuleOutcome]


def _resolve_upload_root() -> Path:
    settings = get_settings()
    upload_dir = Path(settings.upload_dir)
    if not upload_dir.is_absolute():
        upload_dir = BASE_DIR / upload_dir
    return upload_dir


def _png_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) >= 24 and data.startswith(b'\x89PNG\r\n\x1a\n'):
        width, height = struct.unpack('>II', data[16:24])
        return int(width), int(height)
    return None


def _gif_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) >= 10 and data[:6] in {b'GIF87a', b'GIF89a'}:
        width, height = struct.unpack('<HH', data[6:10])
        return int(width), int(height)
    return None


def _jpeg_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) < 4 or data[:2] != b'\xff\xd8':
        return None
    offset = 2
    while offset + 9 < len(data):
        if data[offset] != 0xFF:
            offset += 1
            continue
        marker = data[offset + 1]
        offset += 2
        if marker in {0xD8, 0xD9}:
            continue
        if offset + 2 > len(data):
            break
        segment_length = struct.unpack('>H', data[offset:offset + 2])[0]
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
            if offset + 7 <= len(data):
                height, width = struct.unpack('>HH', data[offset + 3:offset + 7])
                return int(width), int(height)
            break
        offset += max(segment_length, 2)
    return None


def _image_dimensions(data: bytes) -> tuple[int, int] | None:
    return _png_dimensions(data) or _gif_dimensions(data) or _jpeg_dimensions(data)


async def _resolve_image_source(
    db: AsyncSession,
    *,
    image_id: str,
    user_id: str | None,
) -> tuple[bytes, str, int, str]:
    attachment_stmt = select(Attachment).where(Attachment.id == image_id)
    generated_stmt = select(GeneratedImage).where(GeneratedImage.id == image_id)
    if user_id:
        attachment_stmt = attachment_stmt.where(Attachment.user_id == user_id)
        generated_stmt = generated_stmt.where(GeneratedImage.user_id == user_id)

    attachment = (await db.execute(attachment_stmt)).scalar_one_or_none()
    if attachment is not None:
        path = _resolve_upload_root() / attachment.storage_path
        data = path.read_bytes()
        return data, attachment.mime_type, int(attachment.size_bytes), f'attachment:{attachment.file_name}'

    generated = (await db.execute(generated_stmt)).scalar_one_or_none()
    if generated is not None:
        data = base64.b64decode(generated.image_base64)
        return data, generated.mime_type, len(data), 'generated-image'

    raise ValueError('Image source not found for provided image_id.')


def _evaluate_rule(rule: str, *, data: bytes, mime_type: str, size_bytes: int) -> RuleOutcome:
    dimensions = _image_dimensions(data)
    rule_key = rule.strip().lower()

    if rule_key == 'is_png':
        passed = mime_type == 'image/png' or data.startswith(b'\x89PNG')
        return RuleOutcome(rule_name=rule, passed=passed, detail='Image must be PNG format.')
    if rule_key == 'max_5mb':
        passed = size_bytes <= 5 * 1024 * 1024
        return RuleOutcome(rule_name=rule, passed=passed, detail=f'Image size is {size_bytes} bytes.')
    if rule_key == 'min_1024px':
        if not dimensions:
            return RuleOutcome(rule_name=rule, passed=False, detail='Image dimensions could not be determined.')
        passed = dimensions[0] >= 1024 and dimensions[1] >= 1024
        return RuleOutcome(rule_name=rule, passed=passed, detail=f'Image dimensions are {dimensions[0]}x{dimensions[1]}.')
    if rule_key == 'square':
        if not dimensions:
            return RuleOutcome(rule_name=rule, passed=False, detail='Image dimensions could not be determined.')
        passed = dimensions[0] == dimensions[1]
        return RuleOutcome(rule_name=rule, passed=passed, detail=f'Image dimensions are {dimensions[0]}x{dimensions[1]}.')
    if rule_key == 'landscape':
        if not dimensions:
            return RuleOutcome(rule_name=rule, passed=False, detail='Image dimensions could not be determined.')
        passed = dimensions[0] > dimensions[1]
        return RuleOutcome(rule_name=rule, passed=passed, detail=f'Image dimensions are {dimensions[0]}x{dimensions[1]}.')
    if rule_key == 'portrait':
        if not dimensions:
            return RuleOutcome(rule_name=rule, passed=False, detail='Image dimensions could not be determined.')
        passed = dimensions[1] > dimensions[0]
        return RuleOutcome(rule_name=rule, passed=passed, detail=f'Image dimensions are {dimensions[0]}x{dimensions[1]}.')
    return RuleOutcome(rule_name=rule, passed=False, detail='Unknown rule. Supported: is_png, max_5mb, min_1024px, square, landscape, portrait.')


async def run_rules(
    request: ImageRuleRequest,
    *,
    db: AsyncSession,
    user_id: str | None = None,
) -> ImageRuleReport:
    data, mime_type, size_bytes, _source = await _resolve_image_source(db, image_id=request.image_id, user_id=user_id)
    outcomes = [_evaluate_rule(rule, data=data, mime_type=mime_type, size_bytes=size_bytes) for rule in request.rule_names]
    return ImageRuleReport(image_id=request.image_id, outcomes=outcomes)
