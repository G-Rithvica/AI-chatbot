from pydantic import BaseModel, Field


class RagIngestRequest(BaseModel):
    document_id: str = Field(min_length=1)
    source_name: str = Field(min_length=1)
    content: str = Field(min_length=1)


class RagQueryRequest(BaseModel):
    document_id: str | None = Field(default=None)
    question: str = Field(min_length=1)
    top_k: int = Field(default=4, ge=1, le=20)


class RagPdfIngestResponse(BaseModel):
    document_id: str
    source_name: str
    chunk_count: int


class RagChatRequest(BaseModel):
    document_id: str | None = Field(default=None)
    question: str = Field(min_length=1)
    top_k: int = Field(default=4, ge=1, le=20)


class RagCitation(BaseModel):
    document_id: str
    chunk_id: str
    snippet: str
    source_name: str | None = None
    page_number: int | None = None


class RagAnswer(BaseModel):
    answer: str
    citations: list[RagCitation]
