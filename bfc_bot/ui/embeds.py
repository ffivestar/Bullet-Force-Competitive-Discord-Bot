from __future__ import annotations

from datetime import datetime
from typing import Iterable

import discord


def utc_now() -> datetime:
    return datetime.utcnow()


def build_registration_embed() -> discord.Embed:
    embed = discord.Embed(
        title="BFC Registration",
        description="Register to participate in ranked Bullet Force community matches.",
        color=discord.Color.blurple(),
    )
    embed.add_field(
        name="Requirement",
        value="If you play on PC, put PC- at the beginning of your IGN. Example: PC-5ive",
        inline=False,
    )
    embed.set_footer(text="This registration is tied to your Discord account.")
    return embed


def build_registration_confirm_embed(ign: str, already_registered: bool = False, updated: bool = False) -> discord.Embed:
    action = "already registered" if already_registered else "updated" if updated else "registered"
    embed = discord.Embed(
        title=f"Player {action}",
        description=f"Your IGN is now set to {ign}.",
        color=discord.Color.green(),
    )
    embed.add_field(name="IGN", value=ign, inline=True)
    embed.set_footer(text="Your Discord account remains the permanent player ID.")
    return embed


def build_profile_embed(player: object) -> discord.Embed:
    matches = player.matches_played or 0
    wins = player.wins or 0
    losses = player.losses or 0
    win_rate = (wins / matches * 100) if matches else 0
    kd = (player.kills / player.deaths) if player.deaths else float("inf") if player.kills else 0
    kd_text = "∞" if kd == float("inf") else f"{kd:.2f}"

    embed = discord.Embed(
        title=f"{player.ign} | Profile",
        color=discord.Color.blurple(),
    )
    embed.add_field(name="IGN", value=player.ign, inline=True)
    embed.add_field(name="Rating", value=str(player.rating_points), inline=True)
    embed.add_field(name="Matches", value=str(matches), inline=True)
    embed.add_field(name="Wins", value=str(wins), inline=True)
    embed.add_field(name="Losses", value=str(losses), inline=True)
    embed.add_field(name="Win Rate", value=f"{win_rate:.1f}%", inline=True)
    embed.add_field(name="Kills", value=str(player.kills), inline=True)
    embed.add_field(name="Deaths", value=str(player.deaths), inline=True)
    embed.add_field(name="K/D", value=kd_text, inline=True)
    embed.set_footer(text=f"Discord ID: {player.discord_user_id}")
    return embed


def build_queue_choice_embed() -> discord.Embed:
    embed = discord.Embed(
        title="BFC Ranked",
        description="Choose a ranked format to start a matchmaking queue.",
        color=discord.Color.dark_orange(),
    )
    embed.add_field(name="Formats", value="2v2, 3v3, 4v4, 5v5, 6v6", inline=False)
    embed.set_footer(text="Match ID will be assigned once the queue is created.")
    return embed


def build_matchmaking_embed(match_id: int, team_size: int, players: list[object], status: str, required_players: int) -> discord.Embed:
    player_text = "\n".join(f"• {player.ign}" for player in players) or "No players joined yet."
    embed = discord.Embed(
        title=f"BFC Ranked #{match_id}",
        description=f"{team_size}v{team_size} Matchmaking",
        color=discord.Color.gold(),
    )
    embed.add_field(name=f"Players", value=f"{len(players)} / {required_players}", inline=False)
    embed.add_field(name="Queue", value=player_text, inline=False)
    embed.add_field(name="Status", value=status, inline=True)
    embed.set_footer(text=f"Match ID #{match_id}")
    return embed


def build_match_status_embed(match_id: int, status: str, message: str) -> discord.Embed:
    embed = discord.Embed(
        title=f"BFC Ranked #{match_id}",
        description=message,
        color=discord.Color.dark_orange() if status == "GENERATING" else discord.Color.red() if status == "CANCELLED" else discord.Color.blurple(),
    )
    embed.add_field(name="Status", value=status, inline=False)
    embed.set_footer(text=f"Match ID #{match_id}")
    return embed


def build_match_ready_embed(match_id: int, team_size: int, map_name: str, room_name: str, room_password: str, team_one: list[object], team_two: list[object]) -> discord.Embed:
    embed = discord.Embed(
        title=f"BFC Ranked #{match_id}",
        description="Match ready.",
        color=discord.Color.green(),
    )
    embed.add_field(name="Format", value=f"{team_size}v{team_size}", inline=True)
    embed.add_field(name="Map", value=map_name, inline=True)
    embed.add_field(name="Mode", value="TDM", inline=True)
    embed.add_field(name="Room", value=room_name, inline=False)
    embed.add_field(name="Password", value=room_password, inline=False)
    embed.add_field(name="Team 1", value=_format_team(team_one), inline=True)
    embed.add_field(name="Team 2", value=_format_team(team_two), inline=True)
    embed.set_footer(text=f"Status: READY | Match ID #{match_id}")
    return embed


def _format_team(players: list[object]) -> str:
    if not players:
        return "No players"
    return "\n".join(f"• <@{player.discord_user_id}> — {player.ign}" for player in players)
