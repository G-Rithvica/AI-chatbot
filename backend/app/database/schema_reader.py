from dataclasses import dataclass

from sqlalchemy import inspect, text

from app.database.connector import ResolvedDatabaseConfig, create_database_engine


@dataclass(frozen=True)
class TableColumnInfo:
    name: str
    data_type: str


@dataclass(frozen=True)
class TableSchemaInfo:
    name: str
    columns: list[TableColumnInfo]


@dataclass(frozen=True)
class SchemaSnapshot:
    tables: list[TableSchemaInfo]
    summary: str

    @property
    def table_names(self) -> set[str]:
        return {table.name for table in self.tables}


def _table_names_for_config(inspector, config: ResolvedDatabaseConfig) -> list[str]:
    if config.db_type == 'sqlite':
        return sorted(name for name in inspector.get_table_names() if not name.startswith('sqlite_'))
    schema = config.schema
    return sorted(inspector.get_table_names(schema=schema))


def read_schema_snapshot(
    config: ResolvedDatabaseConfig,
    *,
    max_tables: int = 50,
    max_columns_per_table: int = 50,
) -> SchemaSnapshot:
    engine = create_database_engine(config)
    try:
        with engine.connect() as connection:
            connection.execute(text('SELECT 1'))
            inspector = inspect(connection)
            tables: list[TableSchemaInfo] = []
            for table_name in _table_names_for_config(inspector, config)[:max_tables]:
                raw_columns = inspector.get_columns(table_name, schema=None if config.db_type == 'sqlite' else config.schema)
                columns = [
                    TableColumnInfo(
                        name=str(column.get('name', 'unknown')),
                        data_type=str(column.get('type', 'unknown')),
                    )
                    for column in raw_columns[:max_columns_per_table]
                ]
                tables.append(TableSchemaInfo(name=table_name, columns=columns))

        summary = '\n'.join(
            f"{table.name}: {', '.join(f'{column.name} ({column.data_type})' for column in table.columns)}"
            for table in tables
        )
        return SchemaSnapshot(tables=tables, summary=summary)
    finally:
        engine.dispose()
