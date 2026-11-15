#!/usr/bin/env bash
# Launch Toddler Desk; always put GNOME settings back afterwards, even on a crash.
DIR="$(cd "$(dirname "$0")" && pwd)"
python3 "$DIR/toddler_desk.py" "$@"
python3 "$DIR/toddler_desk.py" --restore >/dev/null 2>&1
