from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import discord
from discord.ext import commands

from bfc_bot.database.db import Database
from bfc_bot.database.repositories.matches import MatchRepository
from bfc_bot.database.repositories.players import PlayerRepository
from bfc_bot.services.ranked_service import RankedService
from config import Settings


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)


class BFCBot(commands.Bot):
    def __init__(self, settings: Settings, database: Database) -> None:
        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = True
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents, allowed_mentions=discord.AllowedMentions.none())
        self.settings = settings
        self.database = database
        self.player_repo = PlayerRepository(database)
        self.match_repo = MatchRepository(database)
        self.ranked_service = RankedService(self.player_repo, self.match_repo)

    async def setup_hook(self) -> None:
        for extension in ("commands.registration", "commands.ranked"):
            await self.load_extension(extension)
            log.info("Loaded command extension %s", extension)

        if self.settings.command_guild_id:
            guild = discord.Object(id=self.settings.command_guild_id)
            self.tree.copy_global_to(guild=guild)
            self.tree.clear_commands(guild=None)
            synced = await self.tree.sync(guild=guild)
            log.info("Synced %d guild commands to development guild %s", len(synced), guild.id)
        else:
            synced = await self.tree.sync()
            log.info("Synced %d global application commands", len(synced))

    async def on_ready(self) -> None:
        log.info("Logged in as %s", self.user)

    async def close(self) -> None:
        await super().close()


async def main() -> None:
    try:
        settings = Settings.from_environment()
    except ValueError as error:
        logging.getLogger(__name__).error("Configuration error: %s", error)
        return

    database = Database(settings.database_path)
    database.connect()
    bot = BFCBot(settings, database)
    try:
        await bot.start(settings.discord_token)
    finally:
        await bot.close()
        database.close()


if __name__ == "__main__":
    asyncio.run(main())
