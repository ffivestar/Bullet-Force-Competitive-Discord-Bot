from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bfc_bot.database.db import Database
from bfc_bot.database.repositories.matches import MatchRepository
from bfc_bot.database.repositories.players import PlayerRepository


class RankedFoundationTests(unittest.TestCase):
    def test_player_duplicate_checks_and_profile_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "ranked.sqlite3")
            db.connect()
            try:
                players = PlayerRepository(db)
                one = players.create(1, "alice", "PC-5ive", 1000)
                self.assertEqual(one.rating_points, 1000)
                self.assertTrue(players.exists_ign("PC-5ive"))
                self.assertTrue(players.exists_ign("PC-5ive", exclude_discord_id=1) is False)
                self.assertIsNotNone(players.get_by_discord_id(1))
                two = players.create(2, "bob", "PC-Bob", 1000)
                self.assertTrue(players.exists_ign("PC-Bob", exclude_discord_id=1))
                updated = players.update_ign(1, "PC-Alpha")
                self.assertEqual(updated.ign, "PC-Alpha")
            finally:
                db.close()

    def test_player_unregistration_removes_profile_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "ranked.sqlite3")
            db.connect()
            try:
                players = PlayerRepository(db)
                players.create(1, "alice", "PC-5ive", 1000)
                self.assertIsNotNone(players.get_by_discord_id(1))

                deleted = players.delete(1)
                self.assertTrue(deleted)
                self.assertIsNone(players.get_by_discord_id(1))
                self.assertFalse(players.exists_ign("PC-5ive"))
            finally:
                db.close()

    def test_player_stats_accumulate_from_match_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "ranked.sqlite3")
            db.connect()
            try:
                players = PlayerRepository(db)
                players.create(1, "alice", "PC-1", 1000)
                players.create(2, "bob", "PC-2", 1000)

                players.record_match_result(1, kills=12, deaths=3, won=True)
                players.record_match_result(2, kills=4, deaths=11, won=False)

                alice = players.get_by_discord_id(1)
                bob = players.get_by_discord_id(2)

                self.assertIsNotNone(alice)
                self.assertIsNotNone(bob)
                self.assertEqual(alice.matches_played, 1)
                self.assertEqual(alice.wins, 1)
                self.assertEqual(alice.losses, 0)
                self.assertEqual(alice.kills, 12)
                self.assertEqual(alice.deaths, 3)
                self.assertEqual(bob.matches_played, 1)
                self.assertEqual(bob.wins, 0)
                self.assertEqual(bob.losses, 1)
                self.assertEqual(bob.kills, 4)
                self.assertEqual(bob.deaths, 11)
            finally:
                db.close()

    def test_player_stats_can_be_fully_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "ranked.sqlite3")
            db.connect()
            try:
                players = PlayerRepository(db)
                players.create(1, "alice", "PC-1", 1000)

                updated = players.update_stats(
                    1,
                    matches_played=12,
                    wins=8,
                    losses=4,
                    kills=33,
                    deaths=22,
                    rating_points=1400,
                )

                self.assertIsNotNone(updated)
                self.assertEqual(updated.matches_played, 12)
                self.assertEqual(updated.wins, 8)
                self.assertEqual(updated.losses, 4)
                self.assertEqual(updated.kills, 33)
                self.assertEqual(updated.deaths, 22)
                self.assertEqual(updated.rating_points, 1400)
            finally:
                db.close()

    def test_match_repository_tracks_active_queues_and_unique_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "ranked.sqlite3")
            db.connect()
            try:
                players = PlayerRepository(db)
                matches = MatchRepository(db)
                players.create(1, "alice", "PC-1")
                players.create(2, "bob", "PC-2")
                players.create(3, "charlie", "PC-3")
                players.create(4, "dana", "PC-4")

                match_one = matches.create_match(1, 2, "QUEUING", "TDM")
                match_two = matches.create_match(2, 2, "QUEUING", "TDM")
                self.assertNotEqual(match_one.id, match_two.id)

                matches.add_participant(match_one.id, 1, "PC-1", 1, "2026-01-01T00:00:00")
                matches.add_participant(match_one.id, 2, "PC-2", 1, "2026-01-01T00:00:01")
                matches.add_participant(match_two.id, 3, "PC-3", 1, "2026-01-01T00:00:02")

                self.assertEqual(matches.participant_count(match_one.id), 2)
                self.assertTrue(matches.player_in_active_match(1))
                self.assertTrue(matches.player_in_active_match(3))
                self.assertFalse(matches.player_in_active_match(4))
                self.assertTrue(matches.has_player_in_match(match_one.id, 2))
                self.assertFalse(matches.has_player_in_match(match_two.id, 2))
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
