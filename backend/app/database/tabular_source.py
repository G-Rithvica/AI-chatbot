import hashlib
import sqlite3
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd

from app.core.config import BASE_DIR

_TABULAR_CACHE_DIR = BASE_DIR / '.database_url_cache'
_TABULAR_CACHE_DIR.mkdir(parents=True, exist_ok=True)


class TabularSourceError(ValueError):
    pass


def _looks_like_google_sheet(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.netloc.endswith('docs.google.com') and '/spreadsheets/d/' in parsed.path


def _google_sheet_export_url(url: str) -> str:
    parsed = urlparse(url)
    if '/spreadsheets/d/' not in parsed.path:
        return url

    path_tail = parsed.path.split('/spreadsheets/d/', 1)[1]
    sheet_id = path_tail.split('/', 1)[0]
    query = parse_qs(parsed.query)
    gid = query.get('gid', [None])[0]
    fragment_gid = parsed.fragment.split('gid=', 1)[1] if 'gid=' in parsed.fragment else None
    target_gid = gid or fragment_gid
    if target_gid:
        return f'https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={target_gid}'
    return f'https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv'


def _read_dataframe_from_url(url: str) -> pd.DataFrame:
    candidate_url = _google_sheet_export_url(url) if _looks_like_google_sheet(url) else url
    try:
        return pd.read_csv(candidate_url)
    except Exception as csv_exc:  # noqa: BLE001
        try:
            return pd.read_excel(candidate_url)
        except Exception as excel_exc:  # noqa: BLE001
            if _looks_like_google_sheet(url):
                raise TabularSourceError(
                    'The Google Sheet could not be read. Ensure it is publicly shared or published as CSV.'
                ) from excel_exc
            raise TabularSourceError(f'Failed to read tabular URL: {csv_exc}') from excel_exc


def _safe_table_name(url: str) -> str:
    parsed = urlparse(url)
    base_name = Path(parsed.path).stem or 'sheet_data'
    safe = ''.join(character if character.isalnum() or character == '_' else '_' for character in base_name.lower())
    safe = safe.strip('_') or 'sheet_data'
    if safe[0].isdigit():
        safe = f'table_{safe}'
    return safe[:48]


def _cache_path_for_url(url: str) -> Path:
    digest = hashlib.sha256(url.encode('utf-8')).hexdigest()
    return _TABULAR_CACHE_DIR / f'{digest}.sqlite'


def materialize_tabular_source(url: str) -> tuple[Path, str]:
    dataframe = _read_dataframe_from_url(url)
    cache_path = _cache_path_for_url(url)
    table_name = _safe_table_name(url)

    conn = sqlite3.connect(cache_path)
    try:
        dataframe.to_sql(table_name, conn, if_exists='replace', index=False)
        conn.commit()
    finally:
        conn.close()

    return cache_path, cache_path.name
