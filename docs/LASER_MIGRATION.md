# Laser Trap — Headless Migration Playbook

**Last updated:** 2026-06-07  
**Target repo:** `/Users/apple/activerse_final_changes/led-laser`  
**Status:** 🔴 Scaffold only — copied from LED Hex; **not yet adapted for Laser**  
**Reference repos (locked at `sim-ready-2026-06-07`):**

| Game | Repo | Playbook |
|------|------|----------|
| LED Hex (template) | `led-hexagon` | `docs/LED_HEX_DEVELOPMENT_PLAYBOOK.md` |
| Climb (square floor) | `led-climb` | `docs/CLIMB_DEVELOPMENT_PLAYBOOK.md` |
| Hoops (wall sensors) | `led-hoops` | `docs/HOOPS_DEVELOPMENT_PLAYBOOK.md` |
| Parent migration notes | `activerse_final_changes` | `CLIMB_MIGRATION_PLAYBOOK.md` |

---

## What Laser is (vs other games)

Dark-room **wall pressure button** game. Players press lit boxes on a **1D wall perimeter**, not a 2D floor grid.

| | Hex | Climb | Hoops | **Laser** |
|---|-----|-------|-------|-----------|
| **Play surface** | Hex floor 16×26 | Square floor 6×33 | Hoop strip 1×N | **Wall buttons (1D array)** |
| **Scoring groups** | `FLOOR_LIGHT` | `FLOOR_LIGHT` | `FLOOR_LIGHT` + wall display | **`WALL_LIGHT`** |
| **Input** | Step floor tile | Stand on floor | Momentary hoop sensor | **Press wall button** |
| **Display** | 3 rings / hex | 1 RGB / square | 1 RGB / column | **Wall LED colors** |
| **Simulator** | Hex canvas | Square grid | Hoop strip | **Wall perimeter UI (new)** |

Original source (copy levels + settings from here):

```
/Users/apple/Desktop/activerse/laser/lasertrap_py_source/   # or lasertrap10 unpack
  lasertrap/source/     # level .led / .ledb files
  lasertrap/setting/    # led_parameter, debug_parameter
```

---

## Current `led-laser` repo state

| Item | State |
|------|--------|
| `games/` Python tree | ✅ Present (decompiled laser source) |
| `games/source/` levels | ❌ **Empty** — must copy from original |
| `games/setting/` shelve | ❌ Likely missing — run setup script |
| `api/config.py` | ❌ Still points at `ledhexagon_clone`, `GAME_NAME=led_hex` |
| `api/game_manager.py` | ❌ Hex 3-ring logic, hardcoded clone paths |
| `simulator/` | ❌ Hex canvas — needs **wall perimeter** UI |
| `frontend/` | ❌ Generic hex clone — needs Laser branding + wall sim |
| Dedicated ports | ❌ Assign **8003 / 8768 / 5176** (see below) |

**Recommended base copy:** Start from **`led-climb`** (square-ish, simpler display than 3-ring hex), then apply Laser-specific **wall scoring** from this doc. Do **not** ship hex 3-ring simulator for Laser.

---

## Port map (parallel dev)

| Game | UI | API | ws_bridge |
|------|-----|-----|-----------|
| Hoops | 5173 | 8000 | 8765 |
| Climb | 5174 | 8001 | 8766 |
| LED Hex | 5175 | 8002 | 8767 |
| **Laser** | **5176** | **8003** | **8768** |

Add Laser to `../scripts/start-all-games.sh` when stack is working.

---

## Migration phases

### Phase 0 — Bootstrap (copy & paths)

1. **Copy level data + settings** from original laser install:
   ```bash
   LASER_SRC="${LASER_SRC:-/Users/apple/Desktop/activerse/laser/lasertrap_py_source/lasertrap}"
   cp -r "$LASER_SRC/source" led-laser/games/
   cp -r "$LASER_SRC/setting" led-laser/games/
   ```
2. **Fix `api/config.py`** — mirror Climb/Hoops:
   - `GAMES_ROOT = _REPO_ROOT / "games"`
   - `GAME_NAME = "laser"`
   - `API_PORT` default **8003**
3. **Fix `api/game_manager.py`** — remove hardcoded `_CLONE_ROOT = ...ledhexagon_clone`
4. **Add `scripts/setup_settings.sh`** and **`scripts/start-dev.sh`** (ports 8003/8768/5176)
5. **Add `frontend/src/config.js`** with matching URLs
6. **`.gitignore`** — shelve `*.dat`, `node_modules`, `*.rar`

**Verify:** `curl http://localhost:8003/health` after `uvicorn api.main:app --port 8003`

---

### Phase 1 — Headless core (follow Climb pattern)

1. **Mock all external imports** at top of `game_manager.py` (copy list from `led-climb/api/game_manager.py` — scan `games/` for any extra imports).

2. **`HeadlessLedTable`** — extend Climb’s version with **wall arrays**:
   - `_wall_light_arr`, `_wall_light_state_array`, `_wall_screen_arr`
   - `press_wall(idx)` / `release_wall(idx)` for simulator input
   - Floor grid may be unused or minimal for Laser — confirm from level dumps

3. **Fix `Play.py` decompiler bugs** (copy fixes from Climb/Hoops):
   - `get_game_speed` — default `game_level_speed = 1` before branches
   - `deal_all_direction` — rigid bounce (if floor movement exists in laser levels)
   - Laser’s current `Play.py` still has broken `elif game_level == 2` nesting — **fix before testing**

4. **Level loading** — same ZIP → shelve pattern; skip `play_order=True` audio-only shelves.

5. **Settings loader** — read `value_high`, `value_width`, `wall_light_table`, `list_wall_com_info`, `corner_line_start` from shelve.

**Inspect levels first:**
```python
# Dump group types for one laser .led file
import zipfile, tempfile, shelve, os
from collections import Counter
# ... open game_file, print Counter(g.type for g in dg.values())
# Expect heavy WALL_LIGHT usage
```

---

### Phase 2 — Laser-specific scoring (critical)

Hex/Climb score via `state_table[row][col]` on **`FLOOR_LIGHT`** groups.

**Laser scores via `wall_light_state_array[idx]` on `WALL_LIGHT` groups.**

Reference: `games/gui/gui_editor_game.py` → `life_cal.calculation_one_second_wall_light_dict_group(...)`

Implement in frame callback:

```python
wall_state = led_table.get_wall_light_state_array()
for g in dgroup.values():
    if getattr(g, "type", None) != Setting.WALL_LIGHT:
        continue
    if not (g.start_time_sec <= total_pass <= g.end_time_sec):
        continue
    for idx in (g.start_member or []):
        wi = int(idx)
        if wall_state[wi]:
            game.try_score_wall(wi)  # NEW — mirror try_score_cell logic for wall indices
```

**New API input shape:**
```json
POST /game-input
{ "type": "press", "wall_index": 12 }
{ "type": "release", "wall_index": 12 }
```
Keep `row`/`col` optional for future floor decor; Laser sim uses `wall_index`.

**Display buffer:** Build `wall_display` — list of `[R,G,B]` per wall index (not 2D `led_display`). ws_bridge sends `{ "wall": [...], "rows": 0, "cols": N }` or dedicated `type: "wall_frame"`.

---

### Phase 3 — Simulator UI (new)

Replace hex canvas with **wall perimeter** layout:

- Read `wall_light_layout_real` / `wall_light_table` from settings for button count & positions
- Draw N wall buttons in a rectangle perimeter (top → right → bottom → left)
- Click = `press_wall(i)` → ws_bridge → `/game-input`
- Show active color from `wall_display[i]`

Reference climb simulator (`simulator/static/index.html`) for square patterns, but layout is **1D index → perimeter position**, not row×col grid.

---

### Phase 4 — Frontend

Copy from `led-climb/frontend` (or hoops) and rebrand:

- `GameSelectionScreen.jsx` — Laser only
- `GameSettingsScreen.jsx` — level categories from `/levels` (discover laser folder structure)
- `SimulatorScreen.jsx` — `player_count`, resume, 2P if `.ledb` exists
- `vite.config.js` — `strictPort: true`, port **5176**

Update `api/main.py` `/levels` **BUCKETS** after inspecting `games/source/` layout.

---

### Phase 5 — Gameplay parity checklist

Mirror what Climb/Hoops already have where applicable:

- [ ] Session marathon (5 min, lives persist across levels in series)
- [ ] Board timeout vs session timeout
- [ ] Red / deduct / safe classification on **wall** colors
- [ ] 2P if laser has `.ledb` (wall indices split P1/P2 — verify in source)
- [ ] Wave skip / cover / disappear — only if laser levels use them
- [ ] Leaderboard + `save-score`
- [ ] `/active-game` resume

---

### Phase 6 — Hardware (defer until sim works)

Same as other games — drivers in `games/led/`, `game_hw.py`:

- `list_wall_com_info` for wall serial (not only `list_com_info` floor)
- `led_control_c.LedControl.update_wall_light(...)`
- Input: wall sensor bytes → `wall_light_state_array`
- Dongle: `encryption/yanqian.py` on Windows

See `led-hexagon/docs/HARDWARE_MODE.md` — adapt for wall-only I/O.

---

## Files to touch (checklist)

| File | Action |
|------|--------|
| `api/config.py` | GAMES_ROOT, GAME_NAME, port 8003 |
| `api/game_manager.py` | Full rewrite from Climb + wall scoring |
| `api/main.py` | `/levels` buckets, `/game-input` wall_index |
| `api/database.py` | Fix scores DB path (env-based) |
| `games/game_play/Play.py` | Decompiler fixes |
| `ws_bridge.py` | wall frame format, port 8768 |
| `simulator/static/index.html` | **New** wall perimeter UI |
| `frontend/src/config.js` | 8003/8768/5176 |
| `frontend/vite.config.js` | port 5176 |
| `scripts/start-dev.sh` | new |
| `scripts/setup_settings.sh` | new |
| `docs/LASER_DEVELOPMENT_PLAYBOOK.md` | create when migration done (mirror Hoops) |

---

## Verification commands

```bash
cd led-laser
./scripts/setup_settings.sh
./scripts/start-dev.sh

# API
curl -s http://localhost:8003/health
curl -s http://localhost:8003/levels | python3 -m json.tool | head

# Start game
curl -s -X POST http://localhost:8003/start-game \
  -H 'Content-Type: application/json' \
  -d '{"card_id":"test","level":"<FIRST_LEVEL_ID>","difficulty":"normal","player_count":1}'

curl -s http://localhost:8003/game-state | python3 -c "import sys,json; print(json.load(sys.stdin).keys())"

# Wall press (after implemented)
curl -s -X POST http://localhost:8003/game-input \
  -H 'Content-Type: application/json' \
  -d '{"type":"press","wall_index":0}'
```

---

## Common pitfalls

1. **Scoring floor instead of wall** — Laser levels use `WALL_LIGHT`; copying Hex callback verbatim will never score.
2. **`start_member` is int indices**, not `(row,col)` tuples — do not pass to `try_score_cell(i,j)`.
3. **Hex 3-ring display** — wrong for Laser; wall is single RGB per button.
4. **Empty `games/source/`** — migration blocked until levels copied.
5. **Hardcoded clone paths** — current `led-laser` still references `ledhexagon_clone`.
6. **Play.py `get_game_speed`** — unfixed decompile causes UnboundLocalError on easy difficulty.

---

## When migration is “done”

Create `docs/LASER_DEVELOPMENT_PLAYBOOK.md` with:

- Status at a glance (sim ✅ / hardware ⏳)
- Done / pending checklists
- Run commands
- Link to this migration doc for history

Tag release: `git tag -a sim-ready-YYYY-MM-DD`

---

*Generated from completed Hoops / Climb / Hex headless migrations — June 2026.*
