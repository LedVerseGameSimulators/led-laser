# Cursor chat starter prompt — Laser headless migration

Copy everything inside the fenced block below into a **new Cursor chat** (Agent mode).  
Work only in the **`led-laser`** repo unless copying reference files from siblings.

---

```
Migrate the Laser Trap LED game to a headless React + FastAPI stack in:

  /Users/apple/activerse_final_changes/led-laser

This repo is a stale LED-Hex scaffold. Three sibling games are DONE and locked at git tag `sim-ready-2026-06-07`:

  - led-hexagon  (hex floor, 3-ring)     → docs/LED_HEX_DEVELOPMENT_PLAYBOOK.md
  - led-climb    (square floor 6×33)     → docs/CLIMB_DEVELOPMENT_PLAYBOOK.md
  - led-hoops    (hoop wall strip 1×N)   → docs/HOOPS_DEVELOPMENT_PLAYBOOK.md

READ FIRST (in order):
  1. led-laser/docs/LASER_MIGRATION.md          ← your step-by-step spec
  2. led-climb/docs/CLIMB_DEVELOPMENT_PLAYBOOK.md ← closest architecture to copy
  3. led-climb/docs/PLAYBOOK_OTHER_GAMES.md     ← Laser = WALL_LIGHT scoring section
  4. led-climb/api/game_manager.py              ← copy pattern (mocks, HeadlessLedTable, session loop)

LASER IS DIFFERENT FROM CLIMB/HEX:
  - Scoring targets are WALL_LIGHT groups, not FLOOR_LIGHT
  - group.start_member = wall indices (ints), not (row,col)
  - Input: wall_light_state_array[idx], not state_table[row][col]
  - Simulator must be a WALL PERIMETER UI (lit pressable boxes), not a floor grid
  - API /game-input should accept wall_index (press/release)

ORIGINAL SOURCE (copy levels + settings if games/source is empty):
  ${LASER_SRC:-/Users/apple/Desktop/activerse/laser/lasertrap_py_source/lasertrap}
  - source/   → led-laser/games/source/
  - setting/  → led-laser/games/setting/

PORTS (do not collide with other games):
  UI 5176 | API 8003 | ws_bridge 8768
  Add frontend/src/config.js, scripts/start-dev.sh, vite strictPort

TASK ORDER:
  Phase 0: Fix api/config.py (GAMES_ROOT, GAME_NAME=laser), remove hex clone paths,
           copy levels/settings, setup_settings.sh + start-dev.sh
  Phase 1: Port game_manager from led-climb — mocks, HeadlessLedTable WITH wall arrays,
           Play.py decompiler fixes (get_game_speed, deal_all_direction)
  Phase 2: Implement wall scoring in frame callback + try_score_wall + game-input wall_index
  Phase 3: New simulator HTML — perimeter wall buttons, ws_bridge wall frames
  Phase 4: Laser-branded frontend (GameSelectionScreen, settings, SimulatorScreen)
  Phase 5: E2E smoke test — /health, /levels, start-game, press wall in sim, score changes

DO NOT:
  - Use 3-ring hex display for Laser
  - Score via state_table[row][col] unless a level actually uses FLOOR_LIGHT
  - Point config at ledhexagon_clone or kavida_claude paths
  - Commit until sim E2E works; then add docs/LASER_DEVELOPMENT_PLAYBOOK.md

REFERENCE IMPLEMENTATIONS (read-only copy):
  led-climb/api/game_manager.py
  led-climb/ws_bridge.py
  led-hoops/frontend/src/screens/SimulatorScreen.jsx  (player_count / 2P patterns)

When finished, report: ports, level count, sample wall_index scoring test, and remaining gaps vs LASER_MIGRATION.md Phase 6 (hardware).
```

---

## Optional: one-line version

```
Migrate led-laser per docs/LASER_MIGRATION.md using led-climb as the API template; Laser scores WALL_LIGHT wall indices not floor tiles; ports 8003/8768/5176; build wall-perimeter simulator.
```
