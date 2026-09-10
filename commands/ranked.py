from __future__ import annotations

import asyncio
import random
from datetime import datetime
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from bfc_bot.database.repositories.matches import MatchRepository
from bfc_bot.database.repositories.players import PlayerRepository
from bfc_bot.services.map_selector import select_map
from bfc_bot.services.ranked_service import RankedService
from bfc_bot.services.team_balancer import build_teams
from bfc_bot.ui.embeds import (
    build_match_ready_embed,
    build_match_status_embed,
    build_matchmaking_embed,
    build_queue_choice_embed,
    build_registration_embed,
)
from bfc_bot.utils.permissions import is_staff_or_admin


class RankedCog(commands.Cog):
    ranked = app_commands.Group(name="ranked", description="Manage ranked matchmaking", guild_only=True)

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.player_repo: PlayerRepository | None = getattr(bot, "player_repo", None)
        self.match_repo: MatchRepository | None = getattr(bot, "match_repo", None)
        self.ranked_service: RankedService | None = getattr(bot, "ranked_service", None)

    @ranked.command(name="start", description="Start a ranked queue")
    async def ranked_start(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("Use this command in a Discord server.", ephemeral=True)
            return

        if self.player_repo is None or self.match_repo is None or self.ranked_service is None:
            await interaction.response.send_message("Ranked services are not available.", ephemeral=True)
            return

        player = self.player_repo.get_by_discord_id(interaction.user.id)
        if player is None:
            await interaction.response.send_message(embed=build_registration_embed(), ephemeral=True)
            return

        await interaction.response.send_message(
            embed=build_queue_choice_embed(),
            view=RankedFormatView(self.bot, self.player_repo, self.match_repo, self.ranked_service),
            ephemeral=False,
        )

    @ranked.command(name="end", description="Finish a READY ranked match")
    async def ranked_end(self, interaction: discord.Interaction, match_id: int) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("Use this command in a Discord server.", ephemeral=True)
            return

        if self.match_repo is None:
            await interaction.response.send_message("Match repository is not available.", ephemeral=True)
            return

        match = self.match_repo.get_match(match_id)
        if match is None:
            await interaction.response.send_message("That ranked match does not exist.", ephemeral=True)
            return

        if match.status != "READY":
            await interaction.response.send_message("Only READY matches can be ended.", ephemeral=True)
            return

        participant = self.match_repo.has_player_in_match(match_id, interaction.user.id)
        if not participant and not is_staff_or_admin(interaction.user):
            await interaction.response.send_message("Only participants or staff can end this match.", ephemeral=True)
            return

        await interaction.response.send_message(
            embed=build_match_status_embed(match_id=match.id, status="READY", message="Confirm that this ranked match is complete."),
            view=RankedEndView(self.match_repo, match.id),
            ephemeral=False,
        )


class RankedFormatView(discord.ui.View):
    def __init__(self, bot: commands.Bot, player_repo: PlayerRepository, match_repo: MatchRepository, ranked_service: RankedService) -> None:
        super().__init__(timeout=180)
        self.bot = bot
        self.player_repo = player_repo
        self.match_repo = match_repo
        self.ranked_service = ranked_service

    @discord.ui.button(label="2v2", style=discord.ButtonStyle.primary)
    async def two_v_two(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._start_match(interaction, 2)

    @discord.ui.button(label="3v3", style=discord.ButtonStyle.primary)
    async def three_v_three(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._start_match(interaction, 3)

    @discord.ui.button(label="4v4", style=discord.ButtonStyle.primary)
    async def four_v_four(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._start_match(interaction, 4)

    @discord.ui.button(label="5v5", style=discord.ButtonStyle.primary)
    async def five_v_five(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._start_match(interaction, 5)

    @discord.ui.button(label="6v6", style=discord.ButtonStyle.primary)
    async def six_v_six(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._start_match(interaction, 6)

    async def _start_match(self, interaction: discord.Interaction, team_size: int) -> None:
        player = self.player_repo.get_by_discord_id(interaction.user.id)
        if player is None:
            await interaction.response.send_message("You must register before joining ranked matches.", ephemeral=True)
            return

        match = self.match_repo.create_match(
            creator_discord_id=interaction.user.id,
            team_size=team_size,
            status="QUEUING",
            game_mode="TDM",
        )

        self.match_repo.add_participant(
            match_id=match.id,
            discord_user_id=interaction.user.id,
            ign_snapshot=player.ign,
            team_number=1,
            joined_at=datetime.utcnow().isoformat(),
        )

        await interaction.response.edit_message(
            embed=build_matchmaking_embed(
                match_id=match.id,
                team_size=team_size,
                players=[player],
                status="QUEUING",
                required_players=team_size * 2,
            ),
            view=RankedQueueView(self.bot, self.player_repo, self.match_repo, self.ranked_service, match.id),
        )


class RankedQueueView(discord.ui.View):
    def __init__(self, bot: commands.Bot, player_repo: PlayerRepository, match_repo: MatchRepository, ranked_service: RankedService, match_id: int) -> None:
        super().__init__(timeout=180)
        self.bot = bot
        self.player_repo = player_repo
        self.match_repo = match_repo
        self.ranked_service = ranked_service
        self.match_id = match_id

    @discord.ui.button(label="Join Match", style=discord.ButtonStyle.success)
    async def join_match(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._handle_join(interaction)

    @discord.ui.button(label="Leave Match", style=discord.ButtonStyle.secondary)
    async def leave_match(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._handle_leave(interaction)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def cancel_match(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._handle_cancel(interaction)

    async def _handle_join(self, interaction: discord.Interaction) -> None:
        player = self.player_repo.get_by_discord_id(interaction.user.id)
        if player is None:
            await interaction.response.send_message("You must register before joining ranked matches.", ephemeral=True)
            return

        match = self.match_repo.get_match(self.match_id)
        if match is None:
            await interaction.response.send_message("This ranked match no longer exists.", ephemeral=True)
            return

        if match.status != "QUEUING":
            await interaction.response.send_message("This match is no longer accepting joins.", ephemeral=True)
            return

        if self.match_repo.player_in_active_match(interaction.user.id, exclude_match_id=self.match_id):
            await interaction.response.send_message("You are already in another active ranked match.", ephemeral=True)
            return

        if self.match_repo.has_player_in_match(self.match_id, interaction.user.id):
            await interaction.response.send_message("You are already in this match.", ephemeral=True)
            return

        if self.match_repo.participant_count(self.match_id) >= match.required_players:
            await interaction.response.send_message("This queue is already full.", ephemeral=True)
            return

        self.match_repo.add_participant(
            match_id=self.match_id,
            discord_user_id=interaction.user.id,
            ign_snapshot=player.ign,
            team_number=1,
            joined_at=datetime.utcnow().isoformat(),
        )

        await self._refresh_embed(interaction)

    async def _handle_leave(self, interaction: discord.Interaction) -> None:
        if self.match_repo.has_player_in_match(self.match_id, interaction.user.id):
            self.match_repo.remove_participant(self.match_id, interaction.user.id)
            await self._refresh_embed(interaction)
            return

        await interaction.response.send_message("You are not in this match.", ephemeral=True)

    async def _handle_cancel(self, interaction: discord.Interaction) -> None:
        match = self.match_repo.get_match(self.match_id)
        if match is None:
            await interaction.response.send_message("This match no longer exists.", ephemeral=True)
            return

        if interaction.user.id != match.creator_discord_id and not is_staff_or_admin(interaction.user):
            await interaction.response.send_message("You do not have permission to cancel this match.", ephemeral=True)
            return

        self.match_repo.update_match_status(self.match_id, "CANCELLED")
        await interaction.response.edit_message(
            embed=build_match_status_embed(match_id=self.match_id, status="CANCELLED", message="This ranked match was cancelled."),
            view=None,
        )

    async def _refresh_embed(self, interaction: discord.Interaction) -> None:
        match = self.match_repo.get_match(self.match_id)
        if match is None:
            await interaction.response.send_message("This ranked match no longer exists.", ephemeral=True)
            return

        participants = self.match_repo.list_participants(self.match_id)
        player_objects = [self.player_repo.get_by_discord_id(p["discord_user_id"]) for p in participants]
        player_objects = [player for player in player_objects if player is not None]
        players_count = len(player_objects)

        if players_count >= match.required_players:
            self.match_repo.update_match_status(self.match_id, "GENERATING")
            await interaction.response.edit_message(
                embed=build_match_status_embed(match_id=match.id, status="GENERATING", message="Match found. Generating teams..."),
                view=None,
            )
            await asyncio.sleep(1)
            await self._finalize_match(interaction)
            return

        await interaction.response.edit_message(
            embed=build_matchmaking_embed(
                match_id=match.id,
                team_size=match.team_size,
                players=player_objects,
                status=match.status,
                required_players=match.required_players,
            ),
            view=RankedQueueView(self.bot, self.player_repo, self.match_repo, self.ranked_service, self.match_id),
        )

    async def _finalize_match(self, interaction: discord.Interaction) -> None:
        match = self.match_repo.get_match(self.match_id)
        if match is None:
            await interaction.response.send_message("This ranked match no longer exists.", ephemeral=True)
            return

        participants = self.match_repo.list_participants(self.match_id)
        players = [self.player_repo.get_by_discord_id(p["discord_user_id"]) for p in participants]
        players = [player for player in players if player is not None]

        if len(players) < match.required_players:
            self.match_repo.update_match_status(self.match_id, "CANCELLED")
            await interaction.response.edit_message(
                embed=build_match_status_embed(match_id=match.id, status="CANCELLED", message="Not enough players remained to start the match."),
                view=None,
            )
            return

        random.shuffle(players)
        teams = build_teams(players, match.team_size)
        map_name = select_map()
        room_name = f"BFC Ranked {match.id}"
        room_password = str(random.randint(10, 99))

        team_one = teams[0]
        team_two = teams[1]

        self.match_repo.update_match_result(
            match_id=self.match_id,
            map_name=map_name,
            room_name=room_name,
            room_password=room_password,
            team_1_players=[player.discord_user_id for player in team_one],
            team_2_players=[player.discord_user_id for player in team_two],
        )
        self.match_repo.update_match_status(self.match_id, "READY")

        await interaction.response.edit_message(
            embed=build_match_ready_embed(
                match_id=match.id,
                team_size=match.team_size,
                map_name=map_name,
                room_name=room_name,
                room_password=room_password,
                team_one=team_one,
                team_two=team_two,
            ),
            view=None,
        )


class RankedEndView(discord.ui.View):
    def __init__(self, match_repo: MatchRepository, match_id: int) -> None:
        super().__init__(timeout=180)
        self.match_repo = match_repo
        self.match_id = match_id

    @discord.ui.button(label="Confirm Completion", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.match_repo.update_match_status(self.match_id, "COMPLETED")
        await interaction.response.edit_message(
            embed=build_match_status_embed(match_id=self.match_id, status="COMPLETED", message="This ranked match has been marked complete."),
            view=None,
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.edit_message(
            embed=build_match_status_embed(match_id=self.match_id, status="READY", message="Match completion was cancelled."),
            view=None,
        )


async def setup(bot: commands.Bot) -> None:
    bot.add_view(RankedFormatView(bot, bot.player_repo, bot.match_repo, bot.ranked_service))
    bot.add_view(RankedQueueView(bot, bot.player_repo, bot.match_repo, bot.ranked_service, 0))
    await bot.add_cog(RankedCog(bot))
