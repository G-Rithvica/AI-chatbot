import base64
from types import SimpleNamespace

import pandas as pd
import pytest

import next_projects.project8_data_qa.image_validation as image_validation
import next_projects.project8_data_qa.spreadsheet_adapter as spreadsheet_adapter
from next_projects.project8_data_qa.image_rules import _evaluate_rule, _png_dimensions
from next_projects.project8_data_qa.image_validation import _evaluate_operator, _value_at_path
from next_projects.project8_data_qa.spreadsheet_adapter import SpreadsheetQuestionRequest, answer_spreadsheet_question
from next_projects.project8_data_qa.sql_guard import evaluate_generated_sql


def _tiny_png_bytes() -> bytes:
    return base64.b64decode(
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a6d8AAAAASUVORK5CYII='
    )


def test_sql_guard_blocks_multiple_statements() -> None:
    result = evaluate_generated_sql('SELECT 1; SELECT 2')
    assert result.allowed is False


@pytest.mark.asyncio
async def test_spreadsheet_query_answers_row_count(tmp_path) -> None:
    csv_path = tmp_path / 'sample.csv'
    csv_path.write_text('name,score\nAlice,10\nBob,12\n', encoding='utf-8')

    result = await answer_spreadsheet_question(
        SpreadsheetQuestionRequest(source_id=str(csv_path), question='How many rows are there?')
    )

    assert result.rows_considered == 2
    assert '2' in result.answer
    assert result.columns == ['name', 'score']


@pytest.mark.asyncio
async def test_spreadsheet_query_supports_excel(tmp_path) -> None:
    xlsx_path = tmp_path / 'sample.xlsx'
    pd.DataFrame(
        [
            {'name': 'Alice', 'score': 10},
            {'name': 'Bob', 'score': 12},
            {'name': 'Cara', 'score': 15},
        ]
    ).to_excel(xlsx_path, index=False)

    result = await answer_spreadsheet_question(
        SpreadsheetQuestionRequest(source_id=str(xlsx_path), question='How many rows are there?')
    )

    assert result.rows_considered == 3
    assert '3' in result.answer
    assert result.columns == ['name', 'score']


def test_google_client_rejects_invalid_json_configuration(monkeypatch) -> None:
    monkeypatch.setattr(
        spreadsheet_adapter,
        'get_settings',
        lambda: SimpleNamespace(google_service_account_json='not-a-json-value'),
    )

    with pytest.raises(ValueError, match='GOOGLE_SERVICE_ACCOUNT_JSON must be a valid JSON object string'):
        spreadsheet_adapter._google_client()


@pytest.mark.asyncio
async def test_spreadsheet_query_supports_public_google_sheet_without_credentials(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def fake_read_csv(url: str, *args, **kwargs):
        captured['url'] = url
        return pd.DataFrame([{'name': 'Alice', 'score': 10}, {'name': 'Bob', 'score': 12}])

    monkeypatch.setattr(
        spreadsheet_adapter,
        'get_settings',
        lambda: SimpleNamespace(google_service_account_json=None, llm_model=None, litellm_api_key=None),
    )
    monkeypatch.setattr(spreadsheet_adapter.pd, 'read_csv', fake_read_csv)

    result = await answer_spreadsheet_question(
        SpreadsheetQuestionRequest(
            source_id='https://docs.google.com/spreadsheets/d/abc1234567890/edit#gid=0',
            question='How many rows are there?',
        )
    )

    assert captured['url'].startswith('https://docs.google.com/spreadsheets/d/abc1234567890/gviz/tq?tqx=out:csv')
    assert result.rows_considered == 2
    assert result.columns == ['name', 'score']


@pytest.mark.asyncio
async def test_spreadsheet_query_supports_remote_csv_url(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def fake_read_csv(url: str, *args, **kwargs):
        captured['url'] = url
        return pd.DataFrame([{'name': 'Alice', 'score': 10}, {'name': 'Bob', 'score': 12}])

    monkeypatch.setattr(spreadsheet_adapter.pd, 'read_csv', fake_read_csv)

    result = await answer_spreadsheet_question(
        SpreadsheetQuestionRequest(
            source_id='https://example.com/report.csv',
            question='How many rows are there?',
        )
    )

    assert captured['url'] == 'https://example.com/report.csv'
    assert result.rows_considered == 2
    assert result.columns == ['name', 'score']


@pytest.mark.asyncio
async def test_spreadsheet_query_supports_remote_excel_url(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def fake_read_excel(url: str, *args, **kwargs):
        captured['url'] = url
        return pd.DataFrame([{'name': 'Alice', 'score': 10}])

    monkeypatch.setattr(spreadsheet_adapter.pd, 'read_excel', fake_read_excel)

    result = await answer_spreadsheet_question(
        SpreadsheetQuestionRequest(
            source_id='https://example.com/report.xlsx',
            question='How many rows are there?',
        )
    )

    assert captured['url'] == 'https://example.com/report.xlsx'
    assert result.rows_considered == 1
    assert result.columns == ['name', 'score']


def test_png_rules_detect_format_and_dimensions() -> None:
    data = _tiny_png_bytes()
    dimensions = _png_dimensions(data)
    assert dimensions == (1, 1)

    outcome = _evaluate_rule('is_png', data=data, mime_type='image/png', size_bytes=len(data))
    assert outcome.passed is True


def test_image_validation_field_path_resolution() -> None:
    payload = {
        'metadata': {'width': 1024, 'height': 768},
        'extracted': {'fields': {'invoice_number': 'INV-1001'}},
    }
    assert _value_at_path(payload, 'metadata.width') == 1024
    assert _value_at_path(payload, 'extracted.fields.invoice_number') == 'INV-1001'
    assert _value_at_path(payload, 'extracted.fields.missing') is None


def test_image_validation_operator_evaluation() -> None:
    assert _evaluate_operator(operator='gte', expected=512, extracted=1024) is True
    assert _evaluate_operator(operator='lte', expected=10, extracted=11) is False
    assert _evaluate_operator(operator='contains', expected='inv', extracted='INV-1001') is True
    assert _evaluate_operator(operator='in', expected=['image/png', 'image/jpeg'], extracted='image/png') is True
    assert _evaluate_operator(operator='regex', expected=r'^INV-\d+$', extracted='INV-1001') is True


@pytest.mark.asyncio
async def test_image_validation_batch_supports_multiple_images(monkeypatch) -> None:
    async def fake_validate_image(request, *, db, user_id):
        if request.image_id == 'missing-image':
            raise ValueError('Image source not found for provided image_id.')

        passed = request.image_id != 'bad-image'
        extracted = image_validation.ExtractedImageData(
            metadata={
                'format': 'PNG',
                'mime_type': 'image/png',
                'size_bytes': 1024,
                'width': 1024,
                'height': 1024,
                'source_type': 'attachment',
            },
            text='Invoice INV-1001',
            labels=['invoice'],
            fields={'invoice_number': 'INV-1001'},
        )
        rule_result = image_validation.ImageValidationRuleResult(
            rule_id='invoice_present',
            description='Invoice number must be present',
            operator='contains',
            expected='INV-',
            extracted='INV-1001',
            passed=passed,
            required=True,
            message='Rule satisfied.' if passed else 'Rule failed.',
        )
        return image_validation.ImageValidationResult(
            image_id=request.image_id,
            source_name='sample.png',
            source_type='attachment',
            source_thread_id=None,
            extracted_data=extracted,
            passed=passed,
            failed_rules=[] if passed else [rule_result],
            rule_results=[rule_result],
            summary='ok' if passed else 'failed',
            chat_summary='summary',
        )

    monkeypatch.setattr(image_validation, 'validate_image', fake_validate_image)

    batch_request = image_validation.ImageValidationBatchRequest(
        image_ids=['good-image', 'bad-image', 'missing-image'],
        include_default_rules=True,
        rules=[],
    )

    result = await image_validation.validate_images_batch(batch_request, db=None, user_id='u-1')

    assert result.total_images == 3
    assert result.processed_images == 2
    assert result.passed_images == 1
    assert result.failed_images == 2
    assert len(result.results) == 3
    assert result.results[0].success is True
    assert result.results[1].success is True
    assert result.results[2].success is False
