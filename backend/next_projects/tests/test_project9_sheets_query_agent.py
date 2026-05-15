import pandas as pd
import pytest

import next_projects.project9_sheets_query_agent.service as project9_service
from app.services.sheets_service import extract_google_sheet_id, load_sheet_as_dataframe
from next_projects.project9_sheets_query_agent.models import SheetsAgentQueryRequest


def test_extract_google_sheet_id_from_url() -> None:
    source = 'https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz1234567890/edit#gid=0'
    assert extract_google_sheet_id(source) == '1AbCdEfGhIjKlMnOpQrStUvWxYz1234567890'


def test_load_sheet_as_dataframe_from_csv(tmp_path) -> None:
    csv_path = tmp_path / 'sample.csv'
    csv_path.write_text('name,score\nAlice,10\nBob,12\n', encoding='utf-8')

    df = load_sheet_as_dataframe(str(csv_path))

    assert len(df) == 2
    assert list(df.columns) == ['name', 'score']


def test_load_sheet_as_dataframe_from_excel(tmp_path) -> None:
    xlsx_path = tmp_path / 'sample.xlsx'
    pd.DataFrame([
        {'name': 'Alice', 'score': 10},
        {'name': 'Bob', 'score': 12},
    ]).to_excel(xlsx_path, index=False)

    df = load_sheet_as_dataframe(str(xlsx_path))

    assert len(df) == 2
    assert list(df.columns) == ['name', 'score']


def test_load_sheet_as_dataframe_from_remote_csv_url(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str] = {}

    def _read_csv_stub(url: str, *args, **kwargs) -> pd.DataFrame:
        captured['url'] = url
        return pd.DataFrame([
            {'name': 'Alice', 'score': 10},
            {'name': 'Bob', 'score': 12},
        ])

    monkeypatch.setattr('app.services.sheets_service.pd.read_csv', _read_csv_stub)

    df = load_sheet_as_dataframe('https://example.com/sample.csv')

    assert captured['url'] == 'https://example.com/sample.csv'
    assert len(df) == 2
    assert list(df.columns) == ['name', 'score']


def test_load_sheet_as_dataframe_from_remote_excel_url(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str] = {}

    def _read_excel_stub(url: str, *args, **kwargs) -> pd.DataFrame:
        captured['url'] = url
        return pd.DataFrame([
            {'name': 'Alice', 'score': 10},
        ])

    monkeypatch.setattr('app.services.sheets_service.pd.read_excel', _read_excel_stub)

    df = load_sheet_as_dataframe('https://example.com/sample.xlsx')

    assert captured['url'] == 'https://example.com/sample.xlsx'
    assert len(df) == 1
    assert list(df.columns) == ['name', 'score']


@pytest.mark.asyncio
async def test_answer_sheet_query_uses_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    def _load_stub(source_id: str, sheet_name: str | None = None) -> pd.DataFrame:  # noqa: ARG001
        return pd.DataFrame([
            {'name': 'Alice', 'score': 10},
            {'name': 'Bob', 'score': 12},
            {'name': 'Cara', 'score': 15},
        ])

    def _run_stub(df: pd.DataFrame, question: str) -> str:
        assert len(df) == 2
        assert 'highest score' in question.lower()
        return 'Cara has the highest score (15).'

    monkeypatch.setattr(project9_service, 'load_sheet_as_dataframe', _load_stub)
    monkeypatch.setattr(project9_service, '_run_pandas_agent', _run_stub)

    result = await project9_service.answer_sheet_query(
        SheetsAgentQueryRequest(
            source_id='ignored.csv',
            question='Who has the highest score?',
            max_rows=2,
        )
    )

    assert result.rows_considered == 2
    assert result.columns == ['name', 'score']
    assert 'highest score' in result.answer.lower()
