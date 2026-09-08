from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from config import Settings
from tournament_service import TournamentService


class TournamentCog(commands.GroupCog, name="tournament"):
    def __init__(self, bot: commands.Bot, service: TournamentService, settings: Settings) -> None:
        super().__init__()
        self.bot = bot
        self.service = service
        self.settings = settings

    @app_commands.command(name="create", description="Create a 3v3 double-elimination tournament.")
    @app_commands.describe(name="Tournament name", grand_final_reset="Allow a bracket reset in the grand final")
    @app_commands.default_permissions(manage_guild=True)
    async def create(self, interaction: discord.Interaction, name: str, grand_final_reset: bool | None = None) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return
        if not name.strip():
            await interaction.response.send_message("Tournament name cannot be empty.", ephemeral=True)
            return
        tournament = self.service.create_tournament(
            name=name,
            guild_id=interaction.guild.id,
            created_by=interaction.user.id,
            grand_final_reset=self.settings.grand_final_reset_default if grand_final_reset is None else grand_final_reset,
        )
        await interaction.response.send_message(
            f"Created tournament **{tournament.name}** (ID `{tournament.id}`) in registration mode.\n"
            "Team registration and bracket generation are the next module to enable.",
        )

    @app_commands.command(name="list", description="List BFC tournaments in this server.")
    async def list_tournaments(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return
        tournaments = self.service.list_tournaments(interaction.guild.id)
        if not tournaments:
            await interaction.response.send_message("No tournaments have been created yet.", ephemeral=True)
            return
        lines = [f"`{item.id}` **{item.name}** - {item.status}" for item in tournaments]
        await interaction.response.send_message("\n".join(lines))

    @app_commands.command(name="view", description="View one tournament and its current matches.")
    @app_commands.describe(tournament_id="The tournament ID shown by /tournament list")
    async def view(self, interaction: discord.Interaction, tournament_id: int) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return
        tournament = self.service.get_tournament(tournament_id, interaction.guild.id)
        if tournament is None:
            await interaction.response.send_message("Tournament not found in this server.", ephemeral=True)
            return
        matches = self.service.get_matches(tournament.id)
        match_text = "No matches generated yet." if not matches else "\n".join(
            f"Match `{match.id}`: {match.bracket} R{match.round_number} M{match.match_number} ({match.status})"
            for match in matches
        )
        await interaction.response.send_message(
            f"**{tournament.name}**\nFormat: `{tournament.format}`\nStatus: `{tournament.status}`\n"
            f"Grand final reset: `{tournament.grand_final_reset}`\n{match_text}"
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TournamentCog(bot, bot.tournament_service, bot.settings))
