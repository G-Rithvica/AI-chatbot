from pydantic import BaseModel, Field


class ResearchDigestQueryRequest(BaseModel):
    query: str = Field(min_length=1, description='Search query for arXiv')
    max_results: int = Field(default=10, ge=1, le=50, description='Maximum number of papers to fetch')
    max_summary_length: int = Field(default=500, ge=100, le=2000, description='Max length of generated digest')
    thread_id: str | None = None


class ResearchPaper(BaseModel):
    title: str
    authors: list[str]
    published: str
    arxiv_id: str
    url: str
    summary: str


class ResearchDigestResponse(BaseModel):
    query: str
    papers_found: int
    digest: str
    papers: list[ResearchPaper]
    thread_id: str | None = None
