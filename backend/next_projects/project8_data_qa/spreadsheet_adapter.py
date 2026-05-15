import json
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlparse

import gspread
import pandas as pd
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.llm import get_async_openai_client
from app.core.config import BASE_DIR, get_settings
from app.models.attachment import Attachment


class SpreadsheetQuestionRequest(BaseModel):
    source_id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    sheet_name: str | None = None
    max_rows: int = Field(default=200, ge=1, le=2000)


class SpreadsheetAnswer(BaseModel):
    answer: str
    rows_considered: int
    columns: list[str] = []


def _resolve_upload_root() -> Path:
    settings = get_settings()
    upload_dir = Path(settings.upload_dir)
    if not upload_dir.is_absolute():
        upload_dir = BASE_DIR / upload_dir
    return upload_dir


async def _load_attachment_dataframe(
    db: AsyncSession,
    *,
    user_id: str,
    source_id: str,
    sheet_name: str | None,
) -> pd.DataFrame | None:
    result = await db.execute(select(Attachment).where(Attachment.id == source_id, Attachment.user_id == user_id))
    attachment = result.scalar_one_or_none()
    if not attachment:
        return None

    path = _resolve_upload_root() / attachment.storage_path
    if not path.exists():
        raise FileNotFoundError(f'Spreadsheet source not found: {attachment.file_name}')
    return _read_dataframe_from_path(path, sheet_name=sheet_name)


def _google_client() -> gspread.Client | None:
    settings = get_settings()
    raw = (settings.google_service_account_json or '').strip()
    if not raw:
        return None

    raw_path = Path(raw)
    candidate_paths = [raw_path]
    if not raw_path.is_absolute():
        candidate_paths.extend([BASE_DIR / raw_path, BASE_DIR.parent / raw_path])

    # Accept either a filesystem path to service-account JSON or inline JSON content.
    for candidate in candidate_paths:
        if candidate.exists():
            return gspread.service_account(filename=str(candidate))

    try:
        credentials = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            'GOOGLE_SERVICE_ACCOUNT_JSON must be a valid JSON object string or a valid file path to a JSON file.'
        ) from exc

    if not isinstance(credentials, dict):
        raise ValueError('GOOGLE_SERVICE_ACCOUNT_JSON JSON content must be an object.')

    return gspread.service_account_from_dict(credentials)


def _read_dataframe_from_path(path: Path, *, sheet_name: str | None) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix in {'.csv', '.tsv'}:
        separator = '\t' if suffix == '.tsv' else ','
        return pd.read_csv(path, sep=separator)
    if suffix in {'.xlsx', '.xls', '.ods'}:
        return pd.read_excel(path, sheet_name=sheet_name or 0)
    raise ValueError(f'Unsupported spreadsheet format: {path.suffix}')


def _is_google_sheet(source_id: str) -> bool:
    return 'docs.google.com/spreadsheets' in source_id or len(source_id) > 20 and '/' not in source_id and '.' not in source_id


def _is_http_url(source_id: str) -> bool:
    parsed = urlparse(source_id)
    return parsed.scheme in {'http', 'https'} and bool(parsed.netloc)


def _extract_google_sheet_id(source_id: str) -> str:
    if '/d/' in source_id:
        return source_id.split('/d/', 1)[1].split('/', 1)[0]
    return source_id


def _load_public_google_sheet_dataframe(source_id: str, *, sheet_name: str | None) -> pd.DataFrame:
    sheet_id = _extract_google_sheet_id(source_id)
    url = f'https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv'
    if sheet_name:
        url = f'{url}&sheet={quote_plus(sheet_name)}'
    return pd.read_csv(url)


def _load_google_sheet_dataframe(source_id: str, *, sheet_name: str | None) -> pd.DataFrame:
    client_error: ValueError | None = None
    try:
        client = _google_client()
    except ValueError as exc:
        client = None
        client_error = exc

    if client is not None:
        spreadsheet = client.open_by_key(_extract_google_sheet_id(source_id))
        worksheet = spreadsheet.worksheet(sheet_name) if sheet_name else spreadsheet.sheet1
        records = worksheet.get_all_records()
        return pd.DataFrame(records)

    try:
        return _load_public_google_sheet_dataframe(source_id, sheet_name=sheet_name)
    except Exception as exc:
        if client_error is not None:
            raise ValueError(
                f'{str(client_error)} Also failed to read the sheet as a public Google Sheet.'
            ) from exc
        raise ValueError(
            'Unable to access Google Sheet. Configure GOOGLE_SERVICE_ACCOUNT_JSON for private sheets or make the sheet public.'
        ) from exc


def _load_local_dataframe(source_id: str, *, sheet_name: str | None) -> pd.DataFrame | None:
    candidate = Path(source_id)
    if not candidate.is_absolute():
        candidate = BASE_DIR / source_id
    if not candidate.exists():
        return None
    return _read_dataframe_from_path(candidate, sheet_name=sheet_name)


def _load_remote_dataframe(source_id: str, *, sheet_name: str | None) -> pd.DataFrame | None:
    if not _is_http_url(source_id):
        return None

    lower = source_id.lower()
    if '.csv' in lower or 'format=csv' in lower:
        return pd.read_csv(source_id)
    if '.tsv' in lower:
        return pd.read_csv(source_id, sep='\t')
    if '.xlsx' in lower or '.xls' in lower or '.ods' in lower:
        return pd.read_excel(source_id, sheet_name=sheet_name or 0)
    return None


def _heuristic_answer(df: pd.DataFrame, question: str) -> str:
    normalized = question.lower()
    if 'how many row' in normalized or 'row count' in normalized or 'number of rows' in normalized:
        return f'The spreadsheet contains {len(df)} rows.'
    if 'column' in normalized:
        return f'Columns: {", ".join(map(str, df.columns.tolist()))}'
    if 'preview' in normalized or 'sample' in normalized or 'show' in normalized:
        preview = df.head(5).fillna('').to_dict(orient='records')
        return f'Preview rows: {json.dumps(preview, default=str)}'
    return (
        f'Loaded {len(df)} rows across {len(df.columns)} columns. '
        'LLM is not configured, so only summary-style spreadsheet answers are available.'
    )


async def _llm_answer(df: pd.DataFrame, question: str, *, max_rows: int) -> str:
    settings = get_settings()
    if not settings.llm_model or not settings.litellm_api_key:
        return _heuristic_answer(df, question)

    sampled = df.head(min(max_rows, 25)).fillna('')
    payload = {
        'columns': [str(column) for column in sampled.columns.tolist()],
        'row_count': int(len(df)),
        'sample_rows': sampled.astype(str).to_dict(orient='records'),
    }

    client = get_async_openai_client()
    response = await client.chat.completions.create(
        model=settings.llm_model,
        temperature=0,
        messages=[
            {'role': 'system', 'content': 'Answer spreadsheet questions using only the provided tabular snapshot.'},
            {'role': 'user', 'content': f'Question: {question}\n\nTable snapshot: {json.dumps(payload)}'},
        ],
    )
    return (response.choices[0].message.content or '').strip() or _heuristic_answer(df, question)


async def answer_spreadsheet_question(
    request: SpreadsheetQuestionRequest,
    *,
    db: AsyncSession | None = None,
    user_id: str | None = None,
) -> SpreadsheetAnswer:
    dataframe: pd.DataFrame | None = None

    if db is not None and user_id is not None:
        dataframe = await _load_attachment_dataframe(
            db,
            user_id=user_id,
            source_id=request.source_id,
            sheet_name=request.sheet_name,
        )

    if dataframe is None and _is_google_sheet(request.source_id):
        dataframe = _load_google_sheet_dataframe(request.source_id, sheet_name=request.sheet_name)

    if dataframe is None:
        dataframe = _load_remote_dataframe(request.source_id, sheet_name=request.sheet_name)

    if dataframe is None:
        dataframe = _load_local_dataframe(request.source_id, sheet_name=request.sheet_name)

    if dataframe is None:
        raise ValueError('Spreadsheet source could not be resolved from attachment id, local path, or Google Sheet id/url.')

    limited = dataframe.head(request.max_rows)
    answer = await _llm_answer(limited, request.question, max_rows=request.max_rows)
    return SpreadsheetAnswer(
        answer=answer,
        rows_considered=int(len(limited)),
        columns=[str(column) for column in limited.columns.tolist()],
    )
