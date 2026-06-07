#!/usr/bin/env bash
# Verify Laser settings shelve exists (copied from original install).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SETTING="$ROOT/games/setting"

if [ -f "$SETTING/led_parameter.dat" ]; then
  echo "OK: led_parameter shelve present"
else
  echo "Missing games/setting/ — copy from original laser install:"
  echo "  LASER_SRC=/path/to/lasertrap"
  echo "  cp -r \"\$LASER_SRC/setting\" \"$ROOT/games/\""
  exit 1
fi

if [ -d "$ROOT/games/source/-" ]; then
  echo "OK: level source present ($(find "$ROOT/games/source" -name '*.led' | wc -l | tr -d ' ') .led files)"
else
  echo "Missing games/source/ — copy from original laser install"
  exit 1
fi

echo "Laser settings ready."
