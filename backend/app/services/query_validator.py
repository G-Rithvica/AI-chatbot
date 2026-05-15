import re
from dataclasses import dataclass

from app.database.schema_reader import SchemaSnapshot

_DB_QUESTION_KEYWORDS = {
    'show', 'list', 'count', 'counts', 'total', 'sum', 'average', 'avg', 'top', 'highest', 'lowest', 'revenue',
    'sales', 'row', 'rows', 'record', 'records', 'table', 'tables', 'column', 'columns', 'schema',
    'where', 'group', 'order', 'database', 'db', 'query', 'queries', 'sql',
}
_BLOCKED_KEYWORDS = {
    'delete', 'update', 'drop', 'insert', 'alter', 'truncate', 'exec', 'execute', 'call', 'grant', 'revoke',
    'merge', 'replace', 'vacuum', 'pragma', 'attach', 'detach', 'union',
}


@dataclass(frozen=True)
class QueryValidationResult:
    allowed: bool
    reason: str


def detect_database_intent(question: str, schema: SchemaSnapshot) -> bool:
    lowered = question.lower()
    tokens = set(re.findall(r'[a-z0-9_]+', lowered))
    normalized_tokens = set(tokens)
    normalized_tokens.update(token[:-1] for token in tokens if len(token) > 3 and token.endswith('s'))
    normalized_tokens.update(token[:-3] + 'y' for token in tokens if len(token) > 4 and token.endswith('ies'))
    if normalized_tokens & _DB_QUESTION_KEYWORDS:
        return True

    schema_tokens: set[str] = set()
    for table in schema.tables:
        schema_tokens.update(re.findall(r'[a-z0-9_]+', table.name.lower()))
        for column in table.columns:
            schema_tokens.update(re.findall(r'[a-z0-9_]+', column.name.lower()))
    return bool(normalized_tokens & schema_tokens)


def _strip_sql_comments(sql: str) -> str:
    without_block = re.sub(r'/\*.*?\*/', ' ', sql, flags=re.DOTALL)
    return re.sub(r'--.*?$', ' ', without_block, flags=re.MULTILINE)


def _extract_cte_names(sql: str) -> set[str]:
    return {match.group(1).lower() for match in re.finditer(r'\bwith\s+([a-zA-Z_][\w]*)\s+as\b', sql, flags=re.IGNORECASE)}


def _extract_referenced_tables(sql: str) -> set[str]:
    matches = re.findall(r'\b(?:from|join)\s+([a-zA-Z_][\w\.\"]*)', sql, flags=re.IGNORECASE)
    tables: set[str] = set()
    for match in matches:
        cleaned = match.replace('"', '').split('.')[-1].lower()
        if cleaned:
            tables.add(cleaned)
    return tables


def _has_multiple_statements(sql: str) -> bool:
    trimmed = sql.strip().rstrip(';')
    return ';' in trimmed


def normalize_query_limit(sql: str, *, max_rows: int) -> str:
    cleaned = sql.strip().rstrip(';')
    if re.search(r'\blimit\b', cleaned, flags=re.IGNORECASE):
        return cleaned
    return f'{cleaned} LIMIT {max_rows}'


def validate_read_only_sql(sql: str, schema: SchemaSnapshot) -> QueryValidationResult:
    cleaned = _strip_sql_comments(sql).strip()
    lowered = cleaned.lower().rstrip(';')
    if not cleaned:
        return QueryValidationResult(allowed=False, reason='Generated SQL is empty.')
    if _has_multiple_statements(cleaned):
        return QueryValidationResult(allowed=False, reason='Only one SQL statement is allowed.')
    if any(re.search(rf'\b{keyword}\b', lowered) for keyword in _BLOCKED_KEYWORDS):
        return QueryValidationResult(allowed=False, reason='Only read-only SELECT queries are allowed.')
    if not (lowered.startswith('select ') or lowered.startswith('with ')):
        return QueryValidationResult(allowed=False, reason='Query must start with SELECT or WITH.')

    allowed_tables = {name.lower() for name in schema.table_names}
    cte_names = _extract_cte_names(cleaned)
    referenced_tables = _extract_referenced_tables(cleaned)
    unknown_tables = sorted(table for table in referenced_tables if table not in allowed_tables and table not in cte_names)
    if unknown_tables:
        return QueryValidationResult(
            allowed=False,
            reason=f'Query references unknown tables: {", ".join(unknown_tables)}.',
        )

    return QueryValidationResult(allowed=True, reason='Read-only SQL accepted.')
