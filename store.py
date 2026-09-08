"""Atomic, versioned SQLite tournament documents and legacy foundation migration."""
from __future__ import annotations

import json
from engine import require


class Store:
    def __init__(self, database):
        self.db = database
        self.db.execute('CREATE TABLE IF NOT EXISTS tournament_state (id INTEGER PRIMARY KEY REFERENCES tournaments(id), revision INTEGER NOT NULL DEFAULT 0, payload TEXT NOT NULL)')
        for row in self.db.fetch_all('SELECT * FROM tournaments WHERE id NOT IN (SELECT id FROM tournament_state)'):
            state = self.empty(dict(row))
            # Preserve any teams from the foundation database.
            for team in self.db.fetch_all('SELECT * FROM teams WHERE tournament_id = ?', (row['id'],)):
                members = self.db.fetch_all('SELECT * FROM team_members WHERE team_id = ?', (team['id'],))
                tid = str(team['id'])
                state['teams'][tid] = {'id': tid, 'name': team['name'], 'players': [str(p['user_id']) for p in members]}
                for p in members:
                    state['players'][str(p['user_id'])] = {'id': str(p['user_id']), 'name': p['display_name'], 'tier': p['tier']}
                state['next_team'] = max(state['next_team'], int(tid)+1)
            require(not self.db.fetch_one('SELECT id FROM matches WHERE tournament_id = ?', (row['id'],)),
                    'Legacy match data found. Back up the database and migrate these results before running this version.')
            self.db.execute('INSERT INTO tournament_state(id,payload) VALUES (?,?)', (row['id'], json.dumps(state)))

    @staticmethod
    def empty(row):
        return {'id': row['id'], 'name': row['name'], 'guild_id': row['guild_id'], 'status': 'registration',
                'grand_final_reset': bool(row['grand_final_reset']), 'enforce_tiers': False,
                'region': 'EU', 'map': 'Woods', 'players': {}, 'teams': {}, 'next_team': 1,
                'matches': {}, 'revisions': [], 'champion': None, 'runner_up': None,
                'board_channel': None, 'board_message': None, 'rooms': {}, 'archives': {},
                'cleanup': [], 'revision': 0}

    def create(self, guild, name, actor, reset=True, region='EU', map_name='Woods', enforce_tiers=False):
        require(1 <= len(name.strip()) <= 80, 'Tournament name must contain 1–80 characters.')
        require(1 <= len(region.strip()) <= 40 and 1 <= len(map_name.strip()) <= 60, 'Region/map cannot be empty or too long.')
        conn = self.db.connection
        with conn:
            cur = conn.execute('INSERT INTO tournaments(name,guild_id,created_by,grand_final_reset) VALUES (?,?,?,?)', (name.strip(), guild, actor, int(reset)))
            t = self.empty({'id': cur.lastrowid, 'name': name.strip(), 'guild_id': guild, 'grand_final_reset': reset})
            t.update(region=region.strip(), map=map_name.strip(), enforce_tiers=enforce_tiers)
            conn.execute('INSERT INTO tournament_state(id,payload) VALUES (?,?)', (t['id'], json.dumps(t)))
        return t

    def get(self, tid, guild):
        row = self.db.fetch_one('SELECT s.payload,s.revision FROM tournament_state s JOIN tournaments t ON t.id=s.id WHERE s.id=? AND t.guild_id=?', (tid, guild))
        require(row is not None, 'Tournament not found in this server.')
        t = json.loads(row['payload'])
        t['revision'] = row['revision']
        return t

    def all(self, guild=None):
        rows = self.db.fetch_all('SELECT id,guild_id FROM tournaments' + (' WHERE guild_id=?' if guild is not None else '') + ' ORDER BY id DESC', (guild,) if guild is not None else ())
        return [self.get(row['id'], row['guild_id']) for row in rows]

    def save(self, t):
        conn = self.db.connection
        with conn:
            cur = conn.execute('UPDATE tournament_state SET payload=?,revision=revision+1 WHERE id=? AND revision=?', (json.dumps(t), t['id'], t['revision']))
            require(cur.rowcount == 1, 'Tournament changed; please retry your command.')
            conn.execute('UPDATE tournaments SET status=? WHERE id=?', (t['status'], t['id']))
        t['revision'] += 1
