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
