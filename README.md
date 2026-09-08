# BFC Tournament Bot

Discord tournament infrastructure for the Bullet Force Competitive community.

This project provides a clean foundation for tournament registration, match operations, and competitive statistics. It keeps Discord channel management, tournament rules, and persistence in separate modules so the bot can grow without becoming a single-file application.

## Status

The current release is the tournament foundation. It can create and inspect tournament records, initialise the SQLite database, and prepare private match channels for teams and staff.

### Available now

- `/ping` health check
- `/tournament create` with 3v3 double-elimination metadata
- `/tournament list` and `/tournament view`
- Environment-based configuration with no hardcoded secrets
- SQLite persistence for tournaments, teams, matches, player statistics, and result revisions
- Temporary match text and private voice channels with team and staff permissions
- Stored fields for scores, kills, deaths, calculated KD, top fraggers, and channel IDs

### Planned next

- Tier-aware team registration and balanced randomisation
- Manual team creation and duplicate-player validation
- Bracket seeding and winners/losers advancement
- Match result confirmation and correction workflows
- Permanent match summaries, tournament statistics, and bracket images

## Quick start

### Requirements

- Python 3.11 or newer
- A Discord application and bot token
- A Discord server where the bot can manage channels and use application commands

### Install

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### Configure

```bash
cp .env.example .env
```

Set `DISCORD_TOKEN` in `.env`. The remaining settings are optional:

| Setting | Purpose | Default |
| --- | --- | --- |
| `DATABASE_PATH` | SQLite database location | `data/bfc.sqlite3` |
| `COMMAND_GUILD_ID` | Fast command sync for one test server | Empty |
| `TOURNAMENT_CATEGORY_NAME` | Category for tournament channels | `BFC Tournaments` |
| `MATCH_RESULTS_CHANNEL_NAME` | Results channel name | `match-results` |
| `TOURNAMENT_STAFF_ROLE_NAME` | Staff role for private match access | `Tournament Staff` |
| `BFC_ADMIN_ROLE_NAME` | Administrator role name | `BFC Admin` |
| `GRAND_FINAL_RESET_DEFAULT` | Default grand-final reset setting | `true` |

Never commit `.env` or place the bot token in source code.

### Run

```bash
source .venv/bin/activate
python bot.py
```

The database directory and SQLite file are created automatically on first start.

## Discord setup

1. Create an application in the [Discord Developer Portal](https://discord.com/developers/applications).
2. Add a bot user and copy its token into `.env`.
3. Enable **Server Members Intent** under **Privileged Gateway Intents**.
4. Invite the bot with the `bot` and `applications.commands` scopes.
5. Grant the bot permission to view and send messages, manage channels, connect, and speak.

Set `COMMAND_GUILD_ID` to a test server ID while developing. Leave it empty when you want commands synced globally.

## Commands

```text
/ping
/tournament create name:BFC Season 1 grand_final_reset:true
/tournament list
/tournament view tournament_id:1
```

Creating a tournament currently stores it in registration mode. Bracket generation will be enabled after team registration and validation are implemented.

## Project layout

```text
.
├── bot.py                 # Discord entry point and extension loading
├── config.py              # Environment-backed settings
├── database.py            # SQLite connection and schema creation
├── models.py              # Typed data models
├── repositories.py        # Database reads and writes
├── tournament_service.py  # Tournament application logic
├── discord_channels.py    # Match channel lifecycle
├── engine.py              # Tournament and match domain logic
└── cogs/
	├── general.py        # /ping
	└── tournaments.py    # /tournament commands
```

## Development

Run the repository syntax check before opening a pull request:

```bash
python -m compileall -q .
```

Contributions should keep Discord integration, domain logic, and persistence separated and should never include secrets or generated database files.
