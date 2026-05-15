import json
import os
from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class ValidationRuleDefinition:
    rule_id: str
    description: str
    field_path: str
    operator: str
    expected: Any = None
    required: bool = True


_DEFAULT_RULES: list[ValidationRuleDefinition] = [
    ValidationRuleDefinition(
        rule_id='mime_type_allowed',
        description='Image MIME type must be one of the supported web formats.',
        field_path='metadata.mime_type',
        operator='in',
        expected=['image/png', 'image/jpeg', 'image/jpg', 'image/webp'],
    ),
    ValidationRuleDefinition(
        rule_id='max_size_5mb',
        description='Image file size must be less than or equal to 5 MB.',
        field_path='metadata.size_bytes',
        operator='lte',
        expected=5 * 1024 * 1024,
    ),
    ValidationRuleDefinition(
        rule_id='min_width_512',
        description='Image width must be at least 512 pixels.',
        field_path='metadata.width',
        operator='gte',
        expected=512,
    ),
    ValidationRuleDefinition(
        rule_id='min_height_512',
        description='Image height must be at least 512 pixels.',
        field_path='metadata.height',
        operator='gte',
        expected=512,
    ),
]


def _from_mapping(item: dict[str, Any]) -> ValidationRuleDefinition:
    return ValidationRuleDefinition(
        rule_id=str(item.get('rule_id', '')).strip(),
        description=str(item.get('description', '')).strip(),
        field_path=str(item.get('field_path', '')).strip(),
        operator=str(item.get('operator', '')).strip().lower(),
        expected=item.get('expected'),
        required=bool(item.get('required', True)),
    )


def load_default_rules() -> list[ValidationRuleDefinition]:
    """Load default rules, allowing runtime override via IMAGE_VALIDATION_RULES_JSON.

    Expected env format is a JSON array of rule objects compatible with ValidationRuleDefinition.
    If parsing fails, hardcoded defaults are returned.
    """
    raw = os.getenv('IMAGE_VALIDATION_RULES_JSON', '').strip()
    if not raw:
        return list(_DEFAULT_RULES)

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return list(_DEFAULT_RULES)

    if not isinstance(payload, list):
        return list(_DEFAULT_RULES)

    rules: list[ValidationRuleDefinition] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        parsed = _from_mapping(item)
        if parsed.rule_id and parsed.field_path and parsed.operator:
            rules.append(parsed)

    return rules or list(_DEFAULT_RULES)


def serialize_rule(rule: ValidationRuleDefinition) -> dict[str, Any]:
    return asdict(rule)