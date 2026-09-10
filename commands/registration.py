from __future__ import annotations

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from bfc_bot.database.repositories.players import PlayerRepository
from bfc_bot.ui.embeds import build_registration_embed, build_registration_confirm_embed
from bfc_bot.utils.permissions import is_staff_or_admin
from bfc_bot.utils.rank_sync import RANK_ROLE_NAMES, sync_member_rank

log = logging.getLogger(__name__)


async def _sync_member_nickname(interaction: discord.Interaction, nickname: str | None) -> bool:
    guild = interaction.guild
    if guild is None:
        return False

    me = guild.me
    if me is None:
        log.warning("Guild member data unavailable for guild %s; nickname sync skipped.", guild.id)
        return False

    if not me.guild_permissions.manage_nicknames:
        log.warning("Bot lacks Manage Nicknames permission in guild %s; nickname sync skipped.", guild.id)
        return False

    try:
        member_obj = interaction.user if isinstance(interaction.user, discord.Member) else None
        if member_obj is None:
            member_obj = guild.get_member(interaction.user.id)
        if member_obj is None:
            member_obj = await guild.fetch_member(interaction.user.id)

        await member_obj.edit(nick=nickname)
        return True
    except discord.Forbidden:
        log.warning("Bot lacks permission to edit nicknames for user %s in guild %s.", interaction.user.id, guild.id)
        return False
    except (discord.HTTPException, discord.NotFound) as exc:
        log.warning("Nickname sync failed for user %s in guild %s: %s", interaction.user.id, guild.id, exc)
        return False


async def _clear_member_rank_roles(interaction: discord.Interaction) -> bool:
    guild = interaction.guild
    if guild is None:
        return False

    me = guild.me
    if me is None:
        log.warning("Guild member data unavailable for guild %s; rank role removal skipped.", guild.id)
        return False

    if not me.guild_permissions.manage_roles:
        log.warning("Bot lacks Manage Roles permission in guild %s; rank role removal skipped.", guild.id)
        return False

    try:
        member_obj = interaction.user if isinstance(interaction.user, discord.Member) else None
        if member_obj is None:
            member_obj = guild.get_member(interaction.user.id)
        if member_obj is None:
            member_obj = await guild.fetch_member(interaction.user.id)

        roles_to_remove = [role for role in member_obj.roles if role.name in RANK_ROLE_NAMES]
        if roles_to_remove:
            await member_obj.remove_roles(*roles_to_remove, reason="Removing ranked roles during unregister")
        return True
    except discord.Forbidden:
        log.warning("Bot lacks permission to remove ranked roles for user %s in guild %s.", interaction.user.id, guild.id)
        return False
    except (discord.HTTPException, discord.NotFound) as exc:
        log.warning("Rank role removal failed for user %s in guild %s: %s", interaction.user.id, guild.id, exc)
        return False


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

    @app_commands.command(name="profile", description="Show a registered profile and stats")
    @app_commands.describe(discord_user="Optional player whose profile you want to view")
    async def profile(self, interaction: discord.Interaction, discord_user: Optional[discord.User] = None) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("Use this command in a Discord server.", ephemeral=True)
            return

        if self.player_repo is None:
            await interaction.response.send_message("Player repository is not available.", ephemeral=True)
            return

        target_user = discord_user or interaction.user
        player = self.player_repo.get_by_discord_id(target_user.id)
        if player is None:
            if target_user.id == interaction.user.id:
                await interaction.response.send_message(embed=build_registration_embed())
            else:
                await interaction.response.send_message(f"{target_user.mention} is not registered with the ranked bot yet.")
            return

        await interaction.response.send_message(embed=player.profile_embed())

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

    @app_commands.command(name="unregister", description="Remove your registration and clear your server nickname")
    async def unregister(self, interaction: discord.Interaction) -> None:
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

        deleted = self.player_repo.delete(interaction.user.id)
        nickname_updated = await _sync_member_nickname(interaction, None)
        roles_cleared = await _clear_member_rank_roles(interaction)

        if deleted:
            message = "Your registration has been removed."
            if nickname_updated:
                message += " Your server nickname has been cleared."
            else:
                message += " I could not clear your server nickname because the bot is missing the Manage Nicknames permission or is blocked by role hierarchy."
            if roles_cleared:
                message += " Your ranked roles were removed."
            else:
                message += " I could not remove your ranked roles because the bot is missing the Manage Roles permission or is blocked by role hierarchy."
            await interaction.response.send_message(message, ephemeral=True)
        else:
            await interaction.response.send_message("You are not currently registered.", ephemeral=True)


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
        await interaction.response.defer(ephemeral=True)

        ign = self.ign.value.strip()
        if not ign:
            await interaction.followup.send_message("IGN cannot be empty.", ephemeral=True)
            return

        member = interaction.user
        player = self.player_repo.get_by_discord_id(member.id)
        if player is not None:
            await interaction.followup.send_message("You are already registered.", ephemeral=True)
            return

        if self.player_repo.exists_ign(ign):
            await interaction.followup.send_message(
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

        nickname_updated = await _sync_member_nickname(interaction, ign)

        if interaction.guild is not None:
            try:
                await sync_member_rank(interaction, created, previous_rating=1000, send_rank_up_message=False)
            except Exception as exc:
                log.warning("Profile sync after registration failed for %s: %s", member.id, exc)

        await interaction.followup.send_message(
            embed=build_registration_confirm_embed(ign, nickname_sync_failed=not nickname_updated),
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
        await interaction.response.defer(ephemeral=True)

        ign = self.ign.value.strip()
        if not ign:
            await interaction.followup.send_message("IGN cannot be empty.", ephemeral=True)
            return

        if self.player_repo.exists_ign(ign, exclude_discord_id=interaction.user.id):
            await interaction.followup.send_message(
                f"That IGN is already registered to another player: {ign}",
                ephemeral=True,
            )
            return

        updated = self.player_repo.update_ign(interaction.user.id, ign)
        nickname_updated = await _sync_member_nickname(interaction, ign)

        if interaction.guild is not None and updated is not None:
            try:
                await sync_member_rank(
                    interaction,
                    updated,
                    previous_rating=self.player.rating_points,
                    send_rank_up_message=False,
                    target_user_id=interaction.user.id,
                )
            except Exception as exc:
                log.warning("Profile sync after IGN update failed for %s: %s", interaction.user.id, exc)

        await interaction.followup.send_message(
            embed=build_registration_confirm_embed(ign, updated=True, nickname_sync_failed=not nickname_updated),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RegistrationCog(bot))
