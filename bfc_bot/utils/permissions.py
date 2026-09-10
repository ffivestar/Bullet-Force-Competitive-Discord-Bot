from __future__ import annotations

import discord


def is_staff_or_admin(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True

    for role in getattr(member, "roles", []):
        if getattr(role, "name", "") in {"Tournament Staff", "BFC Admin"}:
            return True

    return False
