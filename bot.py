from __future__ import annotations

import asyncio
import logging

import discord
from discord.ext import commands

from config import Settings
from database import Database
from engine import RuleError
from presentation import send_text


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


class BFCBot(commands.Bot):
    def __init__(self, settings: Settings, database: Database) -> None:
        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = True
        super().__init__(command_prefix="!", intents=intents, allowed_mentions=discord.AllowedMentions.none())
        self.settings = settings
        self.database = database
        self.tree.on_error = self.on_command_error

    async def setup_hook(self) -> None:
        await self.load_extension("cogs.general")
        await self.load_extension("cogs.tournaments")
        if self.settings.command_guild_id:
            guild = discord.Object(id=self.settings.command_guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

    async def on_command_error(self, interaction, error):
        cause = getattr(error, "original", error)
        if isinstance(cause, RuleError):
            await send_text(interaction, str(cause))
        else:
            logging.getLogger(__name__).error("Command failed", exc_info=(type(cause), cause, cause.__traceback__))
            await send_text(interaction, "The action could not finish. Check the bot logs and permissions, then retry. Saved results are retained.")

    async def close(self):
        cog = self.get_cog("TournamentCog")
        if cog:
            cog.reconcile.cancel()
            task = cog.reconcile.get_task()
            if task:
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        await super().close()

    async def on_ready(self) -> None:
        logging.getLogger(__name__).info("Logged in as %s (%s)", self.user, self.user.id if self.user else "unknown")


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
