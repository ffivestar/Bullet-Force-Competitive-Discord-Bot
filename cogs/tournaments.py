from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

import engine
from discord_channels import MatchChannelManager
from presentation import kd, match_text, result_text, safe, send_text, stats_text, teams_text
from rendering import bracket_png
from store import Store

log = logging.getLogger(__name__)


def permitted(member, settings, admin=False):
    if not isinstance(member, discord.Member):
        return False
    names = {r.name for r in member.roles}
    return member.guild_permissions.administrator or settings.bfc_admin_role_name in names or (not admin and settings.tournament_staff_role_name in names)


class SafeView(discord.ui.View):
    async def on_error(self, interaction, error, item):
        log.error('Button failed', exc_info=(type(error),error,error.__traceback__))
        await send_text(interaction, str(error) if isinstance(error,engine.RuleError) else 'Discord could not finish this action. Try again; recorded results remain saved.')


class BoardView(SafeView):
    def __init__(self,cog,tid):
        super().__init__(timeout=None)
        self.cog,self.tid=cog,tid
        for label,kind in [('View Teams','teams'),('View Matches','matches'),('Player Stats','stats'),('Leaderboard','leaderboard')]:
            button=discord.ui.Button(label=label,custom_id=f'bfc:{tid}:{kind}',style=discord.ButtonStyle.secondary)
            async def callback(interaction,kind=kind):
                engine.require(interaction.guild is not None,'Use this in the tournament server.')
                t=cog.store.get(tid,interaction.guild.id)
                if kind=='teams':
                    text=teams_text(t)
                elif kind=='matches':
                    text=cog.matches_text(t)
                else:
                    text=stats_text(t)
                await send_text(interaction,text)
            button.callback=callback
            self.add_item(button)


class ConfirmView(SafeView):
    def __init__(self,cog,tid,mid,author,version,scores,stats):
        super().__init__(timeout=600)
        self.cog,self.tid,self.mid,self.author,self.version=cog,tid,mid,author,version
        self.scores,self.stats=scores,stats

    async def interaction_check(self, interaction):
        engine.require(interaction.user.id==self.author,'Only the moderator who opened this form can confirm it.')
        self.cog.authorize(interaction)
        return True

    @discord.ui.button(label='Confirm Result',style=discord.ButtonStyle.success)
    async def confirm(self,interaction,button):
        await interaction.response.defer(ephemeral=True)
        async with self.cog.lock(self.tid):
            t=self.cog.store.get(self.tid,interaction.guild.id)
            engine.require(t['status']=='active','Tournament is not active.')
            engine.submit(t,self.mid,self.scores,self.stats,interaction.user.id,self.version)
            self.cog.store.save(t)
        self.stop()
        await interaction.edit_original_response(content='Result saved. The bracket, statistics and match rooms are updating.',view=None)
        await self.cog.deliver(interaction,self.tid)

    @discord.ui.button(label='Edit',style=discord.ButtonStyle.secondary)
    async def edit(self,interaction,button):
        t=self.cog.store.get(self.tid,interaction.guild.id)
        engine.require(t['matches'][self.mid]['version']==self.version,'Match changed; open a fresh result form.')
        await interaction.response.send_modal(ResultModal(self.cog,t,self.mid,self.scores,self.stats))
        self.stop()
        if interaction.message:
            await interaction.message.edit(view=None)


class ResultModal(discord.ui.Modal):
    def __init__(self,cog,t,mid,scores=None,stats=None):
        super().__init__(title=f'Tournament {t["id"]} · {mid} result',timeout=600)
        self.cog,self.tid,self.mid,self.version=cog,t['id'],mid,t['matches'][mid]['version']
        self.rosters=[list(t['teams'][tid]['players']) for tid in t['matches'][mid]['teams']]
        self.score=discord.ui.TextInput(label='Team A score, Team B score',placeholder='3, 1',default=', '.join(map(str,scores)) if scores else None,max_length=8)
        self.add_item(self.score)
        self.stat_inputs=[]
        for i,tid in enumerate(t['matches'][mid]['teams']):
            # Three ordered rows per team fit comfortably within Discord's five-field modal limit.
            rows='\n'.join(t['players'][uid]['name'].replace('\n',' ')+' | '+(f"{uid} {stats[uid][0]} {stats[uid][1]}" if stats else f'{uid} K D') for uid in self.rosters[i])
            field=discord.ui.TextInput(label=f"Team {'AB'[i]}: player ID kills deaths",style=discord.TextStyle.paragraph,default=rows,max_length=500)
            self.stat_inputs.append(field)
            self.add_item(field)

    async def on_submit(self,interaction):
        self.cog.authorize(interaction)
        t=self.cog.store.get(self.tid,interaction.guild.id)
        engine.require(t['status']=='active','Tournament is not active.')
        engine.require(t['matches'][self.mid]['version']==self.version,'Match changed; open a fresh result form.')
        try:
            scores=[int(v) for v in re.split(r'[,\s]+',str(self.score).strip())]
            stats={}
            for i,field in enumerate(self.stat_inputs):
                lines=str(field).strip().splitlines()
                engine.require(len(lines)==3,'Enter exactly three player rows per team.')
                for line in lines:
                    parts=re.split(r'[,\s]+',line.rsplit('|',1)[-1].strip())
                    engine.require(len(parts)==3,'Use: player_ID kills deaths (one player per line).')
                    uid=parts[0].strip('<@!>')
                    engine.require(uid in self.rosters[i] and uid not in stats,'Player ID is duplicated or belongs to the wrong team.')
                    stats[uid]=[int(parts[1]),int(parts[2])]
        except ValueError as exc:
            if isinstance(exc,engine.RuleError):
                raise
            raise engine.RuleError('Replace K and D with whole-number kills and deaths. Scores use A, B.') from exc
        engine.validate_result(t,self.mid,scores,stats)
        preview={'teams':t['matches'][self.mid]['teams'],'scores':scores,'stats':stats}
        await interaction.response.send_message('**Review before saving**\n'+result_text(t,t['matches'][self.mid],preview),view=ConfirmView(self.cog,self.tid,self.mid,interaction.user.id,self.version,scores,stats),ephemeral=True,allowed_mentions=discord.AllowedMentions.none())

    async def on_error(self,interaction,error):
        log.error('Result form failed',exc_info=(type(error),error,error.__traceback__))
        await send_text(interaction,str(error) if isinstance(error,engine.RuleError) else 'Unable to read this form. Open /match result and try again.')


class ActionView(SafeView):
    def __init__(self,cog,t,author,action,mid=None):
        super().__init__(timeout=300)
        self.cog,self.tid,self.author,self.action,self.mid=cog,t['id'],author,action,mid
        # Only rule state matters; background Discord delivery must not stale this confirmation.
        self.versions={key:m['version'] for key,m in t['matches'].items()}

    async def interaction_check(self,interaction):
        engine.require(interaction.user.id==self.author,'Only the requesting administrator can confirm.')
        self.cog.authorize(interaction,admin=True)
        return True

    @discord.ui.button(label='Confirm',style=discord.ButtonStyle.danger)
    async def confirm(self,interaction,button):
        await interaction.response.defer(ephemeral=True)
        async with self.cog.lock(self.tid):
            t=self.cog.store.get(self.tid,interaction.guild.id)
            engine.require(self.versions=={key:m['version'] for key,m in t['matches'].items()},'Results changed. Request the action again to review its impact.')
            if self.action=='undo':
                engine.require(t['status']!='cancelled','Cancelled tournaments cannot be changed.')
                affected=engine.undo(t,self.mid,interaction.user.id)
                text='Result undone. Invalidated dependent matches: '+', '.join(affected)+'. Resubmit results after correcting the original match.'
            else:
                t['status']='cancelled'
                t['revisions'].append({'action':'cancel','by':str(interaction.user.id)})
                text='Tournament cancelled. Match rooms will close; history is retained.'
            self.cog.store.save(t)
        self.stop()
        await interaction.edit_original_response(content=text,view=None)
        await self.cog.deliver(interaction,self.tid)

    @discord.ui.button(label='Cancel',style=discord.ButtonStyle.secondary)
    async def cancel(self,interaction,button):
        self.stop()
        await interaction.response.edit_message(content='Action cancelled.',view=None)


class TournamentCog(commands.Cog):
    tournament=app_commands.Group(name='tournament',description='Create and run BFC tournaments',guild_only=True)
    players=app_commands.Group(name='players',description='Manage the tournament player pool',guild_only=True)
    teams=app_commands.Group(name='teams',description='Create balanced random teams',guild_only=True)
    team=app_commands.Group(name='team',description='Manage manual teams',guild_only=True)
    match=app_commands.Group(name='match',description='Match rooms, results and history',guild_only=True)
    stats=app_commands.Group(name='stats',description='Tournament and player statistics',guild_only=True)

    def __init__(self,bot):
        self.bot=bot
        self.store=Store(bot.database)
        self.locks={}
        self.manager=MatchChannelManager(bot,self.store)
        self.last_errors={}

    async def cog_load(self):
        for t in self.store.all():
            if t['board_message']:
                self.bot.add_view(BoardView(self,t['id']),message_id=t['board_message'])
        self.reconcile.start()

    async def cog_unload(self):
        self.reconcile.cancel()

    def lock(self,tid):
        return self.locks.setdefault(tid,asyncio.Lock())

    def authorize(self,interaction,admin=False):
        engine.require(interaction.guild is not None,'Use this command in your Discord server.')
        engine.require(permitted(interaction.user,self.bot.settings,admin),f"Requires {self.bot.settings.bfc_admin_role_name if admin else self.bot.settings.tournament_staff_role_name} or an administrator.")

    async def members(self,guild,text,strict=False):
        # Mentions/IDs separated by spaces, or exact names separated by commas/newlines.
        text=text.strip()
        if re.fullmatch(r'(?:<@!?\d+>|\d+)(?:[\s,]+(?:<@!?\d+>|\d+))*',text):
            tokens=re.findall(r'<@!?\d+>|\d+',text)
        else:
            tokens=[s.strip() for s in re.split(r'[,\n]+',text) if s.strip()]
        engine.require(1<=len(tokens)<=96,'Supply 1–96 mentions/IDs, or comma-separated exact names.')
        people=[]
        for token in tokens:
            uid=token.strip('<@!>')
            if uid.isdigit():
                member=guild.get_member(int(uid))
                if member is None:
                    try:
                        member=await guild.fetch_member(int(uid))
                    except discord.NotFound:
                        raise engine.RuleError(f'Player {uid} is not in this server.')
            else:
                if not guild.chunked:
                    await guild.chunk(cache=True)
                found=[m for m in guild.members if token.casefold() in {m.name.casefold(),m.display_name.casefold()}]
                engine.require(len(found)==1,f'Name “{token}” is missing or ambiguous. Use a Discord mention or ID.')
                member=found[0]
            engine.require(not member.bot,'Bots cannot enter tournaments.')
            tier_names=self.bot.settings.tier_role_names
            tiers=[i+1 for i,name in enumerate(tier_names) if any(r.name==name for r in member.roles)]
            engine.require(len(tiers)<=1,f'{member.display_name} has multiple tier roles. Assign exactly one.')
            engine.require(not strict or len(tiers)==1,f'{member.display_name} needs one of: '+', '.join(tier_names))
            people.append(engine.player(member.id,member.display_name,tiers[0] if tiers else None))
        return people

    async def mutate(self,interaction,tid,operation,admin=False):
        self.authorize(interaction,admin)
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        async with self.lock(tid):
            t=self.store.get(tid,interaction.guild.id)
            operation(t)
            self.store.save(t)
        await send_text(interaction,'Saved.')
        await self.deliver(interaction,tid)

    async def deliver(self,interaction,tid):
        try:
            async with self.lock(tid):
                t=self.store.get(tid,interaction.guild.id)
                await self.manager.sync(t,BoardView(self,tid))
            self.last_errors.pop(tid,None)
        except (discord.HTTPException,engine.RuleError) as exc:
            log.exception('Discord delivery pending for tournament %s',tid)
            self.last_errors[tid]=str(exc)
            await send_text(interaction,'Saved to the database, but a Discord update is pending. Check bot channel permissions and server channel capacity; automatic retries run every 20 seconds. /tournament sync retries now.')

    @tasks.loop(seconds=20)
    async def reconcile(self):
        for initial in self.store.all():
            tid=initial['id']
            try:
                async with self.lock(tid):
                    t=self.store.get(tid,initial['guild_id'])
                    await self.manager.sync(t,BoardView(self,tid))
                self.last_errors.pop(tid,None)
            except Exception as exc:
                self.last_errors[tid]=str(exc)
                log.exception('Retryable tournament delivery failure: %s',tid)

    @reconcile.before_loop
    async def before_reconcile(self):
        await self.bot.wait_until_ready()

    @staticmethod
    def matches_text(t):
        lines=[f"**{safe(t['name'])} — Matches**"]
        for m in t['matches'].values():
            names=[safe(t['teams'][tid]['name']) if tid else 'TBD' for tid in m['teams']]
            room=t['rooms'].get(m['id'],{}).get('text')
            lines.append(f"`{m['id']}` {' vs '.join(names)} — {m['status']}"+(f' <#{room}>' if room else ''))
        return '\n'.join(lines)

    @tournament.command(name='create',description='Create a tournament; administrators only')
    async def create(self,interaction:discord.Interaction,name:str,grand_final_reset:Optional[bool]=None,region:str='EU',map_name:str='Woods',enforce_manual_tiers:bool=False):
        self.authorize(interaction,True)
        t=self.store.create(interaction.guild.id,name,interaction.user.id,self.bot.settings.grand_final_reset_default if grand_final_reset is None else grand_final_reset,region,map_name,enforce_manual_tiers)
        await send_text(interaction,f"Created **{safe(t['name'])}**, ID `{t['id']}`. Add a player pool with /players add and /teams randomize, or use /team create. Then /tournament start.")

    @tournament.command(name='list',description='List this server’s tournaments')
    async def list_tournaments(self,interaction:discord.Interaction):
        await send_text(interaction,'\n'.join(f"`{t['id']}` **{safe(t['name'])}** — {t['status']}" for t in self.store.all(interaction.guild.id)) or 'No tournaments yet.')

    @tournament.command(name='view',description='View tournament details and matches')
    async def view(self,interaction:discord.Interaction,tournament_id:int):
        t=self.store.get(tournament_id,interaction.guild.id)
        await send_text(interaction,f"Status: **{t['status']}** · {len(t['teams'])} teams · {len(t['players'])} players\nRegion: {safe(t['region'])} · Map: {safe(t['map'])} · Final reset: {t['grand_final_reset']}\n"+self.matches_text(t))

    @tournament.command(name='teams',description='View teams and the unassigned player pool')
    async def show_teams(self,interaction:discord.Interaction,tournament_id:int):
        await send_text(interaction,teams_text(self.store.get(tournament_id,interaction.guild.id)))

    @tournament.command(name='start',description='Lock teams, seed brackets and create match rooms in this server')
    async def start(self,interaction:discord.Interaction,tournament_id:int):
        def op(t):
            engine.start(t)
            t['board_channel']=interaction.channel_id
        await self.mutate(interaction,tournament_id,op)

    @tournament.command(name='bracket',description='Show the current bracket image')
    async def bracket(self,interaction:discord.Interaction,tournament_id:int):
        t=self.store.get(tournament_id,interaction.guild.id)
        engine.require(bool(t['matches']),'Start the tournament first.')
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send(file=discord.File(bracket_png(t),filename='bfc-bracket.png'),ephemeral=True)

    @tournament.command(name='settings',description='Change tournament settings before starting; administrators only')
    async def settings(self,interaction:discord.Interaction,tournament_id:int,grand_final_reset:Optional[bool]=None,enforce_manual_tiers:Optional[bool]=None,region:Optional[str]=None,map_name:Optional[str]=None):
        def op(t):
            engine.registration(t)
            if grand_final_reset is not None:
                t['grand_final_reset']=grand_final_reset
            if enforce_manual_tiers is not None:
                if enforce_manual_tiers:
                    engine.require(all(sorted(t['players'][uid]['tier'] or 0 for uid in team['players'])==[1,2,3] for team in t['teams'].values()),'Existing teams do not meet the tier rule.')
                t['enforce_tiers']=enforce_manual_tiers
            for key,value in [('region',region),('map',map_name)]:
                if value is not None:
                    engine.require(1<=len(value.strip())<=40,'Map/region must contain 1–40 characters.')
                    t[key]=value.strip()
        await self.mutate(interaction,tournament_id,op,True)

    @tournament.command(name='delete',description='Cancel a tournament and close its rooms; preserve history')
    async def delete(self,interaction:discord.Interaction,tournament_id:int):
        self.authorize(interaction,True)
        t=self.store.get(tournament_id,interaction.guild.id)
        engine.require(t['status']!='cancelled','Tournament is already cancelled.')
        await interaction.response.send_message(f"Cancel **{safe(t['name'])}** and close all active match rooms? Results and history will be retained.",view=ActionView(self,t,interaction.user.id,'cancel'),ephemeral=True)

    @tournament.command(name='sync',description='Retry Discord delivery or restore the bracket post in this channel')
    async def sync(self,interaction:discord.Interaction,tournament_id:int,restore_board_here:bool=False):
        self.authorize(interaction)
        await interaction.response.defer(ephemeral=True)
        if restore_board_here:
            async with self.lock(tournament_id):
                t=self.store.get(tournament_id,interaction.guild.id)
                t['board_channel']=interaction.channel_id
                t['board_signature']=None
                self.store.save(t)
        await self.deliver(interaction,tournament_id)
        await send_text(interaction,'Sync completed.' if tournament_id not in self.last_errors else 'Sync still pending. Check the bot logs for the Discord error.')

    @players.command(name='add',description='Add mentions/IDs, or comma-separated exact names, to the player pool')
    async def add_players(self,interaction:discord.Interaction,tournament_id:int,names:str):
        self.authorize(interaction)
        await interaction.response.defer(ephemeral=True)
        members=await self.members(interaction.guild,names)
        await self.mutate(interaction,tournament_id,lambda t:engine.add_players(t,members))

    @players.command(name='remove',description='Remove an unassigned player from the pool')
    async def remove_player(self,interaction:discord.Interaction,tournament_id:int,member:discord.Member):
        await self.mutate(interaction,tournament_id,lambda t:engine.remove_player(t,str(member.id)))

    @teams.command(name='randomize',description='Shuffle into teams with exactly one player from each tier')
    async def randomize(self,interaction:discord.Interaction,tournament_id:int):
        self.authorize(interaction)
        await interaction.response.defer(ephemeral=True)
        async with self.lock(tournament_id):
            t=self.store.get(tournament_id,interaction.guild.id)
            engine.registration(t)
            # Refresh roles at randomisation time, rather than trusting old pool snapshots.
            engine.require(bool(t['players']),'Add players first.')
            members=await self.members(interaction.guild,' '.join(t['players']),strict=True)
            t['players']={p['id']:p for p in members}
            engine.randomize(t)
            self.store.save(t)
        await send_text(interaction,teams_text(t))

    @team.command(name='create',description='Create a three-player manual team from mentions/IDs or exact names')
    async def create_team(self,interaction:discord.Interaction,tournament_id:int,name:str,players:str):
        self.authorize(interaction)
        await interaction.response.defer(ephemeral=True)
        members=await self.members(interaction.guild,players)
        await self.mutate(interaction,tournament_id,lambda t:engine.set_team(t,name,members))

    @team.command(name='edit',description='Replace a team’s name and three-player roster before starting')
    async def edit_team(self,interaction:discord.Interaction,tournament_id:int,team_id:str,name:str,players:str):
        self.authorize(interaction)
        await interaction.response.defer(ephemeral=True)
        members=await self.members(interaction.guild,players)
        await self.mutate(interaction,tournament_id,lambda t:engine.set_team(t,name,members,team_id))

    @team.command(name='delete',description='Delete a team before starting; return its players to the pool')
    async def delete_team(self,interaction:discord.Interaction,tournament_id:int,team_id:str):
        def op(t):
            engine.registration(t)
            engine.require(team_id in t['teams'],'Team not found.')
            del t['teams'][team_id]
        await self.mutate(interaction,tournament_id,op)

    def find_match(self,interaction,tid,mid):
        if tid is None:
            for t in self.store.all(interaction.guild.id):
                for key,room in t['rooms'].items():
                    if room.get('text')==interaction.channel_id:
                        engine.require(mid is None or mid.upper()==key,'The supplied match ID does not match this room. Supply both IDs to select another match.')
                        return t,key
            raise engine.RuleError('Outside a match room, supply both tournament_id and match_id.')
        t=self.store.get(tid,interaction.guild.id)
        if mid is None:
            mid=next((key for key,room in t['rooms'].items() if room.get('text')==interaction.channel_id),None)
        mid=mid.upper() if mid else None
        engine.require(mid in t['matches'],'Match not found. Supply its ID, such as W1, L1 or G1.')
        return t,mid

    @match.command(name='view',description='View a match; IDs optional inside its match room')
    async def match_view(self,interaction:discord.Interaction,tournament_id:Optional[int]=None,match_id:Optional[str]=None):
        t,mid=self.find_match(interaction,tournament_id,match_id)
        await send_text(interaction,match_text(t,t['matches'][mid]))

    @match.command(name='result',description='Enter both scores and all six players’ kills/deaths, then confirm')
    async def result(self,interaction:discord.Interaction,tournament_id:Optional[int]=None,match_id:Optional[str]=None):
        self.authorize(interaction)
        t,mid=self.find_match(interaction,tournament_id,match_id)
        engine.require(t['status']=='active' and t['matches'][mid]['status']=='ready','Match is not awaiting a result.')
        await interaction.response.send_modal(ResultModal(self,t,mid))

    @match.command(name='undo',description='Undo a result and all dependent results; administrator confirmation required')
    async def undo(self,interaction:discord.Interaction,tournament_id:int,match_id:str):
        self.authorize(interaction,True)
        t,mid=self.find_match(interaction,tournament_id,match_id)
        engine.require(t['status']!='cancelled','Cancelled tournaments cannot be changed.')
        engine.require(t['matches'][mid]['result'] is not None,'Match has no recorded result.')
        affected=engine.affected_matches(t,mid)
        recorded=[key for key in affected if t['matches'][key]['result']]
        await interaction.response.send_message(f"Undo **{mid}**?\nResults removed: {', '.join(recorded)}.\nDependent matches rebuilt: {', '.join(affected)}.\nTheir rooms will close and statistics will be recalculated. Original results remain in the audit history.",view=ActionView(self,t,interaction.user.id,'undo',mid),ephemeral=True)

    @match.command(name='history',description='Retrieve a permanent result and its correction history')
    async def history(self,interaction:discord.Interaction,tournament_id:int,match_id:str):
        t,mid=self.find_match(interaction,tournament_id,match_id)
        m=t['matches'][mid]
        text=result_text(t,m) if m['result'] else match_text(t,m)
        revisions=[r for r in t['revisions'] if r.get('match')==mid]
        text+=f'\nHistorical revisions: {len(revisions)}'
        for rev in revisions:
            text+=f"\n\n**Voided result — {safe(rev['reason'])} by <@{rev['by']}> <t:{int(rev['at'])}:f>**\n"+result_text(t,m,rev['result'])
        await send_text(interaction,text)

    @match.command(name='settings',description='Set the map and region for an unplayed match')
    async def match_settings(self,interaction:discord.Interaction,tournament_id:int,match_id:str,map_name:str,region:str):
        mid=match_id.upper()
        def op(t):
            engine.require(t['status']=='active' and mid in t['matches'],'Active match not found.')
            m=t['matches'][mid]
            engine.require(m['status'] in ('ready','pending'),'Completed match settings are locked.')
            engine.require(1<=len(map_name.strip())<=60 and 1<=len(region.strip())<=40,'Map/region is empty or too long.')
            m['map'],m['region']=map_name.strip(),region.strip()
        await self.mutate(interaction,tournament_id,op)

    @stats.command(name='tournament',description='Placings, MVP and the tournament leaderboard')
    async def tournament_stats(self,interaction:discord.Interaction,tournament_id:int):
        await send_text(interaction,stats_text(self.store.get(tournament_id,interaction.guild.id)))

    @stats.command(name='player',description='Player stats in one tournament, or across this server’s tournament history')
    async def player_stats(self,interaction:discord.Interaction,member:discord.Member,tournament_id:Optional[int]=None):
        tournaments=[self.store.get(tournament_id,interaction.guild.id)] if tournament_id is not None else self.store.all(interaction.guild.id)
        total={'kills':0,'deaths':0,'wins':0,'losses':0,'top_frags':0,'matches':0}
        count=0
        for t in tournaments:
            p=engine.statistics(t)['players'].get(str(member.id))
            if p:
                count+=1
                for key in total:
                    total[key]+=p[key]
        engine.require(count>0,'Player has no registration in these tournaments.')
        await send_text(interaction,f"**{safe(member.display_name)}** · {count} tournament(s)\n{total['kills']} kills / {total['deaths']} deaths · {kd(total['kills'],total['deaths'])} KD\n{total['wins']} wins · {total['losses']} losses · {total['matches']} matches\n{total['top_frags']} top-frag awards (ties included)")


async def setup(bot):
    await bot.add_cog(TournamentCog(bot))
