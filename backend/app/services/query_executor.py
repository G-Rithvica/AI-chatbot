import asyncio
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text

from app.database.connector import ResolvedDatabaseConfig, create_database_engine
from app.services.query_validator import normalize_query_limit


@dataclass(frozen=True)
class QueryExecutionResult:
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    formatted_table: str | None


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    return str(value)


def _format_table(columns: list[str], rows: list[dict[str, Any]]) -> str | None:
    if not columns:
        return None
    header = '| ' + ' | '.join(columns) + ' |'
    divider = '| ' + ' | '.join('---' for _ in columns) + ' |'
    body = [
        '| ' + ' | '.join(str(row.get(column, '')) for column in columns) + ' |'
        for row in rows
    ]
    return '\n'.join([header, divider, *body])


def _apply_dialect_timeout(connection, config: ResolvedDatabaseConfig) -> None:
    timeout_ms = max(1, config.timeout_seconds) * 1000
    if config.dialect_name == 'postgresql':
        connection.exec_driver_sql(f'SET statement_timeout = {timeout_ms}')
    elif config.dialect_name == 'mysql':
        connection.exec_driver_sql(f'SET SESSION MAX_EXECUTION_TIME={timeout_ms}')


def _execute_sync(
    config: ResolvedDatabaseConfig,
    sql: str,
    params: dict[str, Any],
    *,
    max_rows: int,
) -> QueryExecutionResult:
    engine = create_database_engine(config)
    try:
        with engine.connect() as connection:
            _apply_dialect_timeout(connection, config)
            limited_sql = normalize_query_limit(sql, max_rows=max_rows)
            result = connection.execute(text(limited_sql), params)
            mappings = result.mappings().fetchmany(max_rows)
            rows = [{key: _json_safe(value) for key, value in row.items()} for row in mappings]
            columns = list(result.keys())
            return QueryExecutionResult(
                columns=columns,
                rows=rows,
                row_count=len(rows),
                formatted_table=_format_table(columns, rows),
            )
    finally:
        engine.dispose()


async def execute_read_only_query(
    config: ResolvedDatabaseConfig,
    sql: str,
    params: dict[str, Any],
    *,
    max_rows: int,
) -> QueryExecutionResult:
    return await asyncio.wait_for(
        asyncio.to_thread(_execute_sync, config, sql, params, max_rows=max_rows),
        timeout=max(2, config.timeout_seconds + 2),
    )
