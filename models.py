from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Tournament:
    id: int
    name: str
    guild_id: int
    status: str
    format: str
    grand_final_reset: bool

    @classmethod
    def from_row(cls, row: Any) -> "Tournament":
        return cls(row["id"], row["name"], row["guild_id"], row["status"], row["format"], bool(row["grand_final_reset"]))


@dataclass(frozen=True)
class Team:
    id: int
    tournament_id: int
    name: str
    seed: int | None
    losses: int
    eliminated: bool

    @classmethod
    def from_row(cls, row: Any) -> "Team":
        return cls(row["id"], row["tournament_id"], row["name"], row["seed"], row["losses"], bool(row["eliminated"]))


@dataclass(frozen=True)
class Match:
    id: int
    tournament_id: int
    bracket: str
    round_number: int
    match_number: int
    status: str
    team_a_id: int | None
    team_b_id: int | None

    @classmethod
    def from_row(cls, row: Any) -> "Match":
        return cls(row["id"], row["tournament_id"], row["bracket"], row["round_number"], row["match_number"], row["status"], row["team_a_id"], row["team_b_id"])
