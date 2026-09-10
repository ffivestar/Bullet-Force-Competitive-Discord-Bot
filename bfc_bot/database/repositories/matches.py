from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from bfc_bot.database.db import Database


@dataclass
class RankedMatch:
    id: int
    creator_discord_id: int
    team_size: int
    required_players: int
    status: str
    map_name: str | None
    game_mode: str
    room_name: str | None
    room_password: str | None
    created_at: str
    started_at: str | None
    completed_at: str | None
    team_one_json: str | None = None
    team_two_json: str | None = None


class MatchRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create_match(self, creator_discord_id: int, team_size: int, status: str, game_mode: str) -> RankedMatch:
        required_players = team_size * 2
        now = datetime.utcnow().isoformat()
        cursor = self.database.execute(
            """
            INSERT INTO ranked_matches (
                creator_discord_id,
                team_size,
                required_players,
                status,
                game_mode,
                created_at,
                started_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (creator_discord_id, team_size, required_players, status, game_mode, now, now),
        )
        match_id = cursor.lastrowid
        return self.get_match(match_id)

    def get_match(self, match_id: int) -> RankedMatch | None:
        row = self.database.fetch_one("SELECT * FROM ranked_matches WHERE id = ?", (match_id,))
        return self._row_to_match(row) if row else None

    def add_participant(self, match_id: int, discord_user_id: int, ign_snapshot: str, team_number: int, joined_at: str) -> None:
        self.database.execute(
            """
            INSERT INTO ranked_match_players (
                match_id,
                discord_user_id,
                ign_snapshot,
                team_number,
                joined_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (match_id, discord_user_id, ign_snapshot, team_number, joined_at),
        )

    def list_participants(self, match_id: int) -> list[dict[str, Any]]:
        rows = self.database.fetch_all(
            "SELECT * FROM ranked_match_players WHERE match_id = ? ORDER BY joined_at ASC",
            (match_id,),
        )
        return [dict(row) for row in rows]

    def remove_participant(self, match_id: int, discord_user_id: int) -> None:
        self.database.execute(
            "DELETE FROM ranked_match_players WHERE match_id = ? AND discord_user_id = ?",
            (match_id, discord_user_id),
        )

    def participant_count(self, match_id: int) -> int:
        row = self.database.fetch_one(
            "SELECT COUNT(*) AS count FROM ranked_match_players WHERE match_id = ?",
            (match_id,),
        )
        return int(row["count"]) if row else 0

    def has_player_in_match(self, match_id: int, discord_user_id: int) -> bool:
        row = self.database.fetch_one(
            "SELECT 1 FROM ranked_match_players WHERE match_id = ? AND discord_user_id = ?",
            (match_id, discord_user_id),
        )
        return row is not None

    def player_in_active_match(self, discord_user_id: int, exclude_match_id: int | None = None) -> bool:
        query = """
            SELECT 1
            FROM ranked_match_players rmp
            JOIN ranked_matches rm ON rm.id = rmp.match_id
            WHERE rmp.discord_user_id = ? AND rm.status IN ('QUEUING', 'GENERATING', 'READY')
        """
        params: list[Any] = [discord_user_id]
        if exclude_match_id is not None:
            query += " AND rm.id != ?"
            params.append(exclude_match_id)
        row = self.database.fetch_one(query, tuple(params))
        return row is not None

    def update_match_status(self, match_id: int, status: str) -> None:
        self.database.execute(
            "UPDATE ranked_matches SET status = ? WHERE id = ?",
            (status, match_id),
        )

    def update_match_result(self, match_id: int, map_name: str, room_name: str, room_password: str, team_1_players: list[int], team_2_players: list[int]) -> None:
        self.database.execute(
            "UPDATE ranked_matches SET map_name = ?, room_name = ?, room_password = ?, team_one_json = ?, team_two_json = ? WHERE id = ?",
            (
                map_name,
                room_name,
                room_password,
                json.dumps(team_1_players),
                json.dumps(team_2_players),
                match_id,
            ),
        )

    def clear_all_matches(self) -> None:
        self.database.execute("DELETE FROM ranked_match_players")
        self.database.execute("DELETE FROM ranked_matches")

    def get_active_matches(self) -> list[RankedMatch]:
        rows = self.database.fetch_all(
            "SELECT * FROM ranked_matches WHERE status IN ('QUEUING', 'GENERATING', 'READY') ORDER BY id ASC"
        )
        return [self._row_to_match(row) for row in rows]

    def _row_to_match(self, row: Any) -> RankedMatch:
        return RankedMatch(
            id=row["id"],
            creator_discord_id=row["creator_discord_id"],
            team_size=row["team_size"],
            required_players=row["required_players"],
            status=row["status"],
            map_name=row["map_name"],
            game_mode=row["game_mode"],
            room_name=row["room_name"],
            room_password=row["room_password"],
            created_at=row["created_at"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            team_one_json=row["team_one_json"],
            team_two_json=row["team_two_json"],
        )
