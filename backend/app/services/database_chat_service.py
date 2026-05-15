import asyncio
import logging
import re

from app.database.connector import DatabaseConnectionError, redacted_database_url, resolve_database_config
from app.database.tabular_source import TabularSourceError
from app.database.schema_reader import SchemaSnapshot, read_schema_snapshot
from app.schemas.database_chat import (
    DatabaseConnectRequest,
    DatabaseConnectResponse,
    DatabaseQueryRequest,
    DatabaseQueryResponse,
    DatabaseTableColumn,
    DatabaseTableSchema,
)
from app.services.query_executor import execute_read_only_query
from app.services.query_validator import detect_database_intent, validate_read_only_sql
from app.services.sql_generator import generate_sql_from_question

logger = logging.getLogger(__name__)


def _schema_to_response(snapshot: SchemaSnapshot) -> list[DatabaseTableSchema]:
    return [
        DatabaseTableSchema(
            name=table.name,
            columns=[DatabaseTableColumn(name=column.name, data_type=column.data_type) for column in table.columns],
        )
        for table in snapshot.tables
    ]


def _build_explanation(question: str, *, row_count: int, sql: str) -> str:
    if row_count == 0:
        return f'No rows matched the database question: {question}'
    return f'Executed a read-only query for the question and returned {row_count} row(s).'


def _answer_schema_metadata(question: str, snapshot: SchemaSnapshot) -> DatabaseQueryResponse | None:
    lowered = question.lower()
    tokens = set(re.findall(r'[a-z0-9_]+', lowered))
    asks_table_inventory = any(
        re.search(pattern, lowered)
        for pattern in (
            r'\bhow\s+many\s+tables?\b',
            r'\b(number|count)\s+of\s+tables?\b',
            r'\b(list|show)\s+(all\s+)?tables?\b',
            r'\btable\s+names\b',
            r'\bnames\s+of\s+tables\b',
        )
    )
    if not asks_table_inventory:
        return None

    asks_count = bool(
        re.search(r'\bhow\s+many\s+tables?\b', lowered)
        or re.search(r'\b(number|count)\s+of\s+tables?\b', lowered)
    )
    asks_names = bool(
        re.search(r'\b(list|show)\s+(all\s+)?tables?\b', lowered)
        or re.search(r'\btable\s+names\b', lowered)
        or re.search(r'\bnames\s+of\s+tables\b', lowered)
        or ('name' in tokens or 'names' in tokens) and ('table' in tokens or 'tables' in tokens)
    )

    table_names = sorted(snapshot.table_names)
    rows = [{'table_name': name} for name in table_names]
    count = len(table_names)

    if asks_count and asks_names:
        message = f'Your database has {count} table(s). Listing all table names.'
    elif asks_count:
        message = f'Your database has {count} table(s).'
        rows = [{'table_count': count}]
    else:
        message = f'Listing {count} table name(s) from the current schema.'

    columns = list(rows[0].keys()) if rows else ['table_name']
    return DatabaseQueryResponse(
        detected_intent='database',
        allowed=True,
        message=message,
        explanation='Answered directly from the connected schema snapshot.',
        columns=columns,
        rows=rows,
        row_count=len(rows),
    )


async def connect_to_database(payload: DatabaseConnectRequest) -> DatabaseConnectResponse:
    config = resolve_database_config(payload.connection)
    logger.info('database connect requested db_type=%s target=%s', config.db_type, redacted_database_url(config.url))
    snapshot = await asyncio.to_thread(read_schema_snapshot, config)
    return DatabaseConnectResponse(
        connected=True,
        message='Database connection verified successfully.',
        db_type=config.db_type,
        database=config.database,
        schema_name=config.schema,
        tables=_schema_to_response(snapshot),
        schema_summary=snapshot.summary,
    )


async def answer_database_question(payload: DatabaseQueryRequest) -> DatabaseQueryResponse:
    config = resolve_database_config(payload.connection)
    max_rows = min(payload.max_rows, config.max_rows)
    logger.info('database question received db_type=%s question=%s', config.db_type, payload.question)
    snapshot = await asyncio.to_thread(read_schema_snapshot, config)

    metadata_answer = _answer_schema_metadata(payload.question, snapshot)
    if metadata_answer is not None:
        logger.info('database schema metadata answered directly question=%s', payload.question)
        return metadata_answer

    if not detect_database_intent(payload.question, snapshot):
        return DatabaseQueryResponse(
            detected_intent='general',
            allowed=False,
            message='This does not look like a database question. Ask about tables, counts, filters, totals, or records.',
            explanation='The request was not routed to the SQL engine.',
        )

    generated = await generate_sql_from_question(payload.question, config=config, schema=snapshot)
    validation = validate_read_only_sql(generated.sql, snapshot)
    if not validation.allowed:
        logger.warning('database sql blocked reason=%s sql=%s', validation.reason, generated.sql)
        return DatabaseQueryResponse(
            detected_intent='database',
            allowed=False,
            message=validation.reason,
            sql=generated.sql,
            explanation='The generated SQL was blocked by the safety layer.',
        )

    try:
        execution = await execute_read_only_query(config, generated.sql, generated.params, max_rows=max_rows)
    except TimeoutError as exc:
        logger.warning('database query timeout sql=%s', generated.sql)
        return DatabaseQueryResponse(
            detected_intent='database',
            allowed=False,
            message='The database query timed out.',
            sql=generated.sql,
            explanation=str(exc),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception('database query failed sql=%s', generated.sql)
        return DatabaseQueryResponse(
            detected_intent='database',
            allowed=False,
            message='Failed to execute the database query.',
            sql=generated.sql,
            explanation=str(exc),
        )

    logger.info('database query succeeded rows=%s sql=%s', execution.row_count, generated.sql)
    return DatabaseQueryResponse(
        detected_intent='database',
        allowed=True,
        message='Database query executed successfully.',
        sql=generated.sql,
        explanation=_build_explanation(payload.question, row_count=execution.row_count, sql=generated.sql),
        columns=execution.columns,
        rows=execution.rows,
        row_count=execution.row_count,
        formatted_table=execution.formatted_table,
    )


__all__ = ['DatabaseConnectionError', 'answer_database_question', 'connect_to_database']
