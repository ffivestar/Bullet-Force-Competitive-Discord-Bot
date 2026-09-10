from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bfc_bot.database.repositories.players import PlayerRepository
from bfc_bot.ui.embeds import build_registration_embed, build_registration_confirm_embed
from bfc_bot.utils.permissions import is_staff_or_admin


class RegistrationCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.player_repo: PlayerRepository | None = getattr(bot, "player_repo", None)

    @app_commands.command(name="register", description="Register your Discord account with your Bullet Force IGN")
    async def register(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("Use this command in a Discord server.", ephemeral=True)
            return

        if self.player_repo is None:
            await interaction.response.send_message("Player repository is not available.", ephemeral=True)
            return

        member = interaction.user
        existing = self.player_repo.get_by_discord_id(member.id)
        if existing is not None:
            await interaction.response.send_message(
                embed=build_registration_confirm_embed(existing.ign, already_registered=True),
                ephemeral=True,
            )
            return

        modal = RegisterIGNModal(self.player_repo, interaction)
        await interaction.response.send_modal(modal)

    @app_commands.command(name="profile", description="Show your registered profile and stats")
    async def profile(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("Use this command in a Discord server.", ephemeral=True)
            return

        if self.player_repo is None:
            await interaction.response.send_message("Player repository is not available.", ephemeral=True)
            return

        player = self.player_repo.get_by_discord_id(interaction.user.id)
        if player is None:
            await interaction.response.send_message(
                embed=build_registration_embed(),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(embed=player.profile_embed(), ephemeral=True)

    @app_commands.command(name="setign", description="Update your registered Bullet Force IGN")
    async def setign(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("Use this command in a Discord server.", ephemeral=True)
            return

        if self.player_repo is None:
            await interaction.response.send_message("Player repository is not available.", ephemeral=True)
            return

        player = self.player_repo.get_by_discord_id(interaction.user.id)
        if player is None:
            await interaction.response.send_message(
                embed=build_registration_embed(),
                ephemeral=True,
            )
            return

        modal = SetIGNModal(self.player_repo, interaction, player)
        await interaction.response.send_modal(modal)


class RegisterIGNModal(discord.ui.Modal, title="Register with BFC"):
    ign = discord.ui.TextInput(
        label="Bullet Force IGN",
        placeholder="PC-5ive",
        min_length=2,
        max_length=50,
    )

    def __init__(self, player_repo: PlayerRepository, interaction: discord.Interaction) -> None:
        super().__init__()
        self.player_repo = player_repo
        self.interaction = interaction

    async def on_submit(self, interaction: discord.Interaction) -> None:
        ign = self.ign.value.strip()
        if not ign:
            await interaction.response.send_message("IGN cannot be empty.", ephemeral=True)
            return

        member = interaction.user
        player = self.player_repo.get_by_discord_id(member.id)
        if player is not None:
            await interaction.response.send_message("You are already registered.", ephemeral=True)
            return

        if self.player_repo.exists_ign(ign):
            await interaction.response.send_message(
                f"That IGN is already registered to another player: {ign}",
                ephemeral=True,
            )
            return

        created = self.player_repo.create(
            discord_user_id=member.id,
            discord_username=member.name,
            ign=ign,
            rating_points=1000,
        )

        guild = interaction.guild
        if guild is not None:
            try:
                member_obj = guild.get_member(member.id)
                if member_obj is not None:
                    await member_obj.edit(nick=ign)
            except Exception:
                pass

        await interaction.response.send_message(
            embed=build_registration_confirm_embed(ign),
            ephemeral=True,
        )


class SetIGNModal(discord.ui.Modal, title="Update your IGN"):
    ign = discord.ui.TextInput(
        label="New Bullet Force IGN",
        placeholder="PC-5ive",
        min_length=2,
        max_length=50,
    )

    def __init__(self, player_repo: PlayerRepository, interaction: discord.Interaction, player: object) -> None:
        super().__init__()
        self.player_repo = player_repo
        self.interaction = interaction
        self.player = player

    async def on_submit(self, interaction: discord.Interaction) -> None:
        ign = self.ign.value.strip()
        if not ign:
            await interaction.response.send_message("IGN cannot be empty.", ephemeral=True)
            return

        if self.player_repo.exists_ign(ign, exclude_discord_id=interaction.user.id):
            await interaction.response.send_message(
                f"That IGN is already registered to another player: {ign}",
                ephemeral=True,
            )
            return

        updated = self.player_repo.update_ign(interaction.user.id, ign)
        guild = interaction.guild
        if guild is not None:
            try:
                member_obj = guild.get_member(interaction.user.id)
                if member_obj is not None:
                    await member_obj.edit(nick=ign)
            except Exception:
                pass

        await interaction.response.send_message(
            embed=build_registration_confirm_embed(ign, updated=True),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RegistrationCog(bot))
