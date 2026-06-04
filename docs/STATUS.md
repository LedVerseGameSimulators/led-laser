# LED Hex — Headless + React Conversion: Status

Goal: replace the Tkinter UI with a React frontend + headless API, keeping the
real decompiled game logic. Step toward deploying on the physical LED floor.

## Architecture

```
React frontend (:5173)  ──HTTP──>  FastAPI (:8000)  ──in-proc──>  Play (game logic, headless)
   login/select/play/result          /start-game, /game-input,        mock LedTable (no Tkinter)
        │                            /game-state/{id}, /save-score
        │  iframe + clicks
        ▼
  Simulator UI (:8765)  <──WS frame broadcast──  ws_bridge  ──polls /game-state──> API
        │  press/release over WS  ─────────────────────────> POST /game-input
```

- **API** (`api/`): FastAPI. Runs each game in a background thread via real
  `Play.running()`. State (score, life, time, 3-ring LED grid) exposed over HTTP.
- **ws_bridge.py**: bridges API game-state → simulator canvas (WS), and forwards
  simulator clicks → `/game-input`.
- **Simulator** (`ledhexagon_clone/simulator/static`): hex canvas, 3-ring tiles.
- **Frontend** (`frontend/`): React/Vite. Login → Game/Level select → Settings →
  Simulator (live score/life/time + Stop) → Result (final score + leaderboard).

## Game logic implemented (faithful to decompiled original)

- ✅ Real levels (17–26) loaded from `.led` (zip → shelve `dict_group`)
- ✅ **3-ring tile colors** (outer/mid/inner) end-to-end
- ✅ **Group movement** — `Play.running()` + `deal_all_direction` (sweeping red line).
  Fixed a decompile bug: speed groups moved every frame; restored `move_distance`
  gating so speed = cells/second. Tunable via `game_level_speed` per difficulty.
- ✅ **Breath** shimmer — `LedGroup.breath()` per in-time group (display only)
- ✅ **Consume-on-hit** — stepping a goal tile removes it (blanks) + white flash
- ✅ **Goal-color scoring** (the real mechanic): goal color from the `goal_led`
  indicator (lvl24 green, lvl25 magenta). Step matching `normal_led` floor tiles
  = +1; decor (other colors) = neutral; **red = −1 + HP loss**.
- ✅ **HP / life** = 20 (from `life_value_sw`); red drains HP (rate-limited by
  `life_value_count_time`); game over at 0 (`out_of_life`)
- ✅ **Game time** = 300s (from `game_time_sw`=5min)
- ✅ **Zone confinement** (5×9 from level `zone_*`) — out-of-zone presses rejected
- ✅ **Settings loader** — reads `led_parameter` + `debug_parameter` shelves
- ✅ **Leaderboard** — scores persisted to `hex_scores` in `ledplaydb.sqlite`,
  shown per-level on the result screen
- ✅ **Audio** — browser Web Audio synth (ding on score, buzz on HP loss)

## Not implemented (low priority / uncertain)

- ❌ Hidden-tile bonus mechanic (safe tile reveals timed bonus) — decompile partial
- ❌ Multiplayer (`COLOR_ARR` per-player colors + per-player scores)
- ❌ Wall lights / screen lights (`goal_led`/`goal2_led` secondary outputs — off in our levels)
- ❌ Videos (intro/idle/type-select)
- ❌ `running_by_blue` goal-color *rotation* — decompile-broken (`append(a,b)`,
  `removemember`); our levels use a static goal color so not needed
- ❌ RFID/barcode session + 60-min timer

## Files changed

**kavida_claude/**
- `api/game_manager.py` — headless run loop, settings, scoring, HP, zone, effects
- `api/main.py` — endpoints: start-game, game-input, game-state/{id}, active-game,
  save-score, leaderboard
- `api/database.py` — `hex_scores` table + record/leaderboard
- `ws_bridge.py` — state→sim broadcast + click→API forward (3-ring)
- `frontend/` — React app (Login/Select/Settings/Simulator/Result)
- `docs/SETTINGS.md`, `docs/STATUS.md`

**ledhexagon_clone/** (only decoupling + decompile fixes)
- `game_play/game_running.py` — mock `LedTable` (no Tkinter; stores 3-ring grid,
  press state, breath/channel helpers)
- `game_play/Play.py` — fixed `running()` movement gating (decompile bug)
- `game_play/game_hw.py` — removed Tkinter messageboxes → logger

## Run

```
cd kavida_claude && python -m api.main           # :8000
python ws_bridge.py                               # :8765
cd frontend && npm run dev                         # :5173
```
