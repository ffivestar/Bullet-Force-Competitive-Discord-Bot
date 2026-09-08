from __future__ import annotations

import asyncio
import logging

import discord
from discord.ext import commands

from config import Settings
from database import Database
from tournament_service import TournamentService


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


class BFCBot(commands.Bot):
    def __init__(self, settings: Settings, database: Database) -> None:
        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)
        self.settings = settings
        self.database = database
        self.tournament_service = TournamentService(database)

    async def setup_hook(self) -> None:
        await self.load_extension("cogs.general")
        await self.load_extension("cogs.tournaments")
        if self.settings.command_guild_id:
            guild = discord.Object(id=self.settings.command_guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

    async def on_ready(self) -> None:
        logging.getLogger(__name__).info("Logged in as %s (%s)", self.user, self.user.id if self.user else "unknown")


async def main() -> None:
    settings = Settings.from_environment()
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
