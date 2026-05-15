import json
from pathlib import Path
from urllib.parse import urlparse

import gspread
import pandas as pd

from app.core.config import BASE_DIR, get_settings


class SheetsServiceConfigurationError(RuntimeError):
    pass


def _google_client() -> gspread.Client:
    settings = get_settings()
    raw = (settings.google_service_account_json or '').strip()

    if not raw:
        raise SheetsServiceConfigurationError(
            'GOOGLE_SERVICE_ACCOUNT_JSON is required for Google Sheets sources.'
        )

    raw_path = Path(raw)
    candidate_paths = [raw_path]
    if not raw_path.is_absolute():
        candidate_paths.extend([BASE_DIR / raw_path, BASE_DIR.parent / raw_path])

    # Backward-compatible mode: if a path is provided, use the file.
    # Preferred mode: full JSON string (service_account_from_dict).
    for candidate in candidate_paths:
        if candidate.exists():
            return gspread.service_account(filename=str(candidate))

    try:
        return gspread.service_account_from_dict(json.loads(raw))
    except json.JSONDecodeError as exc:
        raise SheetsServiceConfigurationError(
            'GOOGLE_SERVICE_ACCOUNT_JSON must be a valid JSON string or an existing file path.'
        ) from exc


def _read_dataframe_from_path(path: Path, *, sheet_name: str | None) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix in {'.csv', '.tsv'}:
        sep = '\t' if suffix == '.tsv' else ','
        return pd.read_csv(path, sep=sep)
    if suffix in {'.xlsx', '.xls', '.ods'}:
        return pd.read_excel(path, sheet_name=sheet_name or 0)
    raise ValueError(f'Unsupported spreadsheet format: {path.suffix}')


def is_google_sheet_source(source_id: str) -> bool:
    return 'docs.google.com/spreadsheets' in source_id or (
        len(source_id) > 20 and '/' not in source_id and '.' not in source_id
    )


def _is_http_url(source_id: str) -> bool:
    parsed = urlparse(source_id)
    return parsed.scheme in {'http', 'https'} and bool(parsed.netloc)


def _read_dataframe_from_url(source_id: str, *, sheet_name: str | None) -> pd.DataFrame | None:
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


def extract_google_sheet_id(source_id: str) -> str:
    if '/d/' in source_id:
        return source_id.split('/d/', 1)[1].split('/', 1)[0]
    return source_id


def load_sheet_as_dataframe(source_id: str, sheet_name: str | None = None) -> pd.DataFrame:
    if is_google_sheet_source(source_id):
        client = _google_client()
        spreadsheet = client.open_by_key(extract_google_sheet_id(source_id))
        worksheet = spreadsheet.worksheet(sheet_name) if sheet_name else spreadsheet.sheet1
        records = worksheet.get_all_records()
        return pd.DataFrame(records)

    url_df = _read_dataframe_from_url(source_id, sheet_name=sheet_name)
    if url_df is not None:
        return url_df

    source_path = Path(source_id)
    if not source_path.is_absolute():
        source_path = BASE_DIR / source_path

    if not source_path.exists():
        raise FileNotFoundError(f'Spreadsheet file not found: {source_id}')

    return _read_dataframe_from_path(source_path, sheet_name=sheet_name)
