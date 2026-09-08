#!/bin/sh
set -eu
cd "$(dirname "$0")"
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
if [ ! -f .env ]; then
    cp .env.example .env
    chmod 600 .env
fi
printf '%s\n' 'Setup complete. Set DISCORD_TOKEN and COMMAND_GUILD_ID in .env, then run ./run.sh'
