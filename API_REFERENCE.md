# API Reference — LED Laser Trap (`api/main.py`)

Lightweight at-a-glance reference. Not full OpenAPI detail — see FastAPI's
auto-generated `/docs` (Swagger UI) on a running server for exact schemas.
Default port: `8001` (see `ONSITE_LAN_INTEGRATION_PLAN.md`).

---

## Game lifecycle

### `POST /login`
Look up a player by RFID card ID.
- **Request:** `{ card_id: str }`
- **Response:** `{ success, player?: { custom_id, name, phone, time_left, card_id }, error? }`

### `POST /start-game`
Create and start a new game instance (marathon session).
- **Request:** `{ card_id: str, level: int|str, difficulty: "easy"|"normal"|"hard" }`
- **Response:** `{ success, game_id?, ws_url?, error? }`
- Checks the player's 60-min session time remaining (skipped if DB unavailable) before creating the game.

### `WS /game/{game_id}`
Real-time game state stream. Server pushes `{"type":"game_state","data":<state>}` at ~60fps; client may send input JSON (currently logged only — real input goes via `/game-input`).

### `GET /game-state`
Current state of the first active game (simulator convenience — assumes one game at a time). `{ success, game_id?, state? }` or `{success:false, error:"No active games"}`.

### `GET /game-state/{game_id}`
State of a specific game by ID. `{ success, game_id, state }` or `{success:false, error}`.

### `GET /active-game`
Returns the currently-running, not-yet-game-over game (if any) with its full config, so the frontend can resume the simulator after a page reload instead of restarting login. `{ success, game_id, card_id, level, difficulty, state }` or `{success:false}`.

### `POST /game-input`
Simulator/hardware input: floor tile press or wall button press.
- **Request:** `{ game_id?, type: "press"|"release", row?, col? }` (floor tile) **or** `{ wall_index?, type }` (wall button, debug/simulator)
- If `game_id` omitted, uses whatever game is currently running.
- **Response:** `{ success, score, life }`

### `GET /result/{game_id}`
Final result + top-10 leaderboard after a game ends.
- **Response:** `{ success, score?, player_name?, time_used?, difficulty?, leaderboard?: [{rank,name,score,timestamp}], error? }`

### `POST /save-score`
Persist a finished session to the leaderboard DB (called by frontend at session end, independent of `/logout`).
- **Request key fields:** `card_id, card_id2, multiplayer, level, end_level, score, score2, final_score, final_score2, life, lives_start, result, time_used, levels_cleared, difficulty, started_at`
- **Response:** `{ success }`

### `POST /logout`
End a game session (stops the game thread, blanks hardware floor if `USE_SERIAL_HD`) and record its score.
- **Request:** `{ card_id: str, game_id: str }`
- **Response:** `{ success, error? }`

---

## RFID / settings

### `GET /game-settings`
Static-ish game config loaded from the `led_parameter` shelve (grid dims, wall layout, timeout, max score). Falls back to hardcoded 6×16 defaults if the shelve read fails.
- **Response:** `{ success, wall_layout, grid_dims: {rows, cols}, timeout_seconds, max_score }`

### `POST /settings`
Runtime override push from the central RFID server (default difficulty, session length). Written to `games/setting/runtime_overrides.json`; does **not** touch the original read-only shelve.
- **Request key fields:** `default_difficulty?, session_minutes?`
- **Response:** `{ success, overrides }`

### `GET /settings`
Read back whatever overrides are currently set. Returns `{}` if no override file exists yet.

### `GET /levels`
All Laser Trap levels grouped by category (`casual`, `level`, `advanced`, `intro` — mapped to `source/-`, `source/--`, `source/---`, `source/----`).
- **Response:** `{ success, levels: [{id, name, path, category, multiplayer, file_type}], categories: {<cat>: [...]}, count }`

---

## Scores / leaderboard

### `GET /scores?since=<ISO timestamp>`
Scores recorded after `since`. Used by the central RFID server's poller.
- **Response:** `{ success, game, scores }` or `{success:false, error}`

### `GET /leaderboard/{level}?limit=10`
Top scores for a specific level.
- **Response:** `{ success, level, entries }`

---

## Ops / diagnostics

### `GET /health`
Basic liveness + active-game stats. Used by the LAN connectivity check and the RFID poller.
- **Response:** `{ status: "ok", game, stats }`

### `GET /hw-debug`
Live hardware-loop diagnostics — whether `USE_SERIAL_HD` is on, per-game HW draw counts/timestamps, and any zombie threads from `clear_all()`. Useful onsite to confirm the HW draw loop is actually ticking without watching the physical floor.
- **Response:** `{ use_serial_hd, active_games, games: [{game_id, running, score, hw_draw_count, last_hw_draw}], zombie_threads }`
