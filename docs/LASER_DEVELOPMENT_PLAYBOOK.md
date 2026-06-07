# Laser Trap — Development Playbook & Status

**Last updated:** 2026-06-07  
**Repo:** `/Users/apple/activerse_final_changes/led-laser`  
**Original source:** `laser/_unpacked/lasertrap10/lasertrap/` (decompiled under `games/`)  
**Migration reference:** `docs/LASER_MIGRATION.md`, `../led-climb/docs/CLIMB_DEVELOPMENT_PLAYBOOK.md`

---

## What this game is

Dark-room **wall pressure button** game. Players press lit boxes on a **1D wall perimeter** (14 buttons on a 6×16 floor outline). Scoring targets are `WALL_LIGHT` groups — not floor tiles.

| Mode | Behavior |
|------|----------|
| **1P** | Press scoreable wall colors (blue, orange, yellow, cyan, magenta, white) → +1 |
| **Hazards** | RED wall button → −1 score + −1 HP (rate-limited) |
| **DEDUCT** | `(254,0,48)` → −1 score, consume button |
| **Safe** | GREEN — non-scoring shield |
| **Session** | 5-min marathon through level series; score + lives persist |

Headless stack: **React UI + wall simulator + FastAPI**. Hardware wall serial drivers exist under `games/led/` but are **not wired** into `api/game_manager.py`.

---

## Status at a glance

| Area | Status |
|------|--------|
| Headless API + `Play.running()` loop | ✅ Done |
| Wall perimeter simulator (14 buttons) | ✅ Done |
| WALL_LIGHT scoring via `wall_index` | ✅ Done |
| A / B / C / intro level buckets | ✅ Done |
| Session marathon + level progression | ✅ Done |
| Parallel ports (8003 / 8768 / 5176) | ✅ Done |
| `Play.py` decompiler fixes | ✅ Done |
| Hardware wall serial (`list_wall_com_info`) | ⏳ Pending |
| RFID / MySQL prod login | ⚠️ Partial |
| Audio / video | ⏳ Mocked |

---

## Architecture

```
led-laser/
├── api/
│   ├── main.py              # /levels, /game-input wall_index
│   ├── game_manager.py      # WALL_LIGHT scoring, wall_display
│   └── config.py            # API_PORT=8003
├── games/
│   ├── game_play/Play.py    # FIXED — get_game_speed, deal_all_direction
│   ├── source/
│   │   ├── -/               # A-series casual (*.led)
│   │   ├── --/              # B-series level
│   │   ├── ---/             # C-series advanced
│   │   └── ----/            # intro 02-10
│   └── setting/             # led_parameter (wall_light_table, 6×16)
├── frontend/                # React — Laser-branded UI
├── simulator/static/        # Wall perimeter canvas
├── ws_bridge.py             # wall_frame broadcast
└── scripts/start-dev.sh
```

### Data flow (simulator)

```
React → /start-game → GameManager → Play.running()
    → frame callback → wall_zones[0|1] + floor_display 6×16
    → /game-state → ws_bridge → corridor simulator
    → click LEFT/RIGHT wall bank → /game-input {wall_index: 0|1} → try_score_wall
```

**Wall model:** Venue has **two physical walls** (left + right). `wall_light_layout_real: [1,2]`
maps two hardware read channels to logical indices **0 = left bank**, **1 = right bank**.

**Two inputs (same as hardware):**
- `wall_light_state_array[]` ← wall button serial (sim: floor tile in front of wall)
- `table_state[][]` ← floor laser break-beam serial (sim: floor click = standing)

**Rules engine (ported from original):**
- `vary_with_color_state` — floor `red_table` + tread → life/score (`laser_detect_time` ~0.22s)
- `score_wall_light_groups` — blue `WALL_LIGHT` + wall press → +1 score
- Sim: 7 dots per wall; click floor tile in front of blue wall to score; hold on red floor to lose life.

---

## Run locally

```bash
cd led-laser
./scripts/setup_settings.sh   # first time — verify levels + shelve
./scripts/start-dev.sh
```

| Service | Port |
|---------|------|
| Frontend | 5176 |
| API | 8003 |
| ws_bridge / simulator | 8768 |

---

## Level buckets (`/levels`)

| Category | Path | 2P |
|----------|------|-----|
| `casual` | `source/-/*.led` | No |
| `level` | `source/--/*.led` | No |
| `advanced` | `source/---/*.led` | No |
| `intro` | `source/----/*.led` | No |

---

## Verification

```bash
curl -s http://localhost:8003/health
curl -s http://localhost:8003/levels | python3 -m json.tool | head

curl -s -X POST http://localhost:8003/start-game \
  -H 'Content-Type: application/json' \
  -d '{"card_id":"test","level":"A001","difficulty":"normal"}'

curl -s -X POST http://localhost:8003/game-input \
  -H 'Content-Type: application/json' \
  -d '{"type":"press","wall_index":0}'
```

---

## Pending checklist

### P0 — Before hardware wall test
- [ ] Confirm `list_wall_com_info` COM port matches venue wiring
- [ ] Wall sensor hold vs momentary press behavior
- [ ] USB dongle / `yanqian()` on Windows kiosk

### P1 — Hardware integration
- [ ] `led_control.init_com` for wall_light COM
- [ ] Per-frame: read wall sensors → `wall_light_state_array`, write `wall_light_arr` → serial
- [ ] See `../led-hexagon/docs/HARDWARE_MODE.md` — adapt for wall-only I/O

### P2 — Polish
- [ ] Real MP3 audio (optional)
- [ ] Automated API smoke tests
- [ ] Floor decor display in simulator (FLOOR_LIGHT groups exist but are secondary)

---

## Git milestone

Tag when hardware-validated: `git tag -a sim-ready-YYYY-MM-DD`

History: see `docs/LASER_MIGRATION.md` for migration phases 0→5.
