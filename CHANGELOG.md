# BFC Tournament Bot — Update Log

Updates are listed newest first. This log describes code changes; it does not indicate that a bot has been deployed or tested in a live Discord server.

## 2026-09-08 — Configuration startup follow-up

- Load `.env` explicitly from the bot folder, regardless of the working directory.
- Use the clearer `PASTE_MY_TOKEN_HERE` example and reject both old and new placeholder tokens.
- Report invalid startup configuration as a readable log message.
- Preserve the completed workflow in commit [`8491832`](https://github.com/ffivestar/Bullet-Force-Competitive-Discord-Bot/commit/8491832).

## 2026-09-08 — Complete tournament workflow

### Feature updates

| Area | Update |
| --- | --- |
| Player pool | Add players by mention, Discord ID, or an unambiguous exact name; remove unassigned players. Reject duplicate players and bot accounts. |
| Balanced teams | Refresh Discord tier roles and shuffle within each tier to create teams containing one Tier 1, one Tier 2, and one Tier 3 player. Validate tier counts and conflicting roles. |
| Manual teams | Create, edit, and delete three-player teams before starting. Prevent duplicate team names and players appearing on multiple teams. Support optional tier enforcement. |
| Tournament lifecycle | Create, configure, list, view, start, and cancel tournaments. Lock rosters at start and retain cancelled tournament history. |
| Double elimination | Connect the bracket engine to Discord commands for 2–32 teams, with automatic byes, winners/losers progression, elimination, and an optional grand-final reset. |
| Bracket images | Publish and update a permanent bracket post with BFC styling, scores, connecting lines, and champion status. Include an example PNG. |
| Tournament navigation | Add persistent View Teams, View Matches, Player Stats, and Leaderboard buttons. |
| Match text channels | Create a room for each ready matchup showing rosters, round, map, region, match ID, status, and voice links. Spectators can read; players and staff can write. |
| Private voice channels | Create a separate VC for each team. Restrict access to that team, tournament staff, and admins. Handle match category overflow. |
| Match results | Add a scoreboard form with both team scores and all six players’ kills/deaths, followed by Confirm Result and Edit controls. Infer the winner from the scores. |
| Calculated statistics | Calculate K/D, handle zero deaths, and award per-team top frag to all tied leaders. Reject invalid scores, draws, and incomplete player statistics. |
| Match cleanup | Announce completed matches and delete their text/voice rooms after a 45-second delay. Keep the match record permanently. |
| Result archive | Create or update permanent match-results posts with scores, player statistics, map, region, recorder, and timestamp. |
| Corrections | Add administrator-confirmed result undo. Show affected matches, invalidate dependent results, rebuild the bracket, recalculate statistics, and retain an audit trail. |
| History and awards | Retrieve match history after channel deletion. Show placings, MVP, most kills, best K/D, most top frags, team wins, and player leaderboards. Aggregate player history within a server. |
| Permissions | Check Tournament Staff/BFC Admin roles at runtime. Restrict administrative actions and confirmation buttons, and recheck permissions on confirmation. |
| Recovery | Persist Discord channel/message IDs and cleanup deadlines. Retry failed delivery every 20 seconds; provide a manual sync command and bracket restoration option. |
| Installation | Add executable setup/run scripts, configurable tier role names, exact tested dependency versions, and expanded setup and operating instructions. |

### Fixes and safeguards

- Display a known bracket participant even when the other participant’s source match is still pending.
- Snapshot map and region with submitted results so historical scoreboards retain their original metadata.
- Reject stale or duplicate result confirmations after a match changes.
- Validate a supplied match ID against the current room when a tournament ID is omitted.
- Normalize match text-channel names and reuse saved rooms during retries.
- Disable automatic mentions in bot output.
- Reject the placeholder bot token during configuration loading.
- Cancel the retry worker during shutdown and present readable command errors.
- Exclude local credentials, virtual environments, bytecode, and SQLite sidecar files from version control.

### Validation

| Check | Result |
| --- | --- |
| Automated test suite | **14 tests passed** before publication. |
| Tournament simulations | **372 simulations**: every size from 2 through 32, both final-reset policies, six result-order/outcome scenarios per combination. |
| Bracket rules | Covered byes, no simultaneous matches for one team, elimination after two losses with reset enabled, and tournament completion. |
| Results and corrections | Covered invalid statistics, stale submissions, tied top frags, undo/replay, and statistics derived from current results. |
| Persistence | Covered restart persistence, guild isolation, revision conflicts, and foundation-record migration. |
| Discord integration | Covered command serialization, view construction, runtime permissions, private VC overwrites, room reuse, and delayed cleanup after restart using mocks. |
| Images | Rendered PNGs for 2, 3, 8, 17, and 32 teams; inspected the eight-team preview. |
| Live Discord | Requires the real token, invited bot, server roles/permissions, and a live-server acceptance check. |

### Operating notes

- Supported tournament size: **2–32 teams**, three players per team.
- Scoreboard entry is manual; no Bullet Force API integration is required.
- Run one bot process per SQLite database and keep the process online.
- Undo clears affected downstream results; staff must resubmit those results after correcting the original match.
- Cancelling a tournament preserves historical data.

## Earlier commits — 2026-09-08

| Commit | Update |
| --- | --- |
| [`ede8c75`](https://github.com/ffivestar/Bullet-Force-Competitive-Discord-Bot/commit/ede8c75) | Added tournament state storage and bracket rendering. |
| [`a5c6ed9`](https://github.com/ffivestar/Bullet-Force-Competitive-Discord-Bot/commit/a5c6ed9) | Integrated the existing GitHub history. |
| [`04af70e`](https://github.com/ffivestar/Bullet-Force-Competitive-Discord-Bot/commit/04af70e) | Published the initial tournament bot foundation. |
| [`e910a8e`](https://github.com/ffivestar/Bullet-Force-Competitive-Discord-Bot/commit/e910a8e) | Initial repository commit. |

See [README.md](README.md) for installation and commands, and [the commit history](https://github.com/ffivestar/Bullet-Force-Competitive-Discord-Bot/commits/main/) for the complete file-level change history.
