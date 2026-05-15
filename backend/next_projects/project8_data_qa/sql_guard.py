import json
import re
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.llm import get_async_openai_client
from app.core.config import get_settings


class SqlQuestionRequest(BaseModel):
    question: str = Field(min_length=1)
    max_rows: int = Field(default=50, ge=1, le=200)
    source_id: str | None = None
    sheet_name: str | None = None


class SqlQueryRequest(BaseModel):
    sql: str = Field(min_length=1)
    max_rows: int = Field(default=50, ge=1, le=200)


class SqlGuardResult(BaseModel):
    allowed: bool
    reason: str
    sql: str | None = None


class SqlQueryResult(BaseModel):
    allowed: bool
    reason: str
    sql: str | None = None
    answer: str | None = None
    columns: list[str] = []
    rows: list[dict[str, Any]] = []
    row_count: int = 0


def evaluate_generated_sql(sql: str) -> SqlGuardResult:
    normalized = sql.strip().lower().rstrip(';')
    blocked = ('drop ', 'delete ', 'truncate ', 'alter ', 'insert ', 'update ', 'create ', 'grant ', 'revoke ')
    if not normalized:
        return SqlGuardResult(allowed=False, reason='SQL is empty.')
    if ';' in normalized:
        return SqlGuardResult(allowed=False, reason='Only a single SQL statement is allowed.')
    if any(token in normalized for token in blocked):
        return SqlGuardResult(allowed=False, reason='Mutation statements are blocked in Project 8 prototype.')
    if not (normalized.startswith('select ') or normalized.startswith('with ')):
        return SqlGuardResult(allowed=False, reason='Only read-only SELECT statements are allowed.')
    return SqlGuardResult(allowed=True, reason='Read-only SQL accepted.', sql=sql)


async def _load_schema_summary(db: AsyncSession) -> str:
    query = text(
        """
        SELECT table_name, column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'public'
        ORDER BY table_name, ordinal_position
        """
    )
    result = await db.execute(query)
    grouped: dict[str, list[str]] = {}
    for table_name, column_name, data_type in result.fetchall():
        grouped.setdefault(str(table_name), []).append(f'{column_name} ({data_type})')
    return '\n'.join(f'{table}: {", ".join(columns)}' for table, columns in grouped.items())


def _heuristic_sql(question: str) -> str | None:
    normalized = question.lower()
    table_map = {
        'users': 'users',
        'threads': 'threads',
        'messages': 'messages',
        'attachments': 'attachments',
        'generated images': 'generated_images',
        'generated image': 'generated_images',
        'images': 'generated_images',
    }

    if 'how many' in normalized or 'count' in normalized:
        for phrase, table in table_map.items():
            if phrase in normalized:
                return f'SELECT COUNT(*) AS count FROM {table}'
    if 'latest messages' in normalized or 'recent messages' in normalized:
        return 'SELECT id, thread_id, role, created_at FROM messages ORDER BY created_at DESC LIMIT 10'
    if 'latest threads' in normalized or 'recent threads' in normalized:
        return 'SELECT id, name, updated_at FROM threads ORDER BY updated_at DESC LIMIT 10'
    return None


async def generate_sql_from_question(db: AsyncSession, question: str) -> str:
    heuristic = _heuristic_sql(question)
    if heuristic:
        return heuristic

    settings = get_settings()
    if not settings.llm_model or not settings.litellm_api_key:
        raise ValueError('No SQL heuristic matched and LLM_MODEL/LITELLM_API_KEY is not configured for NL-to-SQL.')

    schema_summary = await _load_schema_summary(db)
    client = get_async_openai_client()
    prompt = (
        'Generate exactly one read-only PostgreSQL SQL statement. '\
        'Return only SQL, no markdown, no explanation. '\
        'Use only SELECT or WITH. Never use mutation statements.\n\n'
        f'Schema:\n{schema_summary}\n\n'
        f'Question: {question}'
    )
    response = await client.chat.completions.create(
        model=settings.llm_model,
        temperature=0,
        messages=[
            {'role': 'system', 'content': 'You generate safe read-only PostgreSQL queries.'},
            {'role': 'user', 'content': prompt},
        ],
    )
    sql = (response.choices[0].message.content or '').strip()
    sql = re.sub(r'^```sql\s*', '', sql, flags=re.IGNORECASE)
    sql = re.sub(r'```$', '', sql).strip()
    return sql


def _normalize_sql_for_execution(sql: str, max_rows: int) -> str:
    cleaned = sql.strip().rstrip(';')
    if re.search(r'\blimit\b', cleaned, flags=re.IGNORECASE):
        return cleaned
    return f'{cleaned} LIMIT {max_rows}'


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


async def execute_read_only_sql(db: AsyncSession, sql: str, *, max_rows: int) -> SqlQueryResult:
    guard = evaluate_generated_sql(sql)
    if not guard.allowed:
        return SqlQueryResult(allowed=False, reason=guard.reason, sql=sql)

    executable_sql = _normalize_sql_for_execution(guard.sql or sql, max_rows)
    result = await db.execute(text(executable_sql))
    rows = [
        {key: _json_safe(value) for key, value in row.items()}
        for row in result.mappings().all()
    ]
    columns = list(rows[0].keys()) if rows else []
    return SqlQueryResult(
        allowed=True,
        reason='Read-only SQL executed successfully.',
        sql=executable_sql,
        columns=columns,
        rows=rows,
        row_count=len(rows),
    )
