# BFC Ranked Matchmaking Bot

This repository is now a ranked matchmaking bot for Bullet Force. The active bot focuses on player registration, ranked queues, generated teams and match details, persistent match state, and a clean foundation for future OCR and rating automation.

## What is currently in the bot

- `/register`: registers a Discord account to a Bullet Force IGN
- `/profile`: shows the registered player profile and stats; optionally accepts another Discord user to view their public profile
- `/setign`: updates a registered IGN
- `/unregister`: removes a registration and clears the server nickname if the bot has permission
- `/ranked start`: opens the ranked format chooser
- `/ranked end`: marks a READY match as complete and prompts the owner to use `/ranked record-result`
- `/ranked record-result`: review a completed match by match ID, apply final rating changes, and post a public result announcement
- `/ranked wipe`: owner-only command that resets all ranked match history and player stats
- `/ranked edit-stats`: owner-only command that fully overwrites a player profile’s stats and rating

## Ranked flow

1. A user runs `/register` and enters their Bullet Force IGN.
2. The bot stores the player in SQLite and, when allowed, updates the Discord server nickname to match the IGN.
3. A user runs `/ranked start` and picks a format such as `1v1`, `2v2`, `3v3`, `4v4`, `5v5`, or `6v6`.
4. The bot creates a ranked queue, lets players join or leave, and tracks participants.
5. Once enough players join, the bot generates teams, rolls a map, creates a room name/password, and updates the queue message to a READY match embed.
6. Staff or participants can run `/ranked end` for the match ID to confirm completion.
7. After a match is finished, the owner runs `/ranked record-result <match_id> <winner_team> [winner_top_frag] [loser_top_frag]` to review, confirm, and publish the public result announcement.

## Current architecture

- `bot.py`: bot startup, command sync, and setup
- `config.py`: environment-backed configuration loading
- `commands/registration.py`: registration, profile, setign, unregister commands
- `commands/ranked.py`: ranked queue flow and match lifecycle
- `bfc_bot/database/`: SQLite schema and repositories
- `bfc_bot/services/`: team balancing, map-selection, and ranked logic extensions
- `bfc_bot/ui/`: embed builders for registration, queues, and ready matches
- `tools/bullet_force_probe/`: isolated Bullet Force research utility; not part of the runtime bot

## Database behavior

The bot uses SQLite for persistent state and stores these tables:

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

The repository currently persists queue state, participants, and result payloads so the bot can continue presenting status updates and ready-match details after a restart.

## Setup and installation

### 1) Create a Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Create a local environment file

Copy `.env.example` to `.env` and fill in the values.

### 3) Run the bot

```bash
./run.sh
```

Or:

```bash
source .venv/bin/activate
python bot.py
```

## Environment variables

The current runtime expects:

- `DISCORD_TOKEN`: bot token
- `DATABASE_PATH`: SQLite database path
- `GUILD_ID`: optional guild ID for guild-only command sync
- `COMMAND_GUILD_ID`: optional development guild ID for guild sync during testing

## Important notes

- The bot does not currently integrate directly with the Bullet Force client.
- Match room names and passwords are generated for manual host recreation.
- Nickname updates require the bot to have the `Manage Nicknames` permission in the Discord server.
- Rank roles and server nicknames are synced from the player’s stored rating whenever a player’s profile changes or a match result is published.
- OCR-based screenshot parsing and automatic rating automation are planned future features, but they are not required for the current ranked matchmaking flow.

## Planned future features

- OCR-based screenshot parsing for match results
- Automatic rating-point calculations and leaderboard updates
- More advanced team balancing based on ratings
- Deeper persistent recovery and richer queue management

## Tests

```bash
.venv/bin/python -m unittest discover -s tests -q
.venv/bin/python -m compileall .
```

## Current repository status

The repository is intentionally kept as a single project and a single GitHub repository. The old tournament-only flow has been removed from the active runtime, while the useful startup/config/test scaffolding has been retained.
