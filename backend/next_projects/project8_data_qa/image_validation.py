import base64
import json
import re
import struct
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.llm import get_async_openai_client
from app.core.config import BASE_DIR, get_settings
from app.models.attachment import Attachment
from app.models.generated_image import GeneratedImage
from .image_validation_rules import ValidationRuleDefinition, load_default_rules


class ImageValidationRuleInput(BaseModel):
    rule_id: str = Field(min_length=1)
    description: str = ''
    field_path: str = Field(min_length=1)
    operator: str = Field(min_length=1)
    expected: Any = None
    required: bool = True


class ImageValidationRequest(BaseModel):
    image_id: str = Field(min_length=1)
    thread_id: str | None = None
    note: str | None = None
    include_default_rules: bool = True
    rules: list[ImageValidationRuleInput] = Field(default_factory=list)


class ImageValidationBatchRequest(BaseModel):
    image_ids: list[str] = Field(min_length=1)
    include_default_rules: bool = True
    rules: list[ImageValidationRuleInput] = Field(default_factory=list)


class ExtractedImageData(BaseModel):
    metadata: dict[str, Any]
    text: str
    labels: list[str]
    fields: dict[str, str]


class ImageValidationRuleResult(BaseModel):
    rule_id: str
    description: str
    operator: str
    expected: Any = None
    extracted: Any = None
    passed: bool
    required: bool = True
    message: str


class ImageValidationResult(BaseModel):
    image_id: str
    source_name: str
    source_type: str
    source_thread_id: str | None = None
    extracted_data: ExtractedImageData
    passed: bool
    failed_rules: list[ImageValidationRuleResult]
    rule_results: list[ImageValidationRuleResult]
    summary: str
    chat_summary: str


class ImageValidationBatchItem(BaseModel):
    image_id: str
    success: bool
    result: ImageValidationResult | None = None
    error: str | None = None


class ImageValidationBatchResult(BaseModel):
    total_images: int
    processed_images: int
    passed_images: int
    failed_images: int
    results: list[ImageValidationBatchItem]
    summary: str


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


def _detect_image_format(data: bytes, mime_type: str) -> str:
    if mime_type:
        return mime_type.split('/')[-1].upper()
    if data.startswith(b'\x89PNG'):
        return 'PNG'
    if data.startswith(b'\xff\xd8'):
        return 'JPEG'
    if data.startswith(b'GIF87a') or data.startswith(b'GIF89a'):
        return 'GIF'
    return 'UNKNOWN'


async def _resolve_image_source(
    db: AsyncSession,
    *,
    image_id: str,
    user_id: str,
) -> tuple[bytes, str, int, str, str | None, str]:
    attachment_stmt = select(Attachment).where(Attachment.id == image_id, Attachment.user_id == user_id)
    generated_stmt = select(GeneratedImage).where(GeneratedImage.id == image_id, GeneratedImage.user_id == user_id)

    attachment = (await db.execute(attachment_stmt)).scalar_one_or_none()
    if attachment is not None:
        path = _resolve_upload_root() / attachment.storage_path
        data = path.read_bytes()
        return data, attachment.mime_type, int(attachment.size_bytes), attachment.file_name, attachment.thread_id, 'attachment'

    generated = (await db.execute(generated_stmt)).scalar_one_or_none()
    if generated is not None:
        data = base64.b64decode(generated.image_base64)
        return data, generated.mime_type, len(data), 'generated-image', generated.thread_id, 'generated'

    raise ValueError('Image source not found for provided image_id.')


def _json_from_response(content: str) -> dict[str, Any]:
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    match = re.search(r'\{[\s\S]*\}', content)
    if not match:
        return {}
    try:
        parsed = json.loads(match.group(0))
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        return {}
    return {}


async def _extract_with_llm(*, image_bytes: bytes, mime_type: str) -> tuple[str, list[str], dict[str, str]]:
    settings = get_settings()
    if not settings.llm_model or not settings.litellm_api_key:
        return '', [], {}

    encoded = base64.b64encode(image_bytes).decode('ascii')
    data_url = f'data:{mime_type or "image/png"};base64,{encoded}'

    client = get_async_openai_client()
    response = await client.chat.completions.create(
        model=settings.llm_model,
        temperature=0,
        messages=[
            {
                'role': 'system',
                'content': (
                    'Extract structured information from the provided image. '
                    'Return strict JSON only with keys: text (string), labels (string array), fields (object map of key->value). '
                    'If a value is not present, return empty string/array/object.'
                ),
            },
            {
                'role': 'user',
                'content': [
                    {'type': 'text', 'text': 'Extract readable text, labels, and field/value pairs from this image.'},
                    {'type': 'image_url', 'image_url': {'url': data_url}},
                ],
            },
        ],
    )
    content = (response.choices[0].message.content or '').strip()
    payload = _json_from_response(content)

    text = str(payload.get('text', '') or '').strip()
    labels_raw = payload.get('labels', [])
    labels = [str(item).strip() for item in labels_raw] if isinstance(labels_raw, list) else []

    fields_raw = payload.get('fields', {})
    fields: dict[str, str] = {}
    if isinstance(fields_raw, dict):
        for key, value in fields_raw.items():
            normalized_key = str(key).strip()
            if not normalized_key:
                continue
            fields[normalized_key] = '' if value is None else str(value).strip()

    return text, labels, fields


def _value_at_path(payload: dict[str, Any], field_path: str) -> Any:
    current: Any = payload
    for part in field_path.split('.'):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def _evaluate_operator(*, operator: str, expected: Any, extracted: Any) -> bool:
    key = operator.lower().strip()
    if key == 'exists':
        return extracted is not None
    if key == 'not_empty':
        if extracted is None:
            return False
        if isinstance(extracted, str):
            return bool(extracted.strip())
        if isinstance(extracted, (list, dict)):
            return len(extracted) > 0
        return True
    if key == 'eq':
        return extracted == expected
    if key == 'neq':
        return extracted != expected
    if key == 'contains':
        return str(expected).lower() in str(extracted or '').lower()
    if key == 'not_contains':
        return str(expected).lower() not in str(extracted or '').lower()
    if key == 'in':
        if not isinstance(expected, list):
            return False
        normalized = [str(item).lower() for item in expected]
        return str(extracted).lower() in normalized
    if key == 'regex':
        if expected is None:
            return False
        return re.search(str(expected), str(extracted or '')) is not None
    if key == 'gte':
        try:
            return float(extracted) >= float(expected)
        except (TypeError, ValueError):
            return False
    if key == 'lte':
        try:
            return float(extracted) <= float(expected)
        except (TypeError, ValueError):
            return False
    return False


def _rule_input_to_definition(item: ImageValidationRuleInput) -> ValidationRuleDefinition:
    return ValidationRuleDefinition(
        rule_id=item.rule_id,
        description=item.description,
        field_path=item.field_path,
        operator=item.operator,
        expected=item.expected,
        required=item.required,
    )


def _chat_summary(*, extracted: ExtractedImageData, passed: bool, rule_results: list[ImageValidationRuleResult]) -> str:
    status = 'PASS' if passed else 'FAIL'

    labels_text = ', '.join(extracted.labels) if extracted.labels else 'None'
    if extracted.fields:
        fields_text = '\n'.join([f'- {key}: {value}' for key, value in extracted.fields.items()])
    else:
        fields_text = '- None'

    rule_lines = []
    for item in rule_results:
        rule_status = 'PASS' if item.passed else 'FAIL'
        rule_lines.append(
            f'- [{rule_status}] {item.rule_id}: expected {item.expected!r}, extracted {item.extracted!r}. {item.message}'
        )

    return (
        f'Image Validation Result: {status}\n\n'
        'Extracted Data:\n'
        f"- Format: {extracted.metadata.get('format')}\n"
        f"- MIME Type: {extracted.metadata.get('mime_type')}\n"
        f"- Size (bytes): {extracted.metadata.get('size_bytes')}\n"
        f"- Dimensions: {extracted.metadata.get('width')}x{extracted.metadata.get('height')}\n"
        f"- Text: {extracted.text or 'None'}\n"
        f"- Labels: {labels_text}\n"
        'Structured Fields:\n'
        f'{fields_text}\n\n'
        'Rule-by-Rule Summary:\n'
        + '\n'.join(rule_lines)
    )


async def validate_image(
    request: ImageValidationRequest,
    *,
    db: AsyncSession,
    user_id: str,
) -> ImageValidationResult:
    image_bytes, mime_type, size_bytes, source_name, source_thread_id, source_type = await _resolve_image_source(
        db,
        image_id=request.image_id,
        user_id=user_id,
    )
    dimensions = _image_dimensions(image_bytes)
    width = dimensions[0] if dimensions else None
    height = dimensions[1] if dimensions else None

    text = ''
    labels: list[str] = []
    fields: dict[str, str] = {}
    try:
        text, labels, fields = await _extract_with_llm(image_bytes=image_bytes, mime_type=mime_type)
    except Exception:
        # Fallback to metadata-only extraction when vision model is unavailable.
        text, labels, fields = '', [], {}

    extracted = ExtractedImageData(
        metadata={
            'format': _detect_image_format(image_bytes, mime_type),
            'mime_type': mime_type,
            'size_bytes': size_bytes,
            'width': width,
            'height': height,
            'source_type': source_type,
        },
        text=text,
        labels=labels,
        fields=fields,
    )

    rules: list[ValidationRuleDefinition] = []
    if request.include_default_rules:
        rules.extend(load_default_rules())
    rules.extend([_rule_input_to_definition(item) for item in request.rules])

    payload = {
        'metadata': extracted.metadata,
        'extracted': {
            'text': extracted.text,
            'labels': extracted.labels,
            'fields': extracted.fields,
        },
    }

    outcomes: list[ImageValidationRuleResult] = []
    for rule in rules:
        value = _value_at_path(payload, rule.field_path)
        passed = _evaluate_operator(operator=rule.operator, expected=rule.expected, extracted=value)
        outcomes.append(
            ImageValidationRuleResult(
                rule_id=rule.rule_id,
                description=rule.description,
                operator=rule.operator,
                expected=rule.expected,
                extracted=value,
                passed=passed,
                required=rule.required,
                message=(
                    'Rule satisfied.' if passed else f'Rule failed for field "{rule.field_path}".'
                ),
            )
        )

    failed_required = [item for item in outcomes if item.required and not item.passed]
    validation_passed = len(failed_required) == 0
    summary = 'Image passed validation rules.' if validation_passed else 'Image failed one or more required rules.'
    chat_summary = _chat_summary(extracted=extracted, passed=validation_passed, rule_results=outcomes)

    return ImageValidationResult(
        image_id=request.image_id,
        source_name=source_name,
        source_type=source_type,
        source_thread_id=source_thread_id,
        extracted_data=extracted,
        passed=validation_passed,
        failed_rules=failed_required,
        rule_results=outcomes,
        summary=summary,
        chat_summary=chat_summary,
    )


async def validate_images_batch(
    request: ImageValidationBatchRequest,
    *,
    db: AsyncSession,
    user_id: str,
) -> ImageValidationBatchResult:
    results: list[ImageValidationBatchItem] = []
    processed_images = 0
    passed_images = 0
    failed_images = 0

    for image_id in request.image_ids:
        image_request = ImageValidationRequest(
            image_id=image_id,
            include_default_rules=request.include_default_rules,
            rules=request.rules,
        )
        try:
            result = await validate_image(image_request, db=db, user_id=user_id)
            processed_images += 1
            if result.passed:
                passed_images += 1
            else:
                failed_images += 1
            results.append(ImageValidationBatchItem(image_id=image_id, success=True, result=result))
        except Exception as exc:  # noqa: BLE001
            failed_images += 1
            results.append(ImageValidationBatchItem(image_id=image_id, success=False, error=str(exc)))

    summary = (
        f'Processed {processed_images}/{len(request.image_ids)} image(s). '
        f'Passed: {passed_images}, Failed: {failed_images}.'
    )

    return ImageValidationBatchResult(
        total_images=len(request.image_ids),
        processed_images=processed_images,
        passed_images=passed_images,
        failed_images=failed_images,
        results=results,
        summary=summary,
    )