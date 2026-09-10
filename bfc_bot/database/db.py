from __future__ import annotations

import sqlite3
from pathlib import Path


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.connection: sqlite3.Connection | None = None

    def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.executescript(self._schema())
        self.connection.commit()

    def close(self) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def execute(self, query: str, parameters: tuple = ()) -> sqlite3.Cursor:
        if self.connection is None:
            raise RuntimeError("Database is not connected")
        cursor = self.connection.execute(query, parameters)
        self.connection.commit()
        return cursor

    def fetch_one(self, query: str, parameters: tuple = ()) -> sqlite3.Row | None:
        if self.connection is None:
            raise RuntimeError("Database is not connected")
        return self.connection.execute(query, parameters).fetchone()

    def fetch_all(self, query: str, parameters: tuple = ()) -> list[sqlite3.Row]:
        if self.connection is None:
            raise RuntimeError("Database is not connected")
        return list(self.connection.execute(query, parameters).fetchall())

    @staticmethod
    def _schema() -> str:
        return """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS players (
    discord_user_id INTEGER PRIMARY KEY,
    discord_username TEXT NOT NULL,
    ign TEXT NOT NULL UNIQUE,
    rating_points INTEGER NOT NULL DEFAULT 1000,
    matches_played INTEGER NOT NULL DEFAULT 0,
    wins INTEGER NOT NULL DEFAULT 0,
    losses INTEGER NOT NULL DEFAULT 0,
    kills INTEGER NOT NULL DEFAULT 0,
    deaths INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ranked_matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    creator_discord_id INTEGER NOT NULL,
    team_size INTEGER NOT NULL,
    required_players INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'QUEUING',
    map_name TEXT,
    game_mode TEXT NOT NULL DEFAULT 'TDM',
    room_name TEXT,
    room_password TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at TEXT,
    completed_at TEXT,
    team_one_json TEXT,
    team_two_json TEXT
);

CREATE TABLE IF NOT EXISTS ranked_match_players (
    match_id INTEGER NOT NULL,
    discord_user_id INTEGER NOT NULL,
    ign_snapshot TEXT NOT NULL,
    team_number INTEGER NOT NULL DEFAULT 1,
    joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(match_id, discord_user_id),
    FOREIGN KEY(match_id) REFERENCES ranked_matches(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_ranked_match_players_match_id
    ON ranked_match_players(match_id);

CREATE INDEX IF NOT EXISTS idx_ranked_match_players_discord_user_id
    ON ranked_match_players(discord_user_id);
"""
