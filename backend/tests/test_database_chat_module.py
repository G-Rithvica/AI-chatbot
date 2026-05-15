import sqlite3

import pytest

from app.database.connector import _normalize_db_type, resolve_database_config
from app.database.schema_reader import read_schema_snapshot
from app.database.tabular_source import TabularSourceError, materialize_tabular_source
from app.schemas.database_chat import DatabaseConnectionInput, DatabaseQueryRequest
from app.services.database_chat_service import answer_database_question
from app.services.query_validator import validate_read_only_sql


def _build_sample_sqlite_db(path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            'CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT, city TEXT, sales INTEGER)'
        )
        conn.execute(
            "INSERT INTO customers (name, city, sales) VALUES ('Asha', 'Hyderabad', 120), ('Kiran', 'Hyderabad', 95), ('Mira', 'Pune', 140)"
        )
        conn.commit()
    finally:
        conn.close()


def test_sql_guard_blocks_union_queries(tmp_path) -> None:
    db_path = tmp_path / 'sample.sqlite'
    _build_sample_sqlite_db(db_path)
    config = resolve_database_config(DatabaseConnectionInput(db_type='sqlite', sqlite_path=str(db_path)))
    schema = read_schema_snapshot(config)

    result = validate_read_only_sql('SELECT name FROM customers UNION SELECT name FROM customers', schema)

    assert result.allowed is False


@pytest.mark.asyncio
async def test_database_query_answers_hyderabad_request(tmp_path) -> None:
    db_path = tmp_path / 'sample.sqlite'
    _build_sample_sqlite_db(db_path)

    result = await answer_database_question(
        DatabaseQueryRequest(
            question='Show all customers from Hyderabad',
            connection=DatabaseConnectionInput(db_type='sqlite', sqlite_path=str(db_path)),
            max_rows=10,
        )
    )

    assert result.allowed is True
    assert result.row_count == 2
    assert result.sql is not None
    assert result.columns == ['id', 'name', 'city', 'sales']
    assert {row['city'] for row in result.rows} == {'Hyderabad'}


@pytest.mark.asyncio
async def test_database_query_answers_table_count_and_names(tmp_path) -> None:
    db_path = tmp_path / 'sample.sqlite'
    _build_sample_sqlite_db(db_path)

    result = await answer_database_question(
        DatabaseQueryRequest(
            question='How many tables are there in my DB and what are their names?',
            connection=DatabaseConnectionInput(db_type='sqlite', sqlite_path=str(db_path)),
            max_rows=50,
        )
    )

    assert result.allowed is True
    assert 'table' in result.message.lower()
    assert result.columns == ['table_name']
    assert any(row['table_name'] == 'customers' for row in result.rows)


@pytest.mark.asyncio
async def test_database_query_counts_rows_for_specific_table(tmp_path) -> None:
    db_path = tmp_path / 'sample.sqlite'
    _build_sample_sqlite_db(db_path)

    result = await answer_database_question(
        DatabaseQueryRequest(
            question='How many customers are there in customers table?',
            connection=DatabaseConnectionInput(db_type='sqlite', sqlite_path=str(db_path)),
            max_rows=50,
        )
    )

    assert result.allowed is True
    assert result.sql is not None
    assert 'count' in result.sql.lower()
    assert 'customers' in result.sql.lower()
    assert result.columns == ['total_count']
    assert result.rows[0]['total_count'] == 3


@pytest.mark.asyncio
async def test_database_query_returns_count_and_names_for_specific_table(tmp_path) -> None:
    db_path = tmp_path / 'sample.sqlite'
    _build_sample_sqlite_db(db_path)

    result = await answer_database_question(
        DatabaseQueryRequest(
            question='How many customers are there in customers table and what are their names?',
            connection=DatabaseConnectionInput(db_type='sqlite', sqlite_path=str(db_path)),
            max_rows=50,
        )
    )

    assert result.allowed is True
    assert result.sql is not None
    assert 'count(*) over() as total_count' in result.sql.lower()
    assert result.columns == ['name', 'total_count']
    assert {row['name'] for row in result.rows} == {'Asha', 'Kiran', 'Mira'}
    assert all(row['total_count'] == 3 for row in result.rows)


def test_schema_reader_lists_tables(tmp_path) -> None:
    db_path = tmp_path / 'sample.sqlite'
    _build_sample_sqlite_db(db_path)
    config = resolve_database_config(DatabaseConnectionInput(db_type='sqlite', sqlite_path=str(db_path)))

    snapshot = read_schema_snapshot(config)

    assert snapshot.tables
    assert snapshot.tables[0].name == 'customers'
    assert any(column.name == 'city' for column in snapshot.tables[0].columns)


def test_materialize_tabular_source_reads_public_csv(monkeypatch, tmp_path) -> None:
    csv_path = tmp_path / 'sample.csv'
    csv_path.write_text('name,city\nAsha,Hyderabad\nMira,Pune\n', encoding='utf-8')

    import pandas as pd
    real_read_csv = pd.read_csv

    def fake_read_csv(url: str):
        assert url == 'https://example.com/sample.csv'
        return real_read_csv(csv_path)

    monkeypatch.setattr(pd, 'read_csv', fake_read_csv)

    sqlite_path, database_name = materialize_tabular_source('https://example.com/sample.csv')

    assert sqlite_path.exists()
    assert database_name.endswith('.sqlite')
    conn = sqlite3.connect(sqlite_path)
    try:
        count = conn.execute('SELECT COUNT(*) FROM sample').fetchone()[0]
    finally:
        conn.close()
    assert count == 2


def test_materialize_tabular_source_reports_private_google_sheet(monkeypatch) -> None:
    import pandas as pd

    def fake_read_csv(url: str):
        raise RuntimeError('401 unauthorized')

    def fake_read_excel(url: str):
        raise RuntimeError('401 unauthorized')

    monkeypatch.setattr(pd, 'read_csv', fake_read_csv)
    monkeypatch.setattr(pd, 'read_excel', fake_read_excel)

    with pytest.raises(TabularSourceError):
        materialize_tabular_source(
            'https://docs.google.com/spreadsheets/d/1PpnjOsdNgd8_k2n7GeddPtVUG5gVtetnuMYj11RiAVw/edit?gid=1904793704#gid=1904793704'
        )


def test_normalize_db_type_accepts_driver_aliases() -> None:
    assert _normalize_db_type('postgresql+asyncpg') == 'postgresql'
    assert _normalize_db_type('postgresql+psycopg2') == 'postgresql'
    assert _normalize_db_type('mysql+pymysql') == 'mysql'
    assert _normalize_db_type('sqlite+aiosqlite') == 'sqlite'


def test_build_url_prefers_dotenv_database_url(monkeypatch, tmp_path) -> None:
    from app.database import connector as connector_module

    db_path = tmp_path / 'dotenv-first.sqlite'
    _build_sample_sqlite_db(db_path)

    monkeypatch.setattr(connector_module, '_read_dotenv_value', lambda key: f'sqlite:///{db_path.as_posix()}' if key == 'DATABASE_URL' else None)

    config = resolve_database_config(DatabaseConnectionInput())

    assert config.db_type == 'sqlite'
    assert config.url.startswith('sqlite:///')


def test_resolve_config_preserves_password_on_async_url_conversion(monkeypatch) -> None:
    from app.database import connector as connector_module
    from sqlalchemy.engine import make_url

    async_url = 'postgresql+asyncpg://postgres.user:abc123@db.example.com:5432/postgres'
    monkeypatch.setattr(connector_module, '_read_dotenv_value', lambda key: async_url if key == 'DATABASE_URL' else None)

    config = resolve_database_config(DatabaseConnectionInput())
    parsed = make_url(config.url)

    assert parsed.drivername == 'postgresql+psycopg2'
    assert parsed.password == 'abc123'
    assert '***' not in config.url