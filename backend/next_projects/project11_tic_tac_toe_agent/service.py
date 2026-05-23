from __future__ import annotations

import json
from typing import Literal

from app.ai.llm import get_async_openai_client
from app.core.config import get_settings

from .models import TicTacToeMoveRequest, TicTacToeMoveResponse

Mark = Literal['X', 'O']

WIN_LINES: tuple[tuple[int, int, int], ...] = (
    (0, 1, 2),
    (3, 4, 5),
    (6, 7, 8),
    (0, 3, 6),
    (1, 4, 7),
    (2, 5, 8),
    (0, 4, 8),
    (2, 4, 6),
)


class TicTacToeValidationError(ValueError):
    pass


def _normalize_board(board: list[str]) -> list[str]:
    if len(board) != 9:
        raise TicTacToeValidationError('Board must contain exactly 9 cells.')

    normalized: list[str] = []
    for cell in board:
        value = (cell or '').strip().upper()
        if value not in {'', 'X', 'O'}:
            raise TicTacToeValidationError('Board values must be X, O, or empty strings.')
        normalized.append(value)
    return normalized


def _winner(board: list[str]) -> str | None:
    for a, b, c in WIN_LINES:
        if board[a] and board[a] == board[b] == board[c]:
            return board[a]
    return None


def _is_draw(board: list[str]) -> bool:
    return _winner(board) is None and all(cell in {'X', 'O'} for cell in board)


def _available_moves(board: list[str]) -> list[int]:
    return [idx for idx, value in enumerate(board) if value == '']


def _validate_marks(user_mark: str, agent_mark: str) -> tuple[Mark, Mark]:
    normalized_user = user_mark.strip().upper()
    normalized_agent = agent_mark.strip().upper()

    if normalized_user not in {'X', 'O'} or normalized_agent not in {'X', 'O'}:
        raise TicTacToeValidationError('Marks must be X or O.')
    if normalized_user == normalized_agent:
        raise TicTacToeValidationError('User and agent marks must be different.')

    return normalized_user, normalized_agent


def _apply_move(board: list[str], index: int, mark: Mark) -> list[str]:
    if index < 0 or index > 8:
        raise TicTacToeValidationError('Move index must be between 0 and 8.')
    if board[index] != '':
        raise TicTacToeValidationError(f'Cell {index} is already occupied.')

    next_board = board.copy()
    next_board[index] = mark
    return next_board


def _minimax_score(board: list[str], agent_mark: Mark, user_mark: Mark, is_agent_turn: bool) -> int:
    winner = _winner(board)
    if winner == agent_mark:
        return 1
    if winner == user_mark:
        return -1
    if _is_draw(board):
        return 0

    moves = _available_moves(board)
    if is_agent_turn:
        best = -2
        for move in moves:
            candidate = board.copy()
            candidate[move] = agent_mark
            best = max(best, _minimax_score(candidate, agent_mark, user_mark, False))
        return best

    worst = 2
    for move in moves:
        candidate = board.copy()
        candidate[move] = user_mark
        worst = min(worst, _minimax_score(candidate, agent_mark, user_mark, True))
    return worst


def _best_fallback_move(board: list[str], agent_mark: Mark, user_mark: Mark) -> tuple[int, str]:
    legal = _available_moves(board)
    if not legal:
        return -1, 'No legal moves available.'

    ranked: list[tuple[int, int]] = []
    for move in legal:
        candidate = board.copy()
        candidate[move] = agent_mark
        score = _minimax_score(candidate, agent_mark, user_mark, False)
        ranked.append((score, move))

    ranked.sort(key=lambda item: (-item[0], item[1]))
    score, selected_move = ranked[0]
    reason = (
        'Selected with deterministic minimax policy for optimal defense and attack '
        f'(score={score}).'
    )
    return selected_move, reason


def _extract_json_object(text: str) -> dict | None:
    raw = (text or '').strip()
    if not raw:
        return None

    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    start = raw.find('{')
    end = raw.rfind('}')
    if start >= 0 and end > start:
        snippet = raw[start : end + 1]
        try:
            parsed = json.loads(snippet)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return None
    return None


async def _llm_move(
    board: list[str],
    agent_mark: Mark,
    user_mark: Mark,
    legal_moves: list[int],
) -> tuple[int, str] | None:
    settings = get_settings()
    if not settings.llm_model or not settings.litellm_api_key:
        return None

    board_with_indices = [
        {
            'index': idx,
            'value': value or 'EMPTY',
        }
        for idx, value in enumerate(board)
    ]

    client = get_async_openai_client()
    response = await client.chat.completions.create(
        model=settings.llm_model,
        temperature=0.1,
        messages=[
            {
                'role': 'system',
                'content': (
                    'You are an expert Tic Tac Toe agent. Return only strict JSON with keys '
                    '"move" (int index 0-8) and "reason" (short sentence). Choose only from legal moves.'
                ),
            },
            {
                'role': 'user',
                'content': (
                    f'Board: {json.dumps(board_with_indices)}\n'
                    f'Agent mark: {agent_mark}\n'
                    f'User mark: {user_mark}\n'
                    f'Legal moves: {legal_moves}\n'
                    'Choose the best move to maximize win chance and minimize loss risk. '
                    'Return JSON only.'
                ),
            },
        ],
    )

    content = (response.choices[0].message.content or '').strip()
    payload = _extract_json_object(content)
    if not payload:
        return None

    move = payload.get('move')
    reason = str(payload.get('reason') or 'LLM selected this move to improve win probability.').strip()
    if not isinstance(move, int):
        return None
    if move not in legal_moves:
        return None

    return move, reason


def _status_from_winner(winner: str | None, user_mark: Mark, agent_mark: Mark, board: list[str]) -> str:
    if winner == user_mark:
        return 'user_won'
    if winner == agent_mark:
        return 'agent_won'
    if _is_draw(board):
        return 'draw'
    return 'in_progress'


async def play_tic_tac_toe_turn(request: TicTacToeMoveRequest) -> TicTacToeMoveResponse:
    board = _normalize_board(request.board)
    user_mark, agent_mark = _validate_marks(request.user_mark, request.agent_mark)

    existing_winner = _winner(board)
    if existing_winner is not None or _is_draw(board):
        raise TicTacToeValidationError('Game is already finished. Start a new board to continue.')

    board = _apply_move(board, request.user_move, user_mark)

    winner_after_user = _winner(board)
    if winner_after_user or _is_draw(board):
        return TicTacToeMoveResponse(
            board=board,
            user_move=request.user_move,
            agent_move=None,
            status=_status_from_winner(winner_after_user, user_mark, agent_mark, board),
            winner=winner_after_user,
            agent_reason='User move ended the game before agent turn.',
            agent_source='none',
        )

    # Use deterministic minimax for immediate response time on each move.
    agent_move, agent_reason = _best_fallback_move(board, agent_mark, user_mark)
    agent_source = 'fallback'

    if agent_move < 0:
        raise TicTacToeValidationError('No legal move available for agent.')

    board = _apply_move(board, agent_move, agent_mark)
    winner = _winner(board)

    return TicTacToeMoveResponse(
        board=board,
        user_move=request.user_move,
        agent_move=agent_move,
        status=_status_from_winner(winner, user_mark, agent_mark, board),
        winner=winner,
        agent_reason=agent_reason,
        agent_source=agent_source,
    )
