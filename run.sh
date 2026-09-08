#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
    printf '%s\n' 'Run ./setup.sh first.' >&2
    exit 1
fi
exec .venv/bin/python bot.py
