import pytest

import next_projects.project11_tic_tac_toe_agent.service as project11_service
from next_projects.project11_tic_tac_toe_agent.models import TicTacToeMoveRequest


@pytest.mark.asyncio
async def test_rejects_invalid_user_move_on_occupied_cell() -> None:
    with pytest.raises(project11_service.TicTacToeValidationError, match='already occupied'):
        await project11_service.play_tic_tac_toe_turn(
            TicTacToeMoveRequest(
                board=['X', '', '', '', '', '', '', '', ''],
                user_move=0,
                user_mark='X',
                agent_mark='O',
            )
        )


@pytest.mark.asyncio
async def test_user_can_win_before_agent_turn() -> None:
    result = await project11_service.play_tic_tac_toe_turn(
        TicTacToeMoveRequest(
            board=['X', 'X', '', 'O', 'O', '', '', '', ''],
            user_move=2,
            user_mark='X',
            agent_mark='O',
        )
    )

    assert result.status == 'user_won'
    assert result.winner == 'X'
    assert result.agent_move is None


@pytest.mark.asyncio
async def test_uses_llm_move_when_legal(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _llm_stub(board, agent_mark, user_mark, legal_moves):  # noqa: ANN001
        assert 4 in legal_moves
        return 4, 'Take center for board control.'

    monkeypatch.setattr(project11_service, '_llm_move', _llm_stub)

    result = await project11_service.play_tic_tac_toe_turn(
        TicTacToeMoveRequest(
            board=['X', '', '', '', '', '', '', '', ''],
            user_move=8,
            user_mark='X',
            agent_mark='O',
        )
    )

    assert result.agent_move == 4
    assert result.agent_source == 'llm'
    assert 'center' in result.agent_reason.lower()


@pytest.mark.asyncio
async def test_falls_back_when_llm_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _llm_none(board, agent_mark, user_mark, legal_moves):  # noqa: ANN001
        return None

    monkeypatch.setattr(project11_service, '_llm_move', _llm_none)

    result = await project11_service.play_tic_tac_toe_turn(
        TicTacToeMoveRequest(
            board=['X', '', '', '', '', '', '', '', ''],
            user_move=1,
            user_mark='X',
            agent_mark='O',
        )
    )

    assert result.agent_move is not None
    assert result.agent_source == 'fallback'
    assert result.status in {'in_progress', 'draw', 'agent_won'}
