from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.models.user import User

from .models import TicTacToeMoveRequest, TicTacToeMoveResponse
from .service import TicTacToeValidationError, play_tic_tac_toe_turn

router = APIRouter(prefix='/project11/tic-tac-toe-agent', tags=['project11'])


@router.post('/move', response_model=TicTacToeMoveResponse)
async def tic_tac_toe_move(
    payload: TicTacToeMoveRequest,
    _current_user: User = Depends(get_current_user),
) -> TicTacToeMoveResponse:
    try:
        result = await play_tic_tac_toe_turn(payload)

        return result
    except TicTacToeValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
