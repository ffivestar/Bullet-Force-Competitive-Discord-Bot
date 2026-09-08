# BFC Tournament Bot

Tournament-only Discord bot for three-player teams. Supports balanced random teams, manual teams, double elimination, bracket PNGs, match rooms, confirmed results, corrections, and permanent player history. No Bullet Force API connection is required: staff enter scoreboard results.

**Project updates:** [Read the dated changelog](CHANGELOG.md) for feature updates, fixes, validation results, and earlier commits.

## Get running

Dependencies have been installed in this folder’s `.venv`. On a new machine, run `./setup.sh` (Python 3.9+; Python 3.11 or newer recommended). The exact dependency versions tested here are in `requirements-lock.txt`; use `pip install -r requirements-lock.txt` to reproduce them.

1. Create a bot in the [Discord Developer Portal](https://discord.com/developers/applications). On its **Bot** page, enable **Server Members Intent**. Message Content Intent is not needed.
2. Invite it with the `bot` and `applications.commands` scopes. Grant **Manage Channels**, **Manage Roles** (channel permission overwrites), **View Channels**, **Send Messages**, **Read Message History**, **Attach Files**, **Embed Links**, **Connect**, and **Speak**. Give it these permissions in the channel where you will start the tournament too. The bot does not join voice or transmit audio.
3. Copy `.env.example` to `.env` if you have not run setup. Set `DISCORD_TOKEN` to your bot token and set `GUILD_ID` to your development Discord server ID for immediate server command sync. Leave it empty for global commands, which can take time to appear. Never share or commit `.env`.
4. Create **BFC Admin**, **Tournament Staff**, **Tier 1**, **Tier 2**, and **Tier 3** roles. Give staff/admin roles to the appropriate moderators and exactly one tier role to each player using random teams. Role names can be changed in `.env`. Discord administrators also have full bot access.
5. Run `./run.sh`. Keep the process running and the computer awake; stopping it takes the bot offline. Use one bot process per database. The SQLite database is created automatically at `data/bfc.sqlite3`.
6. Check `/ping`, then follow one of the workflows below.

**Live Discord verification still requires your real token, invited bot, and server roles.** Automated checks do not log in or create channels in a real server.

## Token and launch details

Paste your token into `.env` on this exact line:

```dotenv
DISCORD_TOKEN=PASTE_MY_TOKEN_HERE
```

Replace only `PASTE_MY_TOKEN_HERE` with the token from the Discord Developer Portal. Do not paste the token into `bot.py`, `.env.example`, or any committed file.

From Terminal on macOS, start the bot with:

```bash
./run.sh
```

The direct equivalent is `.venv/bin/python bot.py`. The bot loads `.env` from the project directory, reports a clear error if the token is missing, and syncs commands to `GUILD_ID` when set. Without that setting, commands sync globally and may take longer to appear.

For development, replace the blank value on this line in `.env`:

```dotenv
GUILD_ID=YOUR_DISCORD_SERVER_ID
```

Use the server ID from Discord Developer Mode. The legacy `COMMAND_GUILD_ID` setting is still accepted for compatibility, but `GUILD_ID` takes precedence.

## Invite this bot application

Use the application that owns the token in the [Discord Developer Portal](https://discord.com/developers/applications): open **OAuth2 > URL Generator**, select these scopes, and generate the invite URL:

- `bot`
- `applications.commands`

Grant these bot permissions when generating the URL:

- Manage Channels
- Manage Roles
- View Channels
- Send Messages
- Read Message History
- Attach Files
- Embed Links
- Connect
- Speak

Open the generated URL, choose the BFC Discord server, review the permissions, and authorize the invitation. The bot does not join voice calls or transmit audio; `Connect` and `Speak` are required so it can create and manage the private team voice channels.

## Balanced random teams

```text
/tournament create name:BFC Cup grand_final_reset:true region:EU map_name:Woods
/players add tournament_id:1 names:@Five @Rex @Ash @Ace @Kai @Leo
/teams randomize tournament_id:1
/tournament teams tournament_id:1
/tournament start tournament_id:1
```

The example six players need two Tier 1, two Tier 2, and two Tier 3 roles. Randomisation refreshes their roles, shuffles each tier separately, and produces exactly one player from each tier per team. Unequal tier counts, missing/multiple tier roles, duplicates, and bot accounts are rejected. You may add players in batches. Delete existing teams before randomising again; their players remain in the pool.

Names accept Discord mentions or numeric IDs separated by spaces/commas. Exact Discord usernames/display names may be entered separated by commas or newlines; ambiguous names are rejected. Mentions are the most reliable option.

## Manual teams

```text
/tournament create name:BFC Manual Cup enforce_manual_tiers:false
/team create tournament_id:2 name:Velocity players:@Five @Rex @Ash
/team create tournament_id:2 name:Nova players:@Ace @Kai @Leo
/tournament teams tournament_id:2
/tournament start tournament_id:2
```

Each team must contain exactly three different server members. A player cannot belong to two teams in the same tournament. Manual teams do not require tiers unless `enforce_manual_tiers:true` is selected. Team creation adds the players to the pool automatically. Editing/deleting a team leaves removed players in the pool; assign them elsewhere or use `/players remove` before starting.

Start supports **2–32 teams**, randomly seeds the bracket, automatically advances byes, and locks rosters. Every registered player must be assigned. Each tournament has its own IDs and history, so multiple tournaments can run concurrently.

## Match rooms and results

Starting creates one permanent bracket post in the channel where `/tournament start` is used. Its **View Teams**, **View Matches**, **Player Stats**, and **Leaderboard** buttons survive restarts. Each result edits the same bracket post.

Every ready matchup gets:

- A text channel with both rosters, round, match ID, region, map, status, and voice links. Spectators can read; only the six players, staff, admins, and bot can write.
- Two private team voice channels. Each team sees its own voice channel; staff/admin roles see both. Discord users with the Administrator permission always bypass channel restrictions.

The default map and region are Woods/EU; change them at tournament creation or for individual unplayed matches with `/match settings`. The bot creates the next round’s rooms when both participants are known. Category overflow is handled when multiple rooms are needed. Discord’s server-wide channel limits still apply.

Inside a match text channel:

```text
/match result
```

Outside the room:

```text
/match result tournament_id:1 match_id:W1
```

Enter the two scores as `3, 1`. The form shows three named player rows for each team:

```text
Five | 123456789012345678 K D
```

Replace `K D` with kills and deaths, for example `24 10`. Keep the player IDs intact. The bot checks all six players, calculates K/D, determines the winning team from the scores, and awards top frag to every player tied for most kills on each team. Zero-death K/D is `∞` for positive kills and `0.00` for 0/0.

Review the full result, then press **Confirm Result** or **Edit**. Results are saved only on confirmation. A stale/double submission is rejected. Staff can reopen the form if its ten-minute confirmation window expires or the bot restarts before confirmation.

After confirmation the bot saves the scores and all six players’ stats, advances winners/losers, updates the bracket, writes a permanent post in `match-results`, and creates the next ready matches. The old match room announces the result and closes with both VCs **45 seconds later**. Cleanup deadlines and pending Discord delivery survive restarts; failed delivery retries every 20 seconds. Records remain in SQLite after channels are deleted.

With final reset enabled, the losers-bracket champion must defeat the undefeated finalist twice. With it disabled, one grand final determines the champion, even if the losing finalist previously had no losses.

## Corrections and history

```text
/match undo tournament_id:1 match_id:W1
/match history tournament_id:1 match_id:W1
```

Undo requires BFC Admin or Discord Administrator and shows a confirmation listing affected matches. It clears the chosen result **and all dependent results**, recalculates statistics, marks old archive posts as voided, retires invalidated rooms, and rebuilds ready matchups. Unrelated results remain intact. Resubmit the corrected original result and any invalidated downstream results. Original scoreboards, recorder, correction author, timestamps, map and region remain in the audit history.

Tournament deletion is an explicitly confirmed cancellation: it closes match rooms while retaining all historical data.

## Commands and access

| Access | Commands |
| --- | --- |
| Everyone | `/ping`, `/tournament list`, `/tournament view`, `/tournament teams`, `/tournament bracket`, `/match view`, `/match history`, `/stats player`, `/stats tournament` |
| Tournament Staff, BFC Admin, Discord Administrator | `/players add`, `/players remove`, `/teams randomize`, `/team create`, `/team edit`, `/team delete`, `/tournament start`, `/tournament sync`, `/match result`, `/match settings` |
| BFC Admin, Discord Administrator | `/tournament create`, `/tournament settings`, `/tournament delete`, `/match undo` |

Runtime role checks protect mutations even when slash commands are visible to everyone. Confirmation buttons are restricted to the requesting moderator and recheck their current access.

`/stats tournament` reports champion, runner-up, third place (where applicable), MVP, most kills, best K/D, most top frags, most team match wins, and a player leaderboard. MVP ranks total kills first, then fewer deaths, then match wins; a remaining exact tie uses registration order. Award leaders include ties. Byes do not contribute match wins or stats. `/stats player` without a tournament ID aggregates that player’s recorded history within this Discord server.

## Recovery and operations

- `/tournament sync tournament_id:1` retries channel/archive/bracket updates immediately.
- `/tournament sync tournament_id:1 restore_board_here:true` recreates or moves the board to the current channel if its post/channel was removed. Use this only when you want a replacement; the old post in another channel is not deleted automatically.
- If a channel operation fails, check the bot’s channel permissions and the server’s available channel capacity. The result stays saved and delivery retries automatically. Logs contain the Discord error.
- Back up `data/bfc.sqlite3` regularly while the bot is stopped. It contains all tournament state, results, pending cleanup, and audit history. Restore the database before restarting the bot.
- Stop with Ctrl+C. Run a single process against each database.
- The bot manages text/voice channels; it does not need PyNaCl or Discord voice playback libraries. A voice-support warning at startup does not prevent channel creation.

## Implementation and checks

- `engine.py`: pure team/bracket/result/undo/statistics rules.
- `store.py`: atomic SQLite tournament documents with revision checks; migrates foundation tournament records.
- `cogs/tournaments.py`: slash commands, forms, permission checks, persistent buttons, retry worker.
- `discord_channels.py`: recoverable channel creation, result archives, delayed cleanup, bracket delivery.
- `rendering.py`: charcoal BFC bracket PNGs rendered from the actual match graph with Pillow.
- `presentation.py`: scoreboards, team lists, statistics, and paginated responses.
- `database.py`: SQLite connection and original foundation schema; `tournament_state` documents are the authoritative state for the full workflow. The original repository/model/service files are retained for compatibility but are not used by the active bot.
- `examples/bracket-preview.png`: an example eight-team bracket.

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m compileall -q bot.py config.py database.py engine.py store.py rendering.py presentation.py discord_channels.py cogs tests
.venv/bin/python -m pip check
```

Tests cover sizes 2–32 with both final policies, out-of-order match completion, byes, no simultaneous matches for one team, two-loss elimination, result validation, stale confirmations, undo/replay, stats, persistence, guild isolation, command serialization, private voice permissions, restart cleanup, and PNG rendering. Discord operations are mocked; live server acceptance remains a separate setup check.

Library references: [discord.py interactions](https://discordpy.readthedocs.io/en/stable/interactions/api.html) and [Pillow drawing](https://pillow.readthedocs.io/en/stable/reference/ImageDraw.html).
