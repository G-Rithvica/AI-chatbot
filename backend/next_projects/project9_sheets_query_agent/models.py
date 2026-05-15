from pydantic import BaseModel, Field


class SheetsAgentQueryRequest(BaseModel):
    source_id: str = Field(min_length=1, description='Local .csv/.xlsx path, Google Sheets URL, or spreadsheet key')
    question: str = Field(min_length=1, description='Natural-language question to ask about the tabular data')
    sheet_name: str | None = Field(default=None, description='Worksheet name for Excel/Google Sheets sources')
    max_rows: int = Field(default=200, ge=1, le=2000)


class SheetsAgentQueryResponse(BaseModel):
    source_type: str = Field(default='spreadsheet')
    agent_type: str = Field(default='langchain-pandas')
    answer: str
    rows_considered: int
    columns: list[str] = Field(default_factory=list)
