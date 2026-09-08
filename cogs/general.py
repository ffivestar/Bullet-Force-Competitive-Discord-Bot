from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands


class GeneralCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="ping", description="Check whether the BFC bot is online.")
    async def ping(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(f"Pong. `{round(self.bot.latency * 1000)} ms`", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GeneralCog(bot))
