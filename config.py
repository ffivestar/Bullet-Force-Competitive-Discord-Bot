from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(Path(__file__).parent / ".env")


@dataclass(frozen=True)
class Settings:
    discord_token: str
    database_path: Path
    command_guild_id: int | None
    tournament_category_name: str
    match_results_channel_name: str
    tournament_staff_role_name: str
    bfc_admin_role_name: str
    grand_final_reset_default: bool
    tier_role_names: tuple[str, str, str] = ("Tier 1", "Tier 2", "Tier 3")

    @classmethod
    def from_environment(cls) -> "Settings":
        token = os.getenv("DISCORD_TOKEN", "").strip()
        if not token or token in {"replace_with_your_bot_token", "PASTE_MY_TOKEN_HERE"}:
            raise ValueError("DISCORD_TOKEN is missing. Paste your Discord bot token into .env after DISCORD_TOKEN=.")

        guild_id = os.getenv("COMMAND_GUILD_ID", "").strip()
        database_path = Path(os.getenv("DATABASE_PATH", "data/bfc.sqlite3"))
        if not database_path.is_absolute():
            database_path = Path(__file__).parent / database_path

        return cls(
            discord_token=token,
            tier_role_names=tuple(os.getenv(f"TIER_{i}_ROLE_NAME", f"Tier {i}") for i in (1, 2, 3)),
            database_path=database_path,
            command_guild_id=int(guild_id) if guild_id else None,
            tournament_category_name=os.getenv("TOURNAMENT_CATEGORY_NAME", "BFC Tournaments"),
            match_results_channel_name=os.getenv("MATCH_RESULTS_CHANNEL_NAME", "match-results"),
            tournament_staff_role_name=os.getenv("TOURNAMENT_STAFF_ROLE_NAME", "Tournament Staff"),
            bfc_admin_role_name=os.getenv("BFC_ADMIN_ROLE_NAME", "BFC Admin"),
            grand_final_reset_default=os.getenv("GRAND_FINAL_RESET_DEFAULT", "true").lower() in {"1", "true", "yes"},
        )
