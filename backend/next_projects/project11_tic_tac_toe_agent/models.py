from pydantic import BaseModel, Field


class TicTacToeMoveRequest(BaseModel):
    board: list[str] = Field(min_length=9, max_length=9, description='Current board values: X, O, or empty string')
    user_move: int = Field(ge=0, le=8, description='User move index')
    user_mark: str = Field(default='X', pattern='^[XO]$', description='User mark')
    agent_mark: str = Field(default='O', pattern='^[XO]$', description='Agent mark')
    thread_id: str | None = None


class TicTacToeMoveResponse(BaseModel):
    board: list[str]
    user_move: int
    agent_move: int | None
    status: str
    winner: str | None
    agent_reason: str
    agent_source: str
