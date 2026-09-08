from __future__ import annotations

from database import Database
from models import Match, Tournament
from repositories import TournamentRepository


class TournamentService:
    """Legacy foundation API. The active tournament workflow uses engine.py and store.py."""

    def __init__(self, database: Database) -> None:
        self.repository = TournamentRepository(database)

    def create_tournament(self, name: str, guild_id: int, created_by: int, grand_final_reset: bool) -> Tournament:
        return self.repository.create(name.strip(), guild_id, created_by, grand_final_reset)

    def list_tournaments(self, guild_id: int) -> list[Tournament]:
        return self.repository.list_for_guild(guild_id)

    def get_tournament(self, tournament_id: int, guild_id: int) -> Tournament | None:
        return self.repository.get(tournament_id, guild_id)

    def get_matches(self, tournament_id: int) -> list[Match]:
        return self.repository.matches_for(tournament_id)
