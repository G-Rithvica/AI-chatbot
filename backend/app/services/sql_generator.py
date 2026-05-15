import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.ai.llm import get_async_openai_client
from app.core.config import get_settings
from app.database.connector import ResolvedDatabaseConfig
from app.database.schema_reader import SchemaSnapshot, TableSchemaInfo


@dataclass(frozen=True)
class GeneratedSql:
    sql: str
    params: dict[str, Any] = field(default_factory=dict)


def _question_tokens(question: str) -> set[str]:
    return set(re.findall(r'[a-z0-9_]+', question.lower()))


def _singular(value: str) -> str:
    if value.endswith('ies'):
        return value[:-3] + 'y'
    if value.endswith('s') and len(value) > 3:
        return value[:-1]
    return value


def _pick_table(question: str, schema: SchemaSnapshot) -> TableSchemaInfo | None:
    lowered = question.lower()
    for table in schema.tables:
        name = table.name.lower()
        if name in lowered or _singular(name) in lowered:
            return table

    tokens = _question_tokens(question)
    scored: list[tuple[int, TableSchemaInfo]] = []
    for table in schema.tables:
        table_tokens = set(re.findall(r'[a-z0-9_]+', table.name.lower()))
        score = len(tokens & table_tokens)
        if score > 0:
            scored.append((score, table))
    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1]


def _pick_column(table: TableSchemaInfo, keywords: tuple[str, ...]) -> str | None:
    for keyword in keywords:
        for column in table.columns:
            if keyword in column.name.lower():
                return column.name
    return None


def _heuristic_sql(question: str, schema: SchemaSnapshot) -> GeneratedSql | None:
    lowered = question.lower()
    table = _pick_table(question, schema)
    if table is None:
        return None

    if 'top ' in lowered and ' by ' in lowered:
        top_match = re.search(r'\btop\s+(\d+)\b', lowered)
        order_match = re.search(r'\bby\s+([a-zA-Z_][\w\s]*)', lowered)
        if top_match and order_match:
            limit = int(top_match.group(1))
            order_phrase = order_match.group(1).strip().split()[0]
            order_column = _pick_column(table, (order_phrase, 'sales', 'revenue', 'amount', 'total'))
            if order_column:
                return GeneratedSql(
                    sql=f'SELECT * FROM {table.name} ORDER BY {order_column} DESC LIMIT {limit}',
                )

    if 'total revenue this month' in lowered or ('total' in lowered and 'revenue' in lowered and 'month' in lowered):
        revenue_table = table if _pick_column(table, ('revenue', 'amount', 'sales', 'total')) else None
        if revenue_table is None:
            for candidate in schema.tables:
                if _pick_column(candidate, ('revenue', 'amount', 'sales', 'total')):
                    revenue_table = candidate
                    break
        if revenue_table:
            metric_column = _pick_column(revenue_table, ('revenue', 'amount', 'sales', 'total'))
            date_column = _pick_column(revenue_table, ('created_at', 'date', 'ordered_at', 'sale_date', 'updated_at'))
            if metric_column and date_column:
                month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                return GeneratedSql(
                    sql=(
                        f'SELECT COALESCE(SUM({metric_column}), 0) AS total_revenue '
                        f'FROM {revenue_table.name} WHERE {date_column} >= :month_start'
                    ),
                    params={'month_start': month_start.isoformat()},
                )

    filter_match = re.search(r'\bfrom\s+([a-zA-Z][\w\- ]*)$', question.strip(), flags=re.IGNORECASE)
    if ('show' in lowered or 'list' in lowered) and filter_match:
        city_column = _pick_column(table, ('city', 'location', 'place'))
        if city_column:
            return GeneratedSql(
                sql=f'SELECT * FROM {table.name} WHERE lower({city_column}) = lower(:filter_value)',
                params={'filter_value': filter_match.group(1).strip()},
            )

    asks_count = 'count' in lowered or 'how many' in lowered
    asks_names = any(keyword in lowered for keyword in ('name', 'names'))
    if asks_count and asks_names:
        name_column = _pick_column(table, ('name', 'full_name', 'username', 'email', 'title'))
        if name_column:
            return GeneratedSql(
                sql=f'SELECT {name_column}, COUNT(*) OVER() AS total_count FROM {table.name} ORDER BY {name_column} ASC',
            )

    if asks_count:
        return GeneratedSql(sql=f'SELECT COUNT(*) AS total_count FROM {table.name}')

    if 'show all' in lowered or 'list all' in lowered:
        return GeneratedSql(sql=f'SELECT * FROM {table.name}')

    return None


async def generate_sql_from_question(
    question: str,
    *,
    config: ResolvedDatabaseConfig,
    schema: SchemaSnapshot,
) -> GeneratedSql:
    heuristic = _heuristic_sql(question, schema)
    if heuristic is not None:
        return heuristic

    settings = get_settings()
    if not settings.llm_model or not settings.litellm_api_key:
        raise ValueError('Unable to generate SQL without an LLM configuration for this question.')

    client = get_async_openai_client()
    prompt = (
        f'You are generating one safe read-only {config.dialect_name} SQL query. '
        'Return only SQL. Never use markdown. Never use DELETE, UPDATE, DROP, INSERT, ALTER, TRUNCATE, EXEC, or UNION. '
        'Use only tables and columns from the provided schema. Prefer LIMIT when applicable.\n\n'
        f'Schema:\n{schema.summary}\n\n'
        f'Question: {question}'
    )
    response = await client.chat.completions.create(
        model=settings.llm_model,
        temperature=0,
        messages=[
            {'role': 'system', 'content': 'You generate safe read-only SQL queries for known schemas only.'},
            {'role': 'user', 'content': prompt},
        ],
    )
    sql = (response.choices[0].message.content or '').strip()
    sql = re.sub(r'^```sql\s*', '', sql, flags=re.IGNORECASE)
    sql = re.sub(r'^```\s*', '', sql)
    sql = re.sub(r'```$', '', sql).strip()
    return GeneratedSql(sql=sql)
