from __future__ import annotations

import logging
import re
from typing import Any

import discord

log = logging.getLogger(__name__)

RANK_ROLE_NAMES = ["Bronze", "Silver", "Gold", "Platinum", "Diamond", "Master", "Grandmaster", "Elite"]
RANK_THRESHOLDS = {
    "Bronze": (0, 149),
    "Silver": (150, 299),
    "Gold": (300, 449),
    "Platinum": (450, 599),
    "Diamond": (600, 749),
    "Master": (750, 849),
    "Grandmaster": (850, 949),
    "Elite": (950, 1000),
}

RANK_ORDER = {name: index for index, name in enumerate(RANK_ROLE_NAMES)}


def get_rank_for_rating(rating: int) -> str:
    for rank_name, (minimum, maximum) in RANK_THRESHOLDS.items():
        if minimum <= rating <= maximum:
            return rank_name
    return "Bronze"


def strip_existing_rating_prefix(ign: str) -> str:
    return re.sub(r"^\[\d+\]\s*", "", ign.strip())


def build_rating_nickname(ign: str, rating: int) -> str:
    clean_ign = strip_existing_rating_prefix(ign)
    base = f"[{rating}] {clean_ign}"
    if len(base) <= 32:
        return base

    remaining = max(0, 32 - len(f"[{rating}] "))
    trimmed_ign = clean_ign[:remaining].rstrip()
    return f"[{rating}] {trimmed_ign}"


async def sync_member_rank(
    interaction: discord.Interaction,
    player: Any,
    *,
    previous_rating: int | None = None,
    send_rank_up_message: bool = True,
    target_user_id: int | None = None,
) -> dict[str, Any]:
    guild = interaction.guild
    channel = getattr(interaction, "channel", None)

    if guild is None:
        return {"nickname_updated": False, "roles_updated": False, "rank_up_message_sent": False, "errors": ["Guild not found"]}

    target_member_id = target_user_id if target_user_id is not None else interaction.user.id

    try:
        member = interaction.user if isinstance(interaction.user, discord.Member) and interaction.user.id == target_member_id else guild.get_member(target_member_id)
        if member is None:
            member = await guild.fetch_member(target_member_id)
    except (discord.HTTPException, discord.NotFound) as exc:
        log.warning("Failed to fetch guild member for player %s in guild %s: %s", player.discord_user_id, guild.id, exc)
        return {"nickname_updated": False, "roles_updated": False, "rank_up_message_sent": False, "errors": [str(exc)]}

    errors: list[str] = []
    role_by_name = {role.name: role for role in guild.roles if role.name in RANK_ROLE_NAMES}
    target_rank = get_rank_for_rating(player.rating_points)
    target_role = role_by_name.get(target_rank)

    guild_me = guild.me
    can_manage_roles = bool(guild_me and guild_me.guild_permissions.manage_roles)
    can_manage_nicknames = bool(guild_me and guild_me.guild_permissions.manage_nicknames)

    if can_manage_roles:
        roles_to_remove = [role for role in member.roles if role.name in RANK_ROLE_NAMES and role.name != target_rank]
        if roles_to_remove:
            try:
                await member.remove_roles(*roles_to_remove, reason=f"Synchronizing ranked roles for {player.ign}")
            except discord.Forbidden as exc:
                errors.append(f"Missing permission to remove ranked roles: {exc}")
                log.warning("Could not remove ranked roles for %s in guild %s: %s", player.discord_user_id, guild.id, exc)
            except (discord.HTTPException, discord.NotFound) as exc:
                errors.append(f"Failed to remove ranked roles: {exc}")
                log.warning("Could not remove ranked roles for %s in guild %s: %s", player.discord_user_id, guild.id, exc)

        if target_role is not None and target_role not in member.roles:
            try:
                await member.add_roles(target_role, reason=f"Synchronizing ranked role for {player.ign}")
            except discord.Forbidden as exc:
                errors.append(f"Missing permission to assign ranked role: {exc}")
                log.warning("Could not assign ranked role for %s in guild %s: %s", player.discord_user_id, guild.id, exc)
            except (discord.HTTPException, discord.NotFound) as exc:
                errors.append(f"Failed to assign ranked role: {exc}")
                log.warning("Could not assign ranked role for %s in guild %s: %s", player.discord_user_id, guild.id, exc)
    else:
        errors.append("Bot lacks Manage Roles permission; ranked role synchronization skipped.")
        log.warning("Bot lacks Manage Roles permission in guild %s; ranked role synchronization skipped for %s.", guild.id, player.discord_user_id)

    if can_manage_nicknames:
        desired_nickname = build_rating_nickname(player.ign, player.rating_points)
        if member.nick != desired_nickname:
            try:
                await member.edit(nick=desired_nickname, reason=f"Updating ranked nickname for {player.ign}")
            except discord.Forbidden as exc:
                errors.append(f"Missing permission to edit nickname: {exc}")
                log.warning("Could not update nickname for %s in guild %s: %s", player.discord_user_id, guild.id, exc)
            except (discord.HTTPException, discord.NotFound) as exc:
                errors.append(f"Failed to edit nickname: {exc}")
                log.warning("Could not update nickname for %s in guild %s: %s", player.discord_user_id, guild.id, exc)
    else:
        errors.append("Bot lacks Manage Nicknames permission; nickname synchronization skipped.")
        log.warning("Bot lacks Manage Nicknames permission in guild %s; nickname synchronization skipped for %s.", guild.id, player.discord_user_id)

    rank_up_message_sent = False
    if send_rank_up_message and previous_rating is not None:
        previous_rank = get_rank_for_rating(previous_rating)
        if previous_rank != target_rank and RANK_ORDER[target_rank] > RANK_ORDER[previous_rank] and channel is not None:
            try:
                await channel.send(
                    f"<@{player.discord_user_id}> has ranked up to {target_rank}!\nRating: {previous_rating} -> {player.rating_points}",
                )
                rank_up_message_sent = True
            except (discord.HTTPException, discord.NotFound) as exc:
                errors.append(f"Failed to send rank-up message: {exc}")
                log.warning("Could not send rank-up message for %s in guild %s: %s", player.discord_user_id, guild.id, exc)

    return {
        "nickname_updated": can_manage_nicknames and member.nick == build_rating_nickname(player.ign, player.rating_points),
        "roles_updated": can_manage_roles,
        "rank_up_message_sent": rank_up_message_sent,
        "errors": errors,
    }
