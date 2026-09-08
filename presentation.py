from __future__ import annotations

import discord
from engine import kd, statistics


def safe(value):
    return discord.utils.escape_markdown(str(value))


def team_name(t, tid):
    return safe(t['teams'][tid]['name']) if tid else 'TBD'


def match_text(t, m):
    lines = [f"**{safe(t['name'])} — {'Winners' if m['bracket']=='W' else 'Losers' if m['bracket']=='L' else 'Grand final'} Round {m['round']}**", '']
    for i, tid in enumerate(m['teams']):
        if i:
            lines.append('\nvs\n')
        lines.append('**'+team_name(t,tid)+'**')
        if tid:
            lines.extend(f'<@{uid}>' for uid in t['teams'][tid]['players'])
    lines.extend(['', f"Region: {safe(m['region'])} | Map: {safe(m['map'])}", f"Tournament: {t['id']} | Match ID: {m['id']}", f"Status: {'Waiting to start / submit result' if m['status']=='ready' else m['status']}"])
    rooms = t['rooms'].get(m['id'], {})
    for key, label in [('a','Team A VC'),('b','Team B VC')]:
        if rooms.get(key):
            lines.append(f"{label}: <#{rooms[key]}>")
    return '\n'.join(lines)


def result_text(t, m, result=None):
    r = result or m['result']
    if not r:
        return f"**{safe(t['name'])} · {m['id']} — RESULT VOIDED**\nAn administrator undid this result or an earlier dependent match. The current bracket is authoritative."
    teams = r['teams']
    winner = teams[0 if r['scores'][0] > r['scores'][1] else 1]
    lines = [f"**{safe(t['name'])} · {m['id']} · {m['bracket']} Round {m['round']}**", f"{team_name(t,teams[0])} **{r['scores'][0]} – {r['scores'][1]}** {team_name(t,teams[1])}", f"Winner: **{team_name(t,winner)}**", f"Map: {safe(r.get('map',m['map']))} | Region: {safe(r.get('region',m['region']))}"]
    for tid in teams:
        lines.append('\n**'+team_name(t,tid)+'**')
        top = max(r['stats'][uid][0] for uid in t['teams'][tid]['players'])
        for uid in t['teams'][tid]['players']:
            k,d = r['stats'][uid]
            lines.append(f"<@{uid}> — {k} K / {d} D · {kd(k,d)} KD" + (' ⭐ Top frag' if k==top else ''))
    if r.get('at'):
        lines.append(f"\nRecorded <t:{int(r['at'])}:f> by <@{r['by']}>")
    if m['bracket']=='W':
        lines.append('Winner advances. Loser → Losers bracket (grand final for a two-team event).')
    elif m['bracket']=='L':
        lines.append('Winner advances. Loser is eliminated.')
    elif m['id']=='G1' and t['grand_final_reset'] and winner==teams[1]:
        lines.append('Grand final reset required: both teams play G2.')
    else:
        lines.append('Tournament champion decided.')
    return '\n'.join(lines)


def teams_text(t):
    lines = [f"**{safe(t['name'])} — Teams**"]
    standings = statistics(t)['teams']
    for tid, team in t['teams'].items():
        members = ', '.join(f"<@{uid}> (T{t['players'][uid]['tier'] or '?'})" for uid in team['players'])
        record = standings[tid]
        status = ' · Eliminated' if record['losses'] >= 2 else ''
        lines.append(f"`{tid}` **{safe(team['name'])}**: {members} · {record['wins']}W/{record['losses']}L{status}")
    used = {uid for team in t['teams'].values() for uid in team['players']}
    unassigned = [f"<@{uid}> (T{p['tier'] or '?'})" for uid,p in t['players'].items() if uid not in used]
    if unassigned:
        lines.append('**Unassigned pool:** '+', '.join(unassigned))
    return '\n'.join(lines)


def stats_text(t):
    s = statistics(t)
    lines = [f"**{safe(t['name'])} — Tournament statistics**"]
    if t.get('champion'):
        lines.extend([f"Champion: {team_name(t,t['champion'])}", f"Runner-up: {team_name(t,t['runner_up'])}", f"3rd place: {team_name(t,s['third']) if s['third'] else 'N/A'}"])
    played = {uid:p for uid,p in s['players'].items() if p['matches']}
    if not played:
        return '\n'.join(lines+['No recorded matches yet.'])
    # Deterministic, documented MVP ranking: kills, then fewer deaths, then wins.
    mvp = max(played,key=lambda uid:(played[uid]['kills'], -played[uid]['deaths'], played[uid]['wins']))
    lines.append(f"Tournament MVP: <@{mvp}> (kills, then fewer deaths, then wins)")
    for label, metric in [('Most kills',lambda p:p['kills']),('Best K/D',lambda p:p['kills']/p['deaths'] if p['deaths'] else float('inf') if p['kills'] else 0),('Most top frags',lambda p:p['top_frags'])]:
        best=max(metric(p) for p in played.values())
        leaders=', '.join(f'<@{uid}>' for uid,p in played.items() if metric(p)==best)
        lines.append(f'{label}: {leaders}')
    best_wins=max(v['wins'] for v in s['teams'].values())
    lines.append('Most team match wins: '+', '.join(team_name(t,tid) for tid,v in s['teams'].items() if v['wins']==best_wins)+f' ({best_wins})')
    lines.append('\n**Leaderboard — kills / deaths · KD · W–L · top frags**')
    for uid,p in sorted(played.items(),key=lambda item:(-item[1]['kills'],item[1]['deaths'])):
        lines.append(f"<@{uid}>: {p['kills']}/{p['deaths']} · {kd(p['kills'],p['deaths'])} · {p['wins']}–{p['losses']} · {p['top_frags']}")
    return '\n'.join(lines)


async def send_text(interaction, text, ephemeral=True):
    # Paginate by lines, splitting a single long pool line when necessary.
    chunks=[]
    current=''
    for line in text.splitlines():
        while len(line)>1800:
            if current:
                chunks.append(current); current=''
            chunks.append(line[:1800]); line=line[1800:]
        if len(current)+len(line)+1>1900:
            chunks.append(current); current=''
        current += line+'\n'
    if current:
        chunks.append(current)
    for chunk in chunks or ['No data.']:
        if interaction.response.is_done():
            await interaction.followup.send(chunk,ephemeral=ephemeral,allowed_mentions=discord.AllowedMentions.none())
        else:
            await interaction.response.send_message(chunk,ephemeral=ephemeral,allowed_mentions=discord.AllowedMentions.none())
