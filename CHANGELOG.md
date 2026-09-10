# BFC Ranked Matchmaking Bot — Update Log

Updates are listed newest first. This log tracks the active ranked matchmaking bot refactor and the recent command/runtime improvements.

## 2026-09-10 — Ranked bot refactor and queue reliability updates

### Current bot state
- Rebuilt the active runtime around a ranked matchmaking foundation instead of the old tournament-only flow.
- Added `/register`, `/profile`, `/setign`, `/unregister`, `/ranked start`, and `/ranked end` to the main bot.
- Added a `1v1` ranked format alongside `2v2`, `3v3`, `4v4`, `5v5`, and `6v6`.
- Persisted queue state, participants, room details, and ready-match payloads in SQLite.
- Kept the Bullet Force probe utility isolated and out of the runtime path.

### Command and runtime improvements
- Added `/unregister` to remove the stored player record and clear the server nickname when permissions allow.
- Updated the registration and IGN update flow to attempt server nickname syncing.
- Added better permission-aware nickname sync handling so missing Discord permissions no longer appear as a silent failure.
- Fixed the ranked queue interaction timing issue so the format-selection and queue-action buttons acknowledge the interaction immediately and continue the match flow.
- Updated the docs and env template so the GitHub-facing project state matches the new ranked bot.

### Planned future work
- OCR-based screenshot parsing for match results
- Final rating formula and automatic rating updates
- Deeper matchmaking automation and richer player statistics

## Earlier history

### 2026-09-08 — Token, launch, and invitation guide
- Added exact `.env` token placement and macOS launch instructions to the README.
- Documented invite scopes and required Discord permissions.

### 2026-09-08 — Configuration startup follow-up
- Loaded `.env` explicitly from the bot folder, regardless of the working directory.
- Added clearer placeholder token handling.
- Improved startup validation and readable configuration errors.

### 2026-09-08 — Complete tournament workflow
- Added the original tournament bot feature set, including bracket generation, Discord team handling, match rooms, and result tracking.
- Added persistent tournament state, match cleanup, and result corrections.

### Earlier commits
- [`ede8c75`](https://github.com/ffivestar/Bullet-Force-Competitive-Discord-Bot/commit/ede8c75) — added tournament state storage and bracket rendering.
- [`a5c6ed9`](https://github.com/ffivestar/Bullet-Force-Competitive-Discord-Bot/commit/a5c6ed9) — integrated the existing GitHub history.
- [`04af70e`](https://github.com/ffivestar/Bullet-Force-Competitive-Discord-Bot/commit/04af70e) — published the initial tournament bot foundation.
- [`e910a8e`](https://github.com/ffivestar/Bullet-Force-Competitive-Discord-Bot/commit/e910a8e) — initial repository commit.
