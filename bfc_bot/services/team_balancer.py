from __future__ import annotations

from itertools import combinations


def build_teams(players: list[object], team_size: int) -> list[list[object]]:
    if team_size <= 0:
        raise ValueError("team_size must be positive")

    total_players = len(players)
    if total_players % (team_size * 2) != 0:
        raise ValueError("Player count must fit the chosen format")

    half = total_players // 2
    if half != team_size:
        raise ValueError("Team size does not match the queued player count")

    best_split: list[list[object]] | None = None
    best_score: tuple[int, int] | None = None

    for team_one in combinations(players, team_size):
        team_one_set = set(team_one)
        team_two = [player for player in players if player not in team_one_set]
        if len(team_two) != team_size:
            continue

        team_one_sum = sum(getattr(player, "rating_points", 0) for player in team_one)
        team_two_sum = sum(getattr(player, "rating_points", 0) for player in team_two)
        score = (abs(team_one_sum - team_two_sum), team_one_sum)

        if best_score is None or score < best_score:
            best_score = score
            best_split = [list(team_one), team_two]

    if best_split is None:
        raise ValueError("Unable to generate balanced teams")

    return best_split
