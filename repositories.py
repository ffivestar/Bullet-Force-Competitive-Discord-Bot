from __future__ import annotations

from database import Database
from models import Match, Team, Tournament


class TournamentRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create(self, name: str, guild_id: int, created_by: int, grand_final_reset: bool) -> Tournament:
        cursor = self.database.execute(
            "INSERT INTO tournaments (name, guild_id, created_by, grand_final_reset) VALUES (?, ?, ?, ?)",
            (name, guild_id, created_by, int(grand_final_reset)),
        )
        row = self.database.fetch_one("SELECT * FROM tournaments WHERE id = ?", (cursor.lastrowid,))
        assert row is not None
        return Tournament.from_row(row)

    def list_for_guild(self, guild_id: int) -> list[Tournament]:
        rows = self.database.fetch_all("SELECT * FROM tournaments WHERE guild_id = ? ORDER BY created_at DESC", (guild_id,))
        return [Tournament.from_row(row) for row in rows]

    def get(self, tournament_id: int, guild_id: int) -> Tournament | None:
        row = self.database.fetch_one("SELECT * FROM tournaments WHERE id = ? AND guild_id = ?", (tournament_id, guild_id))
        return Tournament.from_row(row) if row else None

    def teams_for(self, tournament_id: int) -> list[Team]:
        rows = self.database.fetch_all("SELECT * FROM teams WHERE tournament_id = ? ORDER BY seed, id", (tournament_id,))
        return [Team.from_row(row) for row in rows]

    def matches_for(self, tournament_id: int) -> list[Match]:
        rows = self.database.fetch_all("SELECT * FROM matches WHERE tournament_id = ? ORDER BY round_number, match_number", (tournament_id,))
        return [Match.from_row(row) for row in rows]
