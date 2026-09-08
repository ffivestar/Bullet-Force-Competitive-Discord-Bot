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
log = logging.getLogger(__name__)


def command_names(commands_list, prefix=""):
    names = []
    for command in commands_list:
        full_name = f"{prefix} {command.name}".strip()
        names.append(full_name)
        children = getattr(command, "commands", ())
        names.extend(command_names(children, full_name))
    return names


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
        for extension in ("cogs.general", "cogs.tournaments"):
            await self.load_extension(extension)
            log.info("Loaded command extension %s", extension)

        if self.settings.command_guild_id:
            guild = discord.Object(id=self.settings.command_guild_id)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            log.info("Synced %d top-level application commands to development guild %s", len(synced), guild.id)
            for name in command_names(synced):
                log.info("Synced application command: /%s", name)
        else:
            synced = await self.tree.sync()
            log.info("Synced %d top-level global application commands", len(synced))
            for name in command_names(synced):
                log.info("Synced global application command: /%s", name)

    async def on_command_error(self, interaction, error):
        cause = getattr(error, "original", error)
        log.error("Application command failed", exc_info=(type(cause), cause, cause.__traceback__))
        message = str(cause) if isinstance(cause, RuleError) else "The action could not finish. Check the bot logs and permissions, then retry."
        try:
            await send_text(interaction, message)
        except Exception:
            log.exception("Unable to acknowledge failed application command")

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
        log.info("Logged in as %s (%s)", self.user, self.user.id if self.user else "unknown")


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
