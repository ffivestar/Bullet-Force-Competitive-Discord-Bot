from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bfc_bot.database.repositories.matches import MatchRepository
from bfc_bot.database.repositories.players import PlayerRepository


@dataclass
class RankedService:
    player_repo: PlayerRepository
    match_repo: MatchRepository

    def can_join_queue(self, discord_user_id: int, match_id: int) -> bool:
        return not self.match_repo.player_in_active_match(discord_user_id, exclude_match_id=match_id)
