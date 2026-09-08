from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS tournaments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    guild_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'registration',
    format TEXT NOT NULL DEFAULT '3v3_double_elimination',
    grand_final_reset INTEGER NOT NULL DEFAULT 1,
    created_by INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id INTEGER NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    seed INTEGER,
    losses INTEGER NOT NULL DEFAULT 0,
    eliminated INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tournament_id, name)
);

CREATE TABLE IF NOT EXISTS team_members (
    team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL,
    display_name TEXT NOT NULL,
    tier INTEGER,
    PRIMARY KEY(team_id, user_id),
    UNIQUE(user_id, team_id)
);

CREATE TABLE IF NOT EXISTS matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id INTEGER NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
    bracket TEXT NOT NULL,
    round_number INTEGER NOT NULL,
    match_number INTEGER NOT NULL,
    team_a_id INTEGER REFERENCES teams(id),
    team_b_id INTEGER REFERENCES teams(id),
    winner_team_id INTEGER REFERENCES teams(id),
    loser_team_id INTEGER REFERENCES teams(id),
    status TEXT NOT NULL DEFAULT 'pending',
    score_a INTEGER,
    score_b INTEGER,
    channel_id INTEGER,
    team_a_voice_id INTEGER,
    team_b_voice_id INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT,
    UNIQUE(tournament_id, bracket, round_number, match_number)
);

CREATE TABLE IF NOT EXISTS match_player_stats (
    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    team_id INTEGER NOT NULL REFERENCES teams(id),
    user_id INTEGER NOT NULL,
    kills INTEGER NOT NULL CHECK(kills >= 0),
    deaths INTEGER NOT NULL CHECK(deaths >= 0),
    kd REAL NOT NULL,
    is_top_frag INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(match_id, user_id)
);

CREATE TABLE IF NOT EXISTS result_revisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    previous_result_json TEXT NOT NULL,
    corrected_by INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.connection: sqlite3.Connection | None = None

    def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.executescript(SCHEMA)
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
