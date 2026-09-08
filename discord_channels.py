from __future__ import annotations

import discord

from config import Settings


class MatchChannelManager:
    """Discord channel lifecycle boundary for active matches."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def create_match_channels(
        self,
        guild: discord.Guild,
        match_id: int,
        team_a: tuple[str, list[int]],
        team_b: tuple[str, list[int]],
        staff_role: discord.Role | None,
    ) -> tuple[discord.TextChannel, discord.VoiceChannel, discord.VoiceChannel]:
        category = discord.utils.get(guild.categories, name=self.settings.tournament_category_name)
        if category is None:
            category = await guild.create_category(self.settings.tournament_category_name)

        everyone = guild.default_role
        staff_overwrite = discord.PermissionOverwrite(view_channel=True, connect=True, speak=True)
        base_voice_overwrite = discord.PermissionOverwrite(view_channel=False, connect=False)
        text_overwrites = {everyone: discord.PermissionOverwrite(view_channel=True, send_messages=False)}
        if staff_role:
            text_overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        text_channel = await guild.create_text_channel(
            f"match-{match_id}-{team_a[0]}-vs-{team_b[0]}"[:100],
            category=category,
            overwrites=text_overwrites,
        )

        def voice_overwrites(team_ids: list[int]) -> dict[discord.abc.Snowflake, discord.PermissionOverwrite]:
            overwrites: dict[discord.abc.Snowflake, discord.PermissionOverwrite] = {everyone: base_voice_overwrite}
            if staff_role:
                overwrites[staff_role] = staff_overwrite
            for user_id in team_ids:
                member = guild.get_member(user_id)
                if member:
                    overwrites[member] = discord.PermissionOverwrite(view_channel=True, connect=True, speak=True)
            return overwrites

        team_a_voice = await guild.create_voice_channel(f"{team_a[0]} voice"[:100], category=category, overwrites=voice_overwrites(team_a[1]))
        team_b_voice = await guild.create_voice_channel(f"{team_b[0]} voice"[:100], category=category, overwrites=voice_overwrites(team_b[1]))
        return text_channel, team_a_voice, team_b_voice

    async def delete_match_channels(self, channels: list[discord.abc.GuildChannel]) -> None:
        for channel in channels:
            try:
                await channel.delete(reason="Completed tournament match cleanup")
            except discord.NotFound:
                continue
