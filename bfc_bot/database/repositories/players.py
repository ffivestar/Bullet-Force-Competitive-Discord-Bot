from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from bfc_bot.database.db import Database
from bfc_bot.ui.embeds import build_profile_embed


@dataclass
class Player:
    discord_user_id: int
    discord_username: str
    ign: str
    rating_points: int = 1000
    matches_played: int = 0
    wins: int = 0
    losses: int = 0
    kills: int = 0
    deaths: int = 0
    created_at: str | None = None
    updated_at: str | None = None

    def profile_embed(self) -> Any:
        return build_profile_embed(self)


class PlayerRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create(self, discord_user_id: int, discord_username: str, ign: str, rating_points: int = 1000) -> Player:
        now = datetime.utcnow().isoformat()
        self.database.execute(
            """
            INSERT INTO players (
                discord_user_id,
                discord_username,
                ign,
                rating_points,
                matches_played,
                wins,
                losses,
                kills,
                deaths,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, 0, 0, 0, 0, 0, ?, ?)
            """,
            (discord_user_id, discord_username, ign, rating_points, now, now),
        )
        return self.get_by_discord_id(discord_user_id)

    def get_by_discord_id(self, discord_user_id: int) -> Player | None:
        row = self.database.fetch_one(
            "SELECT * FROM players WHERE discord_user_id = ?",
            (discord_user_id,),
        )
        return self._row_to_player(row) if row else None

    def exists_ign(self, ign: str, exclude_discord_id: int | None = None) -> bool:
        if exclude_discord_id is None:
            row = self.database.fetch_one("SELECT 1 FROM players WHERE ign = ?", (ign,))
        else:
            row = self.database.fetch_one(
                "SELECT 1 FROM players WHERE ign = ? AND discord_user_id != ?",
                (ign, exclude_discord_id),
            )
        return row is not None

    def update_ign(self, discord_user_id: int, ign: str) -> Player | None:
        now = datetime.utcnow().isoformat()
        self.database.execute(
            "UPDATE players SET ign = ?, updated_at = ? WHERE discord_user_id = ?",
            (ign, now, discord_user_id),
        )
        return self.get_by_discord_id(discord_user_id)

    def rows(self) -> list[Player]:
        return [self._row_to_player(row) for row in self.database.fetch_all("SELECT * FROM players ORDER BY ign ASC")]

    def _row_to_player(self, row: Any) -> Player:
        return Player(
            discord_user_id=row["discord_user_id"],
            discord_username=row["discord_username"],
            ign=row["ign"],
            rating_points=row["rating_points"],
            matches_played=row["matches_played"],
            wins=row["wins"],
            losses=row["losses"],
            kills=row["kills"],
            deaths=row["deaths"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
