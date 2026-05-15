from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


SupportedDatabaseType = Literal['mysql', 'postgresql', 'sqlite', 'supabase']


class DatabaseConnectionInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    db_type: SupportedDatabaseType | None = None
    host: str | None = None
    port: int | None = None
    database: str | None = None
    username: str | None = None
    password: str | None = None
    schema_name: str | None = Field(default=None, alias='schema')
    sqlite_path: str | None = None
    url: str | None = None
    ssl_required: bool | None = None


class DatabaseConnectRequest(BaseModel):
    connection: DatabaseConnectionInput | None = None


class DatabaseTableColumn(BaseModel):
    name: str
    data_type: str


class DatabaseTableSchema(BaseModel):
    name: str
    columns: list[DatabaseTableColumn]


class DatabaseConnectResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    connected: bool
    message: str
    db_type: str | None = None
    database: str | None = None
    schema_name: str | None = Field(default=None, alias='schema')
    tables: list[DatabaseTableSchema] = Field(default_factory=list)
    schema_summary: str | None = None


class DatabaseQueryRequest(BaseModel):
    question: str = Field(min_length=1)
    max_rows: int = Field(default=50, ge=1, le=200)
    thread_id: str | None = None
    connection: DatabaseConnectionInput | None = None


class DatabaseQueryResponse(BaseModel):
    detected_intent: str
    allowed: bool
    message: str
    sql: str | None = None
    explanation: str | None = None
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0
    formatted_table: str | None = None


class SpreadsheetQueryRequest(BaseModel):
    source_id: str = Field(min_length=1, description='Attachment ID, local path, or Google Sheets URL')
    question: str = Field(min_length=1)
    sheet_name: str | None = Field(default=None, description='Sheet name for multi-sheet documents')
    max_rows: int = Field(default=50, ge=1, le=200)
    thread_id: str | None = None


class SpreadsheetQueryResponse(BaseModel):
    source_type: str = Field(default='spreadsheet')
    allowed: bool = True
    message: str
    answer: str
    columns: list[str] = Field(default_factory=list)
    rows_considered: int
    thread_id: str | None = None
