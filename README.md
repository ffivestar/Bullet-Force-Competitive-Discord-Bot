# BFC | Bullet Force Competitive

This repository has been refactored into a fresh ranked matchmaking bot foundation for BFC. The current focus is on registering players, creating ranked queues, generating random teams/map/room details, storing persistent match state, and preparing the data model for future screenshot OCR and rating-point automation.

## Current architecture

- `bot.py`: bot startup, command sync, and bot bootstrapping
- `config.py`: environment-backed settings
- `bfc_bot/`: new ranked bot modules
  - `database/`: SQLite schema and repositories
  - `services/`: queue, map, team, and rating extension points
  - `ui/`: reusable embed helpers
  - `utils/`: permission helpers
  - `commands/`: slash command modules
- `tools/bullet_force_probe/`: isolated research utility for Bullet Force client investigation; not part of the bot runtime

## Keep / refactor / remove summary

### Kept
- `bot.py` startup structure
- `config.py` environment handling
- `.gitignore`, Git metadata, and existing repository state
- general SQLite connection utility patterns
- existing test setup and Python tooling

### Refactored
- The main runtime now loads the new `commands.registration` and `commands.ranked` modules instead of the old tournament-only cogs.
- The old tournament bot is no longer the primary architecture.
- Database structure has been replaced with a simpler ranked foundation for `players`, `ranked_matches`, and `ranked_match_players`.

### Removed from active runtime
- Tournament bracket generation, double-elimination logic, and tournament-specific command flow are no longer loaded by the bot.
- Legacy tournament-only cogs are left in the repository for reference but are not part of the active bot startup.

### Added
- Player registration flow with `/register`, `/profile`, and `/setign`
- Ranked queue flow with `/ranked start`
- Match repositories and SQLite-backed storage
- Team generation, map selection, and match-ready embed generation
- Placeholder rating service for future formula work

## Current slash commands

- `/register`
- `/profile`
- `/setign`
- `/ranked start`
- `/ranked end` (foundation added; currently validates READY matches and marks them completed after confirmation)

## Database schema

The active schema now supports:

### players
- `discord_user_id` (primary key)
- `discord_username`
- `ign` (unique)
- `rating_points`
- `matches_played`
- `wins`
- `losses`
- `kills`
- `deaths`
- `created_at`
- `updated_at`

### ranked_matches
- `id`
- `creator_discord_id`
- `team_size`
- `required_players`
- `status`
- `map_name`
- `game_mode`
- `room_name`
- `room_password`
- `created_at`
- `started_at`
- `completed_at`
- `team_one_json`
- `team_two_json`

### ranked_match_players
- `match_id`
- `discord_user_id`
- `ign_snapshot`
- `team_number`
- `joined_at`

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## .env setup

1. Copy `.env.example` to `.env`
2. Fill in `DISCORD_TOKEN`
3. Optionally set `GUILD_ID` for guild-specific command sync
4. Leave the database path as-is unless you want a custom location

## Start the bot

```bash
source .venv/bin/activate
python bot.py
```

## Planned extension points

- OCR-based screenshot parsing
- Manual stat entry flow
- Final rating-point formula and automatic score updates
- More advanced team balancing based on ranking points
- Persistent recovery for components beyond the current queue view lifecycle

## Notes

- The bot intentionally does not integrate with Bullet Force live-client networking.
- The room name/password are generated for manual recreation by the host.
- The rating system is deliberately left as a placeholder until the final formula is specified.

## Tests

```bash
.venv/bin/python -m unittest discover -s tests -q
.venv/bin/python -m compileall -q bot.py bfc_bot commands tests
```

The current test suite includes the existing legacy checks plus the new ranked foundation checks.
