from __future__ import annotations

import random
from typing import Iterable


def build_teams(players: list[object], team_size: int) -> list[list[object]]:
    if team_size <= 0:
        raise ValueError("team_size must be positive")

    shuffled = list(players)
    random.shuffle(shuffled)

    total_players = len(shuffled)
    if total_players % (team_size * 2) != 0:
        raise ValueError("Player count must fit the chosen format")

    half = total_players // 2
    return [shuffled[:half], shuffled[half:]]
