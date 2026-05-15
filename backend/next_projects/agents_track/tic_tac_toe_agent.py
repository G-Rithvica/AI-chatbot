from dataclasses import dataclass


@dataclass
class MoveSuggestion:
    index: int
    reason: str


def suggest_move(board: list[str], mark: str = 'X') -> MoveSuggestion:
    """Simple baseline: choose first empty cell."""
    for idx, value in enumerate(board):
        if value.strip() == '':
            return MoveSuggestion(index=idx, reason=f'First available move selected for {mark}.')
    return MoveSuggestion(index=-1, reason='No legal moves available.')
