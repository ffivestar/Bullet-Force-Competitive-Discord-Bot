from __future__ import annotations

import asyncio
import json
import logging
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
from bfc_bot.utils.rank_sync import get_rank_for_rating, sync_member_rank

log = logging.getLogger(__name__)


class RankedCog(commands.Cog):
    ranked = app_commands.Group(name="ranked", description="Manage ranked matchmaking", guild_only=True)

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.player_repo: PlayerRepository | None = getattr(bot, "player_repo", None)
        self.match_repo: MatchRepository | None = getattr(bot, "match_repo", None)
        self.ranked_service: RankedService | None = getattr(bot, "ranked_service", None)

    def _is_bot_owner(self, interaction: discord.Interaction) -> bool:
        owner = getattr(self.bot.application, "owner", None)
        return owner is not None and interaction.user.id == owner.id

    def _owner_denied_message(self) -> str:
        return "You do not have permission to execute this command."

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

        if self.match_repo is None or self.player_repo is None:
            await interaction.response.send_message("Ranked services are not available.", ephemeral=True)
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

        self.match_repo.update_match_status(match_id, "COMPLETED")
        await interaction.response.send_message(
            f"Marked match #{match_id} as complete. Use `/ranked record-result` to log player stats for the registered players.",
            ephemeral=True,
        )

    @ranked.command(name="wipe", description="Wipe ranked match history and reset all player stats (owner only)")
    async def ranked_wipe(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("Use this command in a Discord server.", ephemeral=True)
            return

        if self.match_repo is None or self.player_repo is None:
            await interaction.response.send_message("Ranked services are not available.", ephemeral=True)
            return

        if not self._is_bot_owner(interaction):
            await interaction.response.send_message(self._owner_denied_message(), ephemeral=True)
            return

        await interaction.response.send_message(
            "This will permanently delete all ranked match history and reset every registered player back to their default stats."
            "\n\nDo you want to continue?",
            view=RankedWipeConfirmView(self.match_repo, self.player_repo),
            ephemeral=True,
        )

    @ranked.command(name="edit-stats", description="Edit a registered player's stats completely (owner only)")
    @app_commands.describe(
        discord_user="Registered player to update",
        matches_played="Total matches played",
        wins="Total wins",
        losses="Total losses",
        kills="Total kills",
        deaths="Total deaths",
        rating_points="Total rating points",
    )
    async def ranked_edit_stats(
        self,
        interaction: discord.Interaction,
        discord_user: discord.User,
        matches_played: int,
        wins: int,
        losses: int,
        kills: int,
        deaths: int,
        rating_points: int,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("Use this command in a Discord server.", ephemeral=True)
            return

        if self.player_repo is None:
            await interaction.response.send_message("Player repository is not available.", ephemeral=True)
            return

        if not self._is_bot_owner(interaction):
            await interaction.response.send_message(self._owner_denied_message(), ephemeral=True)
            return

        player = self.player_repo.get_by_discord_id(discord_user.id)
        if player is None:
            await interaction.response.send_message("That Discord user is not registered in the ranked bot.", ephemeral=True)
            return

        await interaction.response.send_message(
            f"You are about to fully overwrite {player.ign}'s ranked stats with:\n"
            f"- Matches Played: {matches_played}\n"
            f"- Wins: {wins}\n"
            f"- Losses: {losses}\n"
            f"- Kills: {kills}\n"
            f"- Deaths: {deaths}\n"
            f"- Rating Points: {rating_points}\n\n"
            "Do you want to save this full profile update?",
            view=RankedEditStatsConfirmView(
                player_repo=self.player_repo,
                discord_user_id=discord_user.id,
                matches_played=matches_played,
                wins=wins,
                losses=losses,
                kills=kills,
                deaths=deaths,
                rating_points=rating_points,
            ),
            ephemeral=True,
        )

    @ranked.command(name="record-result", description="Review and publish a completed ranked match result by match ID")
    @app_commands.describe(
        match_id="The ranked match ID to review",
        winner_team="Which team won the match? Use 1 or 2.",
        winner_top_frag="Optional top fragger on the winning team",
        loser_top_frag="Optional top fragger on the losing team",
    )
    async def ranked_record_result(
        self,
        interaction: discord.Interaction,
        match_id: int,
        winner_team: int,
        winner_top_frag: discord.User | None = None,
        loser_top_frag: discord.User | None = None,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("Use this command in a Discord server.", ephemeral=True)
            return

        if self.player_repo is None or self.match_repo is None:
            await interaction.response.send_message("Ranked services are not available.", ephemeral=True)
            return

        if not self._is_bot_owner(interaction):
            await interaction.response.send_message(self._owner_denied_message(), ephemeral=True)
            return

        if winner_team not in (1, 2):
            await interaction.response.send_message("winner_team must be either 1 or 2.", ephemeral=True)
            return

        match = self.match_repo.get_match(match_id)
        if match is None:
            await interaction.response.send_message("That ranked match does not exist.", ephemeral=True)
            return

        participants = self.match_repo.list_participants(match_id)
        if not participants:
            await interaction.response.send_message("That ranked match has no participants to review.", ephemeral=True)
            return

        team_one_ids = json.loads(match.team_one_json or "[]") if match.team_one_json else []
        team_two_ids = json.loads(match.team_two_json or "[]") if match.team_two_json else []

        summary_lines = [
            f"Match #{match_id} review",
            f"Format: {match.team_size}v{match.team_size}",
            f"Map: {match.map_name or 'Unknown'}",
            f"Room: {match.room_name or 'Unknown'}",
            f"Winner: Team {winner_team}",
            "Participants:",
        ]

        for participant in participants:
            player = self.player_repo.get_by_discord_id(participant["discord_user_id"])
            if player is None:
                continue

            team_prefix = "Team 1" if participant["discord_user_id"] in team_one_ids else "Team 2"
            summary_lines.append(
                f"• {team_prefix} — {player.ign} — {player.rating_points} ELO — {get_rank_for_rating(player.rating_points)}"
            )

        summary_lines.append("\nThis review is ready to be posted publicly for the affected players.")

        await interaction.response.send_message(
            "\n".join(summary_lines),
            view=RankedRecordResultConfirmView(
                player_repo=self.player_repo,
                match_repo=self.match_repo,
                match_id=match_id,
                winner_team=winner_team,
                winner_top_frag_id=winner_top_frag.id if winner_top_frag is not None else None,
                loser_top_frag_id=loser_top_frag.id if loser_top_frag is not None else None,
            ),
            ephemeral=True,
        )


class RankedWipeConfirmView(discord.ui.View):
    def __init__(self, match_repo: MatchRepository, player_repo: PlayerRepository) -> None:
        super().__init__(timeout=180)
        self.match_repo = match_repo
        self.player_repo = player_repo

    @discord.ui.button(label="Confirm Wipe", style=discord.ButtonStyle.danger)
    async def confirm_wipe(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.match_repo.clear_all_matches()
        self.player_repo.reset_all_stats()

        await interaction.response.send_message(
            "Wiped all ranked match data and reset all player stats back to the default profile state.",
            ephemeral=True,
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_wipe(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_message("Wipe cancelled. No ranked data was changed.", ephemeral=True)


class RankedRecordResultConfirmView(discord.ui.View):
    def __init__(
        self,
        player_repo: PlayerRepository,
        match_repo: MatchRepository,
        match_id: int,
        winner_team: int,
        winner_top_frag_id: int | None = None,
        loser_top_frag_id: int | None = None,
    ) -> None:
        super().__init__(timeout=180)
        self.player_repo = player_repo
        self.match_repo = match_repo
        self.match_id = match_id
        self.winner_team = winner_team
        self.winner_top_frag_id = winner_top_frag_id
        self.loser_top_frag_id = loser_top_frag_id

    @discord.ui.button(label="Post Public Review", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        try:
            match = self.match_repo.get_match(self.match_id)
            if match is None:
                await interaction.response.send_message("That ranked match no longer exists.", ephemeral=True)
                return

            participants = self.match_repo.list_participants(self.match_id)
            if not participants:
                await interaction.response.send_message("That ranked match has no participants to review.", ephemeral=True)
                return

            team_one_ids = json.loads(match.team_one_json or "[]") if match.team_one_json else []
            team_two_ids = json.loads(match.team_two_json or "[]") if match.team_two_json else []

            lines = [
                f"@everyone Ranked match #{self.match_id} has been reviewed.",
                f"Format: {match.team_size}v{match.team_size}",
                f"Map: {match.map_name or 'Unknown'}",
                f"Room: {match.room_name or 'Unknown'}",
                f"Winner: Team {self.winner_team}",
            ]
            if self.winner_top_frag_id is not None:
                lines.append(f"Winning team top fragger: <@{self.winner_top_frag_id}>")
            if self.loser_top_frag_id is not None:
                lines.append(f"Losing team top fragger: <@{self.loser_top_frag_id}>")
            lines.extend(["", "Result summary:"])

            previous_ratings: dict[int, int] = {}
            updated_players: list[tuple[object, int, int, str]] = []

            for participant in participants:
                player = self.player_repo.get_by_discord_id(participant["discord_user_id"])
                if player is None:
                    continue

                team_number = 1 if participant["discord_user_id"] in team_one_ids else 2
                previous_ratings[player.discord_user_id] = player.rating_points
                base_delta = 25 if team_number == self.winner_team else -25
                extra_delta = 10 if player.discord_user_id in {self.winner_top_frag_id, self.loser_top_frag_id} else 0
                delta = base_delta + extra_delta if team_number == self.winner_team else base_delta - extra_delta
                updated = self.player_repo.apply_rating_delta(player.discord_user_id, delta)

                if updated is not None:
                    updated_players.append(
                        (
                            player,
                            previous_ratings[player.discord_user_id],
                            updated.rating_points,
                            get_rank_for_rating(updated.rating_points),
                        )
                    )

                    try:
                        await sync_member_rank(
                            interaction,
                            updated,
                            previous_rating=previous_ratings[player.discord_user_id],
                            send_rank_up_message=True,
                            target_user_id=player.discord_user_id,
                        )
                    except Exception as sync_error:
                        log.warning("Rank sync after match result failed for %s: %s", player.discord_user_id, sync_error)

            self.match_repo.update_match_status(self.match_id, "COMPLETED")

            for player, old_rating, new_rating, rank in updated_players:
                old_rank = get_rank_for_rating(old_rating)
                change = new_rating - old_rating
                lines.append(
                    f"• <@{player.discord_user_id}> — {player.ign} — {old_rating} -> {new_rating} ELO ({change:+d}) — {old_rank} -> {rank}"
                )

            public_message = "\n".join(lines)

            if interaction.channel is not None:
                await interaction.channel.send(public_message)

            await interaction.response.send_message(
                f"Posted the public ranked match review for match #{self.match_id} and applied the rating changes.",
                ephemeral=True,
            )
        except Exception as exc:
            await interaction.response.send_message(f"Failed to post the match review: {exc}", ephemeral=True)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_message("Record-result cancelled. No public review was posted.", ephemeral=True)


class RankedEditStatsConfirmView(discord.ui.View):
    def __init__(
        self,
        player_repo: PlayerRepository,
        discord_user_id: int,
        matches_played: int,
        wins: int,
        losses: int,
        kills: int,
        deaths: int,
        rating_points: int,
    ) -> None:
        super().__init__(timeout=180)
        self.player_repo = player_repo
        self.discord_user_id = discord_user_id
        self.matches_played = matches_played
        self.wins = wins
        self.losses = losses
        self.kills = kills
        self.deaths = deaths
        self.rating_points = rating_points

    @discord.ui.button(label="Confirm Full Edit", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        try:
            previous_player = self.player_repo.get_by_discord_id(self.discord_user_id)
            updated = self.player_repo.update_stats(
                self.discord_user_id,
                matches_played=self.matches_played,
                wins=self.wins,
                losses=self.losses,
                kills=self.kills,
                deaths=self.deaths,
                rating_points=self.rating_points,
            )
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        if interaction.guild is not None and updated is not None:
            try:
                await sync_member_rank(
                    interaction,
                    updated,
                    previous_rating=previous_player.rating_points if previous_player is not None else None,
                    send_rank_up_message=True,
                    target_user_id=self.discord_user_id,
                )
            except Exception as exc:
                log.warning("Rank sync after full stats edit failed for %s: %s", self.discord_user_id, exc)

        await interaction.response.send_message(
            f"Updated {updated.ign}'s full ranked stats: {self.matches_played} matches, {self.wins} wins, {self.losses} losses, "
            f"{self.kills} kills, {self.deaths} deaths, {self.rating_points} rating points.",
            ephemeral=True,
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_message("Profile edit cancelled. No stats were changed.", ephemeral=True)


class RankedResultReviewView(discord.ui.View):
    def __init__(
        self,
        player_repo: PlayerRepository,
        match_repo: MatchRepository,
        match_id: int,
        match_players: list[object],
        winning_player_ids: set[int],
        parsed_result: Any,
    ) -> None:
        super().__init__(timeout=180)
        self.player_repo = player_repo
        self.match_repo = match_repo
        self.match_id = match_id
        self.match_players = match_players
        self.winning_player_ids = winning_player_ids
        self.parsed_result = parsed_result

    @discord.ui.button(label="Confirm Result", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        updated_players: list[str] = []
        for player in self.match_players:
            stats = self.parsed_result.player_stats.get(player.discord_user_id, {"kills": 0, "deaths": 0})
            won = player.discord_user_id in self.winning_player_ids
            self.player_repo.record_match_result(
                player.discord_user_id,
                kills=int(stats.get("kills", 0)),
                deaths=int(stats.get("deaths", 0)),
                won=won,
            )
            updated_players.append(
                f"{player.ign}: {stats.get('kills', 0)} kills / {stats.get('deaths', 0)} deaths ({'W' if won else 'L'})"
            )

        self.match_repo.update_match_status(self.match_id, "COMPLETED")

        await interaction.response.send_message(
            f"Confirmed. Updated {len(updated_players)} registered profiles and marked match #{self.match_id} complete.\n"
            + "\n".join(updated_players),
            ephemeral=True,
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_message(
            f"Cancelled the result update for match #{self.match_id}. No player stats were saved.",
            ephemeral=True,
        )


class RankedFormatView(discord.ui.View):
    def __init__(self, bot: commands.Bot, player_repo: PlayerRepository, match_repo: MatchRepository, ranked_service: RankedService) -> None:
        super().__init__(timeout=180)
        self.bot = bot
        self.player_repo = player_repo
        self.match_repo = match_repo
        self.ranked_service = ranked_service

    @discord.ui.button(label="1v1", style=discord.ButtonStyle.primary)
    async def one_v_one(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._start_match(interaction, 1)

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
        await interaction.response.send_message("Starting ranked queue...", ephemeral=True)

        player = self.player_repo.get_by_discord_id(interaction.user.id)
        if player is None:
            await interaction.followup.send_message("You must register before joining ranked matches.", ephemeral=True)
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

        await interaction.message.edit(
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
        await interaction.response.send_message("Joining ranked queue...", ephemeral=True)

        player = self.player_repo.get_by_discord_id(interaction.user.id)
        if player is None:
            await interaction.followup.send_message("You must register before joining ranked matches.", ephemeral=True)
            return

        match = self.match_repo.get_match(self.match_id)
        if match is None:
            await interaction.followup.send_message("This ranked match no longer exists.", ephemeral=True)
            return

        if match.status != "QUEUING":
            await interaction.followup.send_message("This match is no longer accepting joins.", ephemeral=True)
            return

        if self.match_repo.player_in_active_match(interaction.user.id, exclude_match_id=self.match_id):
            await interaction.followup.send_message("You are already in another active ranked match.", ephemeral=True)
            return

        if self.match_repo.has_player_in_match(self.match_id, interaction.user.id):
            await interaction.followup.send_message("You are already in this match.", ephemeral=True)
            return

        if self.match_repo.participant_count(self.match_id) >= match.required_players:
            await interaction.followup.send_message("This queue is already full.", ephemeral=True)
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
        await interaction.response.send_message("Leaving ranked queue...", ephemeral=True)

        if self.match_repo.has_player_in_match(self.match_id, interaction.user.id):
            self.match_repo.remove_participant(self.match_id, interaction.user.id)
            await self._refresh_embed(interaction)
            return

        await interaction.followup.send_message("You are not in this match.", ephemeral=True)

    async def _handle_cancel(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message("Cancelling ranked queue...", ephemeral=True)

        match = self.match_repo.get_match(self.match_id)
        if match is None:
            await interaction.followup.send_message("This match no longer exists.", ephemeral=True)
            return

        if interaction.user.id != match.creator_discord_id and not is_staff_or_admin(interaction.user):
            await interaction.followup.send_message("You do not have permission to cancel this match.", ephemeral=True)
            return

        self.match_repo.update_match_status(self.match_id, "CANCELLED")
        await interaction.message.edit(
            embed=build_match_status_embed(match_id=self.match_id, status="CANCELLED", message="This ranked match was cancelled."),
            view=None,
        )

    async def _refresh_embed(self, interaction: discord.Interaction) -> None:
        match = self.match_repo.get_match(self.match_id)
        if match is None:
            await interaction.followup.send_message("This ranked match no longer exists.", ephemeral=True)
            return

        participants = self.match_repo.list_participants(self.match_id)
        player_objects = [self.player_repo.get_by_discord_id(p["discord_user_id"]) for p in participants]
        player_objects = [player for player in player_objects if player is not None]
        players_count = len(player_objects)

        if players_count >= match.required_players:
            self.match_repo.update_match_status(self.match_id, "GENERATING")
            await interaction.message.edit(
                embed=build_match_status_embed(match_id=match.id, status="GENERATING", message="Match found. Generating teams..."),
                view=None,
            )
            await asyncio.sleep(1)
            await self._finalize_match(interaction)
            return

        await interaction.message.edit(
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
            await interaction.followup.send_message("This ranked match no longer exists.", ephemeral=True)
            return

        participants = self.match_repo.list_participants(self.match_id)
        players = [self.player_repo.get_by_discord_id(p["discord_user_id"]) for p in participants]
        players = [player for player in players if player is not None]

        if len(players) < match.required_players:
            self.match_repo.update_match_status(self.match_id, "CANCELLED")
            await interaction.message.edit(
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

        await interaction.message.edit(
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
        await interaction.response.send_message("Marking match complete...", ephemeral=True)
        self.match_repo.update_match_status(self.match_id, "COMPLETED")
        await interaction.message.edit(
            embed=build_match_status_embed(match_id=self.match_id, status="COMPLETED", message="This ranked match has been marked complete."),
            view=None,
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_message("Cancelling match completion...", ephemeral=True)
        await interaction.message.edit(
            embed=build_match_status_embed(match_id=self.match_id, status="READY", message="Match completion was cancelled."),
            view=None,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RankedCog(bot))
