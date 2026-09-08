"""Pure tournament rules. No Discord calls; all mutations are persisted by Store."""
from __future__ import annotations

import copy
import random
import time
from collections import Counter


class RuleError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise RuleError(message)


def registration(t):
    require(t['status'] == 'registration', 'Teams and players are locked after the tournament starts.')


def player(uid, name, tier=None):
    return {'id': str(uid), 'name': name, 'tier': tier}


def add_players(t, players):
    registration(t)
    ids = [p['id'] for p in players]
    require(len(ids) == len(set(ids)), 'A player was supplied more than once.')
    require(not set(ids) & set(t['players']), 'One or more players are already in the pool.')
    require(len(t['players']) + len(players) <= 96, 'Maximum: 96 players (32 teams).')
    for p in players:
        t['players'][p['id']] = p


def remove_player(t, uid):
    registration(t)
    require(uid in t['players'], 'Player is not registered.')
    require(not any(uid in team['players'] for team in t['teams'].values()), 'Remove the player from their team first.')
    del t['players'][uid]


def set_team(t, name, players, team_id=None):
    registration(t)
    name = name.strip()
    require(1 <= len(name) <= 40, 'Team names must contain 1–40 characters.')
    require(len(players) == 3 and len({p['id'] for p in players}) == 3, 'A team needs exactly three different players.')
    if team_id:
        require(team_id in t['teams'], 'Team not found.')
    require(not any(v['name'].casefold() == name.casefold() for k, v in t['teams'].items() if k != team_id), 'Team name already exists.')
    used = {uid for k, team in t['teams'].items() if k != team_id for uid in team['players']}
    require(not used.intersection(p['id'] for p in players), 'A player is already on another team.')
    if t['enforce_tiers']:
        require(sorted(p['tier'] or 0 for p in players) == [1, 2, 3], 'This tournament requires one player from each tier.')
    require(team_id or len(t['teams']) < 32, 'Maximum: 32 teams.')
    require(len(set(t['players']) | {p['id'] for p in players}) <= 96, 'Maximum: 96 registered players; remove unused players first.')
    if not team_id:
        team_id = str(t['next_team'])
        t['next_team'] += 1
    for p in players:
        t['players'][p['id']] = p
    t['teams'][team_id] = {'id': team_id, 'name': name, 'players': [p['id'] for p in players]}
    return team_id


def randomize(t):
    registration(t)
    require(not t['teams'], 'Delete existing teams before randomising; the pool is retained.')
    tiers = [[p for p in t['players'].values() if p['tier'] == tier] for tier in (1, 2, 3)]
    require(sum(map(len, tiers)) == len(t['players']), 'Every pooled player must have exactly one Tier 1, Tier 2 or Tier 3 role.')
    require(len(tiers[0]) == len(tiers[1]) == len(tiers[2]) and len(tiers[0]) >= 2,
            'Need equal tier counts and at least two players in each tier (six players total).')
    for pool in tiers:
        random.SystemRandom().shuffle(pool)
    for i, members in enumerate(zip(*tiers), 1):
        set_team(t, f'Team {i}', list(members))


def start(t):
    registration(t)
    require(2 <= len(t['teams']) <= 32, 'Register 2–32 teams before starting.')
    assigned = [uid for team in t['teams'].values() for uid in team['players']]
    require(len(assigned) == len(set(assigned)), 'Players cannot appear on multiple teams.')
    require(set(assigned) == set(t['players']), 'Some pooled players have no team. Assign or remove them before starting.')
    require(all(len(team['players']) == 3 for team in t['teams'].values()), 'Every team must have three players.')
    seeds = list(t['teams'])
    random.SystemRandom().shuffle(seeds)
    size = 1 << (len(seeds) - 1).bit_length()
    # Standard seed ordering distributes byes evenly, without empty first-round pairs.
    order = [1, 2]
    while len(order) < size:
        total = 2 * len(order) + 1
        order = [x for seed in order for x in (seed, total - seed)]
    slots = [seeds[s - 1] if s <= len(seeds) else None for s in order]
    t['seeds'] = seeds
    t['matches'] = {}
    counts = Counter()

    def add(bracket, rnd, sources):
        counts[bracket] += 1
        mid = f'{bracket}{counts[bracket]}'
        t['matches'][mid] = {'id': mid, 'bracket': bracket, 'round': rnd, 'sources': sources,
                            'teams': [None, None], 'status': 'pending', 'result': None,
                            'winner': None, 'loser': None, 'version': 0,
                            'map': t['map'], 'region': t['region']}
        return mid

    def ref(mid, outcome='winner'):
        return [outcome, mid]

    winners = []
    previous = [add('W', 1, [['seed', slots[i]], ['seed', slots[i+1]]]) for i in range(0, size, 2)]
    winners.append(previous)
    while len(previous) > 1:
        previous = [add('W', len(winners)+1, [ref(previous[i]), ref(previous[i+1])]) for i in range(0, len(previous), 2)]
        winners.append(previous)
    if size == 2:
        lower = ref(winners[0][0], 'loser')
    else:
        previous = [add('L', 1, [ref(winners[0][i], 'loser'), ref(winners[0][i+1], 'loser')]) for i in range(0, size//2, 2)]
        for r in range(1, len(winners)):
            # Cross-feed new losers to avoid immediate rematches where possible.
            drops = list(reversed(winners[r]))
            previous = [add('L', 2*r, [ref(previous[i]), ref(drops[i], 'loser')]) for i in range(len(previous))]
            if r < len(winners)-1:
                previous = [add('L', 2*r+1, [ref(previous[i]), ref(previous[i+1])]) for i in range(0, len(previous), 2)]
        lower = ref(previous[0])
    final = add('G', 1, [ref(winners[-1][0]), lower])
    if t['grand_final_reset']:
        add('G', 2, [ref(final, 'loser'), ref(final)])
    t['status'] = 'active'
    recompute(t)


def recompute(t):
    t['champion'] = None
    t['runner_up'] = None
    t['status'] = 'active'
    for m in t['matches'].values():
        ready = True
        teams = []
        for kind, source in m['sources']:
            if kind == 'seed':
                teams.append(source)
            else:
                parent = t['matches'][source]
                ready &= parent['status'] in ('complete', 'bye')
                teams.append(parent[kind] if ready else None)
        m['teams'] = teams
        m['winner'] = m['loser'] = None
        if m['id'] == 'G2':
            first = t['matches']['G1']
            if first['status'] != 'complete':
                m['status'] = 'pending'
                continue
            if first['winner'] == first['teams'][0]:
                m['status'] = 'skipped'
                t['champion'], t['runner_up'] = first['winner'], first['loser']
                continue
        if not ready:
            m['status'] = 'pending'
        elif None in teams:
            m['status'] = 'bye'
            m['winner'] = next((team for team in teams if team is not None), None)
        elif m['result']:
            r = m['result']
            require(r['teams'] == teams, 'Stored result conflicts with bracket participants.')
            win = 0 if r['scores'][0] > r['scores'][1] else 1
            m['winner'], m['loser'] = teams[win], teams[1-win]
            m['status'] = 'complete'
        else:
            m['status'] = 'ready'
        if m['bracket'] == 'G' and m['status'] == 'complete':
            if m['id'] == 'G2' or not t['grand_final_reset'] or m['winner'] == teams[0]:
                t['champion'], t['runner_up'] = m['winner'], m['loser']
    if t['champion']:
        t['status'] = 'complete'


def validate_result(t, mid, scores, stats):
    require(mid in t['matches'], 'Match not found.')
    m = t['matches'][mid]
    require(m['status'] == 'ready', 'This match is not awaiting a result. Undo an existing result first.')
    require(len(scores) == 2 and all(type(s) is int and 0 <= s <= 999 for s in scores), 'Scores must be whole numbers between 0 and 999.')
    require(scores[0] != scores[1], 'A tournament match cannot end in a draw.')
    expected = {uid for tid in m['teams'] for uid in t['teams'][tid]['players']}
    require(set(stats) == expected, 'Supply kills/deaths for all six players, exactly once.')
    require(all(len(v) == 2 and all(type(n) is int and 0 <= n <= 9999 for n in v) for v in stats.values()), 'Kills/deaths must be whole numbers from 0 to 9999.')


def submit(t, mid, scores, stats, actor, version):
    m = t['matches'].get(mid)
    require(m is not None and m['version'] == version, 'The match changed. Open a fresh result form.')
    validate_result(t, mid, scores, stats)
    m['result'] = {'teams': list(m['teams']), 'scores': list(scores), 'stats': copy.deepcopy(stats),
                   'by': str(actor), 'at': time.time()}
    m['version'] += 1
    recompute(t)


def affected_matches(t, mid):
    require(mid in t['matches'], 'Match not found.')
    affected = {mid}
    for key, m in t['matches'].items():
        if any(kind != 'seed' and source in affected for kind, source in m['sources']):
            affected.add(key)
    return [key for key in t['matches'] if key in affected]


def undo(t, mid, actor):
    require(t['matches'].get(mid, {}).get('result') is not None, 'That match has no recorded result.')
    affected = affected_matches(t, mid)
    for key in affected:
        m = t['matches'][key]
        if m['result']:
            t['revisions'].append({'match': key, 'result': copy.deepcopy(m['result']), 'by': str(actor), 'at': time.time(), 'reason': f'Undo {mid}'})
        m['result'] = None
        m['version'] += 1
    recompute(t)
    return affected


def kd(kills, deaths):
    return f'{kills / deaths:.2f}' if deaths else ('∞' if kills else '0.00')


def statistics(t):
    players = {uid: {'name': p['name'], 'kills': 0, 'deaths': 0, 'wins': 0, 'losses': 0, 'top_frags': 0, 'matches': 0} for uid, p in t['players'].items()}
    teams = {tid: {'wins': 0, 'losses': 0} for tid in t['teams']}
    for m in t['matches'].values():
        if not m['result']:
            continue
        r = m['result']
        for tid in m['teams']:
            won = tid == m['winner']
            teams[tid]['wins' if won else 'losses'] += 1
            top = max(r['stats'][uid][0] for uid in t['teams'][tid]['players'])
            for uid in t['teams'][tid]['players']:
                k, d = r['stats'][uid]
                p = players[uid]
                p['kills'] += k
                p['deaths'] += d
                p['matches'] += 1
                p['wins' if won else 'losses'] += 1
                p['top_frags'] += int(k == top)
    third = None
    if t.get('champion'):
        lower = [m for m in t['matches'].values() if m['bracket'] == 'L' and m['result']]
        if lower:
            third = lower[-1]['loser']
    return {'players': players, 'teams': teams, 'third': third}
