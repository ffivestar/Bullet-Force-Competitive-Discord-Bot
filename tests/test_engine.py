import copy
import random
import tempfile
import unittest
from collections import Counter
from pathlib import Path

import engine
from database import Database
from store import Store


def tournament(count=4, reset=True):
    t=Store.empty({'id':1,'name':'BFC Test','guild_id':123,'grand_final_reset':reset})
    for i in range(count):
        engine.set_team(t,f'Team {i+1}',[engine.player(i*3+j,f'Player {i*3+j}',j) for j in (1,2,3)])
    return t


def play(t,mid,side=0):
    m=t['matches'][mid]
    stats={uid:[20,10] for tid in m['teams'] for uid in t['teams'][tid]['players']}
    engine.submit(t,mid,[3,1] if side==0 else [1,3],stats,999,m['version'])


class TournamentTests(unittest.TestCase):
    def test_every_size_and_both_final_policies(self):
        for count in range(2,33):
            for reset in (True,False):
                for seed in range(6):
                    with self.subTest(count=count,reset=reset,seed=seed):
                        rng=random.Random(seed)
                        t=tournament(count,reset)
                        engine.start(t)
                        played=0
                        while t['status']!='complete':
                            ready=[m for m in t['matches'].values() if m['status']=='ready']
                            self.assertTrue(ready,'Bracket deadlocked')
                            participants=[tid for m in ready for tid in m['teams']]
                            self.assertEqual(len(participants),len(set(participants)),'Team is in two active matches')
                            losses=engine.statistics(t)['teams']
                            for tid in participants:
                                self.assertLess(losses[tid]['losses'],2)
                            m=rng.choice(ready)
                            self.assertNotEqual(*m['teams'])
                            play(t,m['id'],rng.randrange(2))
                            played+=1
                            self.assertLessEqual(played,2*count-1)
                        losses=engine.statistics(t)['teams']
                        if reset:
                            self.assertLess(losses[t['champion']]['losses'],2)
                            self.assertTrue(all(v['losses']==2 for tid,v in losses.items() if tid!=t['champion']))
                        self.assertIn(played,(2*count-2,2*count-1))
                        self.assertEqual(sum(p['matches'] for p in engine.statistics(t)['players'].values()),played*6)

    def test_grand_final_reset(self):
        for side in (0,1):
            t=tournament(2); engine.start(t); play(t,'W1')
            play(t,'G1',side)
            self.assertEqual(t['matches']['G2']['status'],'skipped' if side==0 else 'ready')
            if side:
                play(t,'G2')
            self.assertEqual(t['status'],'complete')

    def test_balanced_pool_validation(self):
        t=tournament(2); t['teams']={}
        engine.randomize(t)
        self.assertEqual(len(t['teams']),2)
        for team in t['teams'].values():
            self.assertEqual(sorted(t['players'][uid]['tier'] for uid in team['players']),[1,2,3])
        with self.assertRaises(engine.RuleError):
            engine.randomize(t)
        t['teams']={}; t['players']['1']['tier']=None
        with self.assertRaises(engine.RuleError):
            engine.randomize(t)

    def test_registration_validation(self):
        t=tournament(2)
        with self.assertRaises(engine.RuleError):
            engine.set_team(t,'Other',[engine.player(1,'a'),engine.player(80,'b'),engine.player(81,'c')])
        with self.assertRaises(engine.RuleError):
            engine.set_team(t,'Other',[engine.player(80,'a')]*3)
        t['enforce_tiers']=True
        with self.assertRaises(engine.RuleError):
            engine.set_team(t,'Other',[engine.player(i,str(i)) for i in (80,81,82)])
        engine.add_players(t,[engine.player(100,'Unassigned',1)])
        with self.assertRaises(engine.RuleError):
            engine.start(t)
        engine.remove_player(t,'100'); engine.start(t)
        with self.assertRaises(engine.RuleError):
            engine.remove_player(t,'1')

    def test_undo_descendants_and_replay(self):
        t=tournament(8); engine.start(t)
        while t['status']!='complete':
            play(t,next(k for k,m in t['matches'].items() if m['status']=='ready'))
        before=copy.deepcopy(t)
        expected=engine.affected_matches(t,'W1')
        engine.undo(t,'W1',44)
        self.assertIsNone(t['champion'])
        self.assertEqual(t['status'],'active')
        for mid,m in t['matches'].items():
            if mid in expected:
                self.assertIsNone(m['result'])
            else:
                self.assertEqual(m['result'],before['matches'][mid]['result'])
        self.assertTrue(t['revisions'])
        play(t,'W1',1)
        while t['status']!='complete':
            play(t,next(k for k,m in t['matches'].items() if m['status']=='ready'))
        self.assertTrue(t['champion'])
        # Stats derive from current results, never from voided audit entries.
        self.assertEqual(sum(p['matches'] for p in engine.statistics(t)['players'].values()),6*sum(bool(m['result']) for m in t['matches'].values()))

    def test_stale_confirmation_and_invalid_stats(self):
        t=tournament(2); engine.start(t)
        m=t['matches']['W1']
        stats={uid:[0,0] for uid in t['players']}
        for scores,bad in [([1,1],stats),([-1,2],stats),([1,2],{}),([1,2],dict(stats,**{'1':[-1,0]}))]:
            with self.assertRaises(engine.RuleError):
                engine.submit(t,'W1',scores,bad,1,0)
        engine.submit(t,'W1',[3,1],stats,1,0)
        with self.assertRaises(engine.RuleError):
            engine.submit(t,'W1',[3,1],stats,1,0)
        engine.undo(t,'W1',1)
        with self.assertRaises(engine.RuleError):
            engine.submit(t,'W1',[3,1],stats,1,0)
        self.assertEqual(engine.kd(10,0),'∞')
        self.assertEqual(engine.kd(0,0),'0.00')

    def test_tied_top_frags(self):
        t=tournament(2); engine.start(t); play(t,'W1')
        self.assertTrue(all(p['top_frags']==1 for p in engine.statistics(t)['players'].values()))


class StoreTests(unittest.TestCase):
    def test_persistence_isolation_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Database(Path(tmp)/'db.sqlite3'); db.connect(); store=Store(db)
            t=store.create(123,'One',99); other=store.create(123,'Two',99)
            self.assertNotEqual(t['id'],other['id'])
            with self.assertRaises(engine.RuleError):
                store.get(t['id'],124)
            stale=store.get(t['id'],123)
            engine.add_players(t,[engine.player(1,'Test',1)]); store.save(t)
            with self.assertRaises(engine.RuleError):
                store.save(stale)
            db.close(); db.connect(); store=Store(db)
            self.assertEqual(store.get(t['id'],123)['players']['1']['name'],'Test')
            db.close()

    def test_migrates_foundation_tournaments(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Database(Path(tmp)/'db.sqlite3'); db.connect()
            db.execute("INSERT INTO tournaments(name,guild_id,created_by) VALUES ('Existing',123,1)")
            store=Store(db)
            self.assertEqual(store.get(1,123)['name'],'Existing')
            Store(db)
            self.assertEqual(len(store.all()),1)
            db.close()


if __name__=='__main__':
    unittest.main()
