from next_projects.agents_track.tic_tac_toe_agent import suggest_move
from next_projects.project8_data_qa.sql_guard import evaluate_generated_sql


def test_tic_tac_toe_suggest_move_returns_legal_index() -> None:
    move = suggest_move(['', 'O', 'X', '', '', '', '', '', ''])
    assert move.index in {0, 3, 4, 5, 6, 7, 8}


def test_sql_guard_blocks_mutation() -> None:
    blocked = evaluate_generated_sql('DELETE FROM users')
    allowed = evaluate_generated_sql('SELECT * FROM users')
    assert blocked.allowed is False
    assert allowed.allowed is True
