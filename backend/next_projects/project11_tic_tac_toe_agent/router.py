from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.services.chat_service import save_message
from app.services.thread_service import auto_name_thread, get_thread

from .models import TicTacToeMoveRequest, TicTacToeMoveResponse
from .service import TicTacToeValidationError, play_tic_tac_toe_turn

router = APIRouter(prefix='/project11/tic-tac-toe-agent', tags=['project11'])


def _render_board(board: list[str]) -> str:
    rows = [board[0:3], board[3:6], board[6:9]]
    return '\n'.join(' | '.join(cell or ' ' for cell in row) for row in rows)


def _winner_name(winner: str | None, user_name: str, user_mark: str, agent_mark: str) -> str:
    normalized_winner = (winner or '').upper()
    if normalized_winner == user_mark.upper():
        return user_name
    if normalized_winner == agent_mark.upper():
        return 'Agent'
    return 'None'


@router.post('/move', response_model=TicTacToeMoveResponse)
async def tic_tac_toe_move(
    payload: TicTacToeMoveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TicTacToeMoveResponse:
    try:
        result = await play_tic_tac_toe_turn(payload)

        if payload.thread_id:
            thread = await get_thread(db, payload.thread_id, current_user.id)
            if not thread:
                raise HTTPException(status_code=404, detail='Thread not found.')

            if thread.name == 'New Chat':
                await auto_name_thread(db, thread, 'Project 11 Tic Tac Toe')

            user_display = (current_user.name or current_user.email.split('@')[0]).strip() or 'User'
            await save_message(
                db,
                current_user.id,
                'user',
                f'Project 11 Move: {user_display} placed {payload.user_mark.upper()} in tile {payload.user_move + 1}.',
                payload.thread_id,
            )

            outcome = (
                'Round in progress.'
                if result.status == 'in_progress'
                else f'Round complete. Winner: {_winner_name(result.winner, user_display, payload.user_mark, payload.agent_mark)}.'
            )
            agent_tile = 'none' if result.agent_move is None else str(result.agent_move + 1)
            assistant_lines = [
                'Project 11 Update',
                f'Status: {result.status}',
                f'Agent tile: {agent_tile}',
                f'Decision source: {result.agent_source}',
                f'Reason: {result.agent_reason}',
                outcome,
                '',
                'Board:',
                '```',
                _render_board(result.board),
                '```',
            ]
            await save_message(
                db,
                current_user.id,
                'assistant',
                '\n'.join(assistant_lines),
                payload.thread_id,
            )

        return result
    except TicTacToeValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
