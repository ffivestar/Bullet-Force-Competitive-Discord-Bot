"""Recoverable Discord delivery; IDs and pending cleanup survive restarts."""
from __future__ import annotations

import hashlib
import json
import re
import time
import discord
from presentation import match_text, result_text, safe
from rendering import bracket_png


class MatchChannelManager:
    def __init__(self, bot, store):
        self.bot, self.store = bot, store

    async def channel(self, guild, cid):
        if not cid:
            return None
        cached = guild.get_channel(cid)
        if cached:
            return cached
        try:
            channel = await guild.fetch_channel(cid)
            return channel
        except discord.NotFound:
            return None

    async def sync(self, t, board_view=None):
        guild = self.bot.get_guild(t['guild_id'])
        if guild is None:
            return
        # Archive results before retiring any room. A failed send leaves the room available.
        for mid,m in t['matches'].items():
            old=t['archives'].get(mid)
            signature=hashlib.sha256(json.dumps([m['result'],m['map'],m['region']],sort_keys=True).encode()).hexdigest()
            if (m['result'] or old) and (not old or old['signature']!=signature):
                channel = await self.channel(guild,old['channel']) if old else None
                if channel is None:
                    channel=discord.utils.get(guild.text_channels,name=self.bot.settings.match_results_channel_name)
                if channel is None:
                    channel=await guild.create_text_channel(self.bot.settings.match_results_channel_name, reason='Permanent BFC result archive')
                message=None
                if old and old['channel']==channel.id:
                    try:
                        message=await channel.fetch_message(old['message'])
                    except discord.NotFound:
                        pass
                if message:
                    await message.edit(content=result_text(t,m),allowed_mentions=discord.AllowedMentions.none())
                else:
                    message=await channel.send(result_text(t,m),allowed_mentions=discord.AllowedMentions.none())
                t['archives'][mid]={'channel':channel.id,'message':message.id,'signature':signature}
                self.store.save(t)
        for mid,room in list(t['rooms'].items()):
            m=t['matches'][mid]
            if m['status']!='ready' or room['version']!=m['version'] or t['status']=='cancelled':
                text_channel=await self.channel(guild,room.get('text'))
                if text_channel:
                    if m['result']:
                        r=m['result']; a,b=r['teams']
                        closing=f"Match complete: {safe(t['teams'][a]['name'])} {r['scores'][0]}–{r['scores'][1]} {safe(t['teams'][b]['name'])}."
                    else:
                        closing='This match was cancelled or changed by a result correction.'
                    await text_channel.send(closing+' This room and its voice channels close in 45 seconds.',allowed_mentions=discord.AllowedMentions.none())
                t['cleanup'].append({'ids':[room[k] for k in ('text','a','b') if room.get(k)],'after':time.time()+45})
                del t['rooms'][mid]
                self.store.save(t)
        for job in list(t['cleanup']):
            if job['after']>time.time():
                continue
            for cid in list(job['ids']):
                channel=await self.channel(guild,cid)
                if channel:
                    await channel.delete(reason='BFC completed or invalidated match cleanup')
                job['ids'].remove(cid)
                self.store.save(t)
            t['cleanup'].remove(job)
            self.store.save(t)
        if t['status']=='active':
            for m in t['matches'].values():
                if m['status']=='ready':
                    await self.ensure_room(guild,t,m)
        if t['board_channel'] and t['matches']:
            signature=hashlib.sha256(json.dumps([t['matches'],t['status']],sort_keys=True).encode()).hexdigest()
            if signature != t.get('board_signature'):
                channel=await self.channel(guild,t['board_channel'])
                if channel:
                    attachment=discord.File(bracket_png(t),filename='bfc-bracket.png')
                    content=f"🏆 **{safe(t['name'])}** · Tournament #{t['id']} · {len(t['teams'])} teams · **{t['status']}**"
                    if t.get('champion'):
                        content+='\nChampion: **'+safe(t['teams'][t['champion']]['name'])+'**'
                    message=None
                    if t['board_message']:
                        try:
                            message=await channel.fetch_message(t['board_message'])
                        except discord.NotFound:
                            pass
                    if message:
                        await message.edit(content=content,attachments=[attachment],view=board_view,allowed_mentions=discord.AllowedMentions.none())
                    else:
                        message=await channel.send(content,file=attachment,view=board_view,allowed_mentions=discord.AllowedMentions.none())
                    t['board_message']=message.id
                    t['board_signature']=signature
                    self.store.save(t)

    async def ensure_room(self,guild,t,m):
        room=t['rooms'].setdefault(m['id'],{'version':m['version']})
        # One category per tournament, spilling after 15 simultaneous match rooms.
        category_name=f"{self.bot.settings.tournament_category_name} {t['id']}"[:90]
        category=next((c for c in guild.categories if c.name.startswith(category_name+' ·') and len(c.channels)<=47),None)
        if category is None:
            count=sum(c.name.startswith(category_name+' ·') for c in guild.categories)
            category=await guild.create_category(f'{category_name} · {count+1}')
        roles=[r for r in guild.roles if r.name in (self.bot.settings.tournament_staff_role_name,self.bot.settings.bfc_admin_role_name)]
        members={}
        for tid in m['teams']:
            for uid in t['teams'][tid]['players']:
                member=guild.get_member(int(uid))
                if member is None:
                    try:
                        member=await guild.fetch_member(int(uid))
                    except discord.NotFound:
                        # Departed players remain in the historical roster; no accidental public access.
                        continue
                members[uid]=member
        for key in ('text','a','b'):
            channel=await self.channel(guild,room.get(key))
            if channel:
                continue
            is_text=key=='text'
            overwrites={guild.default_role:discord.PermissionOverwrite(view_channel=is_text,send_messages=False,connect=False)}
            for role in roles:
                overwrites[role]=discord.PermissionOverwrite(view_channel=True,send_messages=True,connect=True,speak=True)
            if guild.me:
                overwrites[guild.me]=discord.PermissionOverwrite(view_channel=True,send_messages=True,connect=True,speak=True,manage_channels=True,read_message_history=True,attach_files=True,embed_links=True)
            tids=m['teams'] if is_text else [m['teams'][0 if key=='a' else 1]]
            for tid in tids:
                for uid in t['teams'][tid]['players']:
                    if uid in members:
                        overwrites[members[uid]]=discord.PermissionOverwrite(view_channel=True,send_messages=True,connect=True,speak=True)
            a,b=(t['teams'][tid]['name'] for tid in m['teams'])
            marker=f'bfc-{t["id"]}-{m["id"].lower()}-v{m["version"]}'
            name=(f'{marker}-{a}-vs-{b}' if is_text else f'{marker}-{key} {a if key=="a" else b}')[:100]
            if is_text:
                name=re.sub(r'[^a-z0-9-]+','-',name.lower()).strip('-')
            # Recover a channel created immediately before a process crash.
            channel=next((c for c in guild.channels if c.name==name and isinstance(c,discord.TextChannel if is_text else discord.VoiceChannel)),None)
            if channel is None:
                if is_text:
                    channel=await guild.create_text_channel(name,category=category,overwrites=overwrites,topic=f'BFC tournament {t["id"]}, match {m["id"]}',reason='BFC active match')
                else:
                    channel=await guild.create_voice_channel(name,category=category,overwrites=overwrites,reason='BFC private team voice')
            room[key]=channel.id
            if is_text:
                room.pop('intro',None)
            self.store.save(t)
        signature=hashlib.sha256(match_text(t,m).encode()).hexdigest()
        if signature != room.get('intro_signature'):
            channel=await self.channel(guild,room['text'])
            message=None
            if room.get('intro'):
                try:
                    message=await channel.fetch_message(room['intro'])
                except discord.NotFound:
                    pass
            if message:
                await message.edit(content=match_text(t,m),allowed_mentions=discord.AllowedMentions.none())
            else:
                message=await channel.send(match_text(t,m),allowed_mentions=discord.AllowedMentions.none())
            room['intro']=message.id
            room['intro_signature']=signature
            self.store.save(t)
