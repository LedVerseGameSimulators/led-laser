# Hardware Validation — LED Laser Trap

> **Status: FIRST-TIME REAL-HARDWARE TEST.** The hardware driver code in
> `api/game_manager.py` (`_hw_init()`, `USE_SERIAL_HD`, the per-frame
> `led.led_control` calls) has **never been run against a physical LED
> floor**. It was written by analogy from led-hoops/led-climb's real
> hardware findings — not validated on laser's own hardware. Treat every
> item below as unverified until an onsite run confirms it. This is not a
> re-test of known-working code.

---

## 1. What hardware integration exists

| Item | Value |
|---|---|
| Floor grid | 6 rows × 16 cols |
| COM ports (floor) | 1, per `HARDWARE_INTEGRATION_PLAN.md`'s Laser Trap section (`Grid: 6×16 · COM: 1 port · Layout: 5`) |
| Layout type | read from shelve (`led_layout_type`), dev shelve shows `5` |
| Protocol | 3 bytes/tile (R, G, B), same as hoops/climb |
| Enable mechanism | `USE_SERIAL_HD=1` env var |

**`USE_SERIAL_HD` mechanism** (`api/game_manager.py`):
- `USE_SERIAL_HD = os.environ.get("USE_SERIAL_HD", "0") == "1"` gates everything below.
- When true: `serial`/`led.*` modules are NOT mocked (real pyserial + real
  `led/led_control.py` are imported instead of `MagicMock()`).
- `_hw_init()` (called once per game start) opens `shelve` at
  `games/setting/led_parameter`, reads `list_com_info`, `led_layout_type`,
  `value_high`/`value_width`, `floor_layout_coors_no_use`, then calls
  `led_control.init_layout(...)` and `led_control.init_com(...)`. Sets the
  module-level `_hw_led_control` handle used by every later frame.
- Per frame (inside `_frame_callback`, throttled to `_HW_DRAW_INTERVAL`
  seconds, default 0.045s): builds a `rows × cols` grid from
  `floor_display`, calls `_hw_led_control.draw_screen_by_com(layout, grid)`
  to write LEDs, then `update_screen_state_by_com(...)` to read sensor
  presses back into `led_table.state_table`. Wrapped in try/except so a
  serial glitch never crashes the game thread; all HW I/O is serialized
  through `_hw_serial_lock`.
- Blank-on-stop (added in this pass — see `docs/` note below): the exact
  same `draw_screen_by_com` call, with an all-`[0,0,0]` grid, fires at
  every game-end path.

### Known gap — wall/screen lights are NOT wired to hardware

Laser Trap physically has **wall lights** (button perimeter) in addition
to the floor grid — the dev shelve contains `list_wall_com_info` (COM7)
and `list_screen_com_info` (COM6) alongside the floor's `list_com_info`
(COM9). `ONSITE.md` even says "wall lights... will light correctly when
the actual game runs," but that is **not backed by the current code**:

- `_hw_init()` only reads `list_com_info` and only calls
  `led_control.init_com(list_com_info)` — the wall/screen COM entries are
  never opened.
- The per-frame HW block only sends `floor_display`; `wall_display`
  (built every frame for the browser simulator) is never written to any
  serial port.
- `docs/LASER_MIGRATION.md` (Phase 6, "Hardware — defer until sim works")
  explicitly flags this as unfinished: wall serial needs
  `list_wall_com_info` + `led_control_c.LedControl.update_wall_light(...)`,
  which was never implemented.

**Practical effect:** on real hardware, expect the floor grid to light up
but the physical wall-button LEDs to stay dark (or be driven by whatever
legacy system, if any, currently owns COM7/COM6) even though the
simulator shows `wall_display` correctly. Confirm this onsite — see
checklist item 5 below.

---

## 2. Validation history

| Test | Status |
|---|---|
| Simulator-only (browser canvas) gameplay | Validated repeatedly during dev |
| `USE_SERIAL_HD=1` against real serial hardware | **Never done** — this will be the first attempt |
| Floor grid ↔ physical tile mapping | **Never done** — implemented by analogy, unverified |
| Sensor press → game input, real floor | **Never done** |
| Wall lights over serial | **Not implemented** (see gap above), so nothing to validate yet |
| Blank-on-stop fix (this pass) | Code written and `ast.parse`-checked only; **cannot be validated without a physical floor** |

Because nothing here has touched real hardware, do not assume any
individual piece (COM port assignment, grid orientation, timing) works
just because the equivalent piece worked on led-hoops or led-climb — each
game's shelve config, wiring loom, and physical tile layout differ.

---

## 3. Onsite checklist

Run in order. Do not skip ahead if a step fails — fix it before moving on,
since later steps assume earlier ones are correct.

- [ ] **3.1 — Confirm shelve config.** From `games/`:
  ```
  python -c "import shelve; db=shelve.open('setting/led_parameter',flag='r'); [print(k,'=',db[k]) for k in db.keys()]; db.close()"
  ```
  Note `list_com_info` (floor COM port + range), `led_layout_type`,
  `value_high`/`value_width` (should read 6/16), `list_wall_com_info`,
  `list_screen_com_info`.

- [ ] **3.2 — Confirm COM ports are visible to Windows** (Device Manager
  → Ports (COM & LPT), or `python -c "import serial.tools.list_ports;
  [print(p) for p in serial.tools.list_ports.comports()]"`). The floor
  port from `list_com_info` must appear.

- [ ] **3.3 — Run `games/test_hardware.py`** (already exists in this
  repo — floor-only diagnostic, does not touch wall/screen COM ports):
  ```
  cd games
  python test_hardware.py
  ```
  Expected: `All COM ports opened OK`, floor lights solid green for 3s,
  stepping on a tile during the 5s read window prints `PRESS detected:
  row=X col=Y`, then `Floor cleared. Done.`

- [ ] **3.4 — Verify the full 6×16 grid maps correctly to physical
  positions.** This is the step most likely to surface a first-time
  bring-up bug (see troubleshooting below). Do not just glance at the
  green flood from 3.3 — with the floor lit, walk the full perimeter and:
  - Confirm row 0 is the physically-correct edge (e.g. entrance side, per
    the venue layout), not the opposite edge (row/mirror flip).
  - Confirm column 0 is the physically-correct side (not left/right
    mirrored).
  - Send a single-tile test pattern (e.g. only `[3][5]` lit) and confirm
    it lights the tile a human would call "row 3, column 5" — not an
    adjacent tile (catches off-by-one indexing) and not a mirrored one
    (catches transposition).
  - Check the 25 "no-use" cells from `floor_layout_coors_no_use` (the
    `(0,12)..(5,15)`-ish block in the dev shelve) — confirm those really
    are physically absent/inactive tiles on the real floor, not tiles
    that exist but got excluded by a stale coordinate list.

- [ ] **3.5 — Wall lights: confirm expected behavior before assuming a
  bug.** Given the gap in section 1, do not spend time debugging wall
  lights as if they were supposed to already work — first confirm with
  whoever owns the venue hardware whether wall lights are (a) expected to
  be driven by this software at all, (b) driven by a separate legacy
  controller unaffected by this port, or (c) simply not part of this
  deployment. Only escalate as a "bug" if the answer is (a).

- [ ] **3.6 — Start full stack with hardware mode on:**
  ```
  set USE_SERIAL_HD=1
  python -m uvicorn api.main:app --host 0.0.0.0 --port 8001
  ```
  Expected log: `Hardware ready: 1 port(s), 6×16, layout=5` (or whatever
  the real shelve reports). If it instead logs `Hardware init failed:
  ...`, hardware mode silently fell back to sim-only for that session —
  treat as a failed step, not a warning to ignore.

- [ ] **3.7 — Play one full marathon session end-to-end on real
  hardware**, not just a single level: start from `/login` through the
  full level sequence to natural session end (timeout, or life
  exhausted, or sequence cleared). Confirm the floor tracks the
  simulator throughout — no lag, no stuck tiles, no silent HW disconnect
  partway through (check `logs/api.log` for repeated `HW I/O:` warnings,
  which indicate the try/except is swallowing serial errors frame after
  frame).

- [ ] **3.8 — Confirm laser-beam hazard timing feels right physically.**
  The simulator's timing was tuned by eye on a browser canvas; a 6×16
  physical floor has a different visual scale and possibly serial
  latency the browser never had. Specifically check:
  - Does the "warning" phase before a beam fires give a player enough
    physical time to react (step off the tile) at real walking speed?
  - Does `_HW_DRAW_INTERVAL` (default 0.045s ≈ 22fps) look smooth on the
    real floor, or does the sweep look laggy/stepped compared to the
    simulator's redraw rate? If laggy, that's a hardware-only symptom —
    the simulator won't show it.

- [ ] **3.9 — Confirm the blank-on-stop fix actually blanks the physical
  floor** (implemented in this pass — see below). Test all four paths:
  - Let a level run to session timeout (no manual stop) → floor should
    go fully dark within ~1s of the simulator showing the scoreboard.
  - Force life to 0 with time remaining, then let it exhaust for real
    (not a mid-level restart) → floor blanks.
  - Manually trigger `/logout` mid-session → floor blanks.
  - Start a second game while the first's stale pattern would otherwise
    still be showing → confirm `clear_all()`'s blank fires before the new
    game's first real frame draws over it.

---

## 4. Troubleshooting — first-time bring-up

Since this is genuinely untested, don't assume a mismatch from the
simulator's behavior means the game logic is wrong — check hardware
wiring/config explanations first, in this order:

**COM port ordering wrong (floor lights, but pattern is scrambled/rotated
across ports — n/a here since laser is 1 port, but relevant if the venue
combines floor+wall+screen onto one multi-port bus):**
- Check X before assuming Y: before assuming `led_control.py`'s
  `init_com`/`draw_screen_by_com` logic has a bug, verify `list_com_info`
  in the shelve lists the port names in the SAME order the physical
  cables are actually run in. A single floor port makes this unlikely
  for laser, but if the venue technician re-cabled anything, re-check
  this first.

**Row/col transposed (grid looks rotated 90°, or a horizontal sweep
appears vertical):**
- Check X before assuming Y: before assuming the game's pattern-generation
  logic is broken, dump `value_high`/`value_width` from the shelve and
  confirm they really are `6`/`16` (rows/cols) and not swapped — a
  transposed shelve value is indistinguishable from a code bug by just
  watching the floor. Also check `led_layout_type` (`5` in dev) actually
  matches the physical serpentine wiring direction on this floor, not a
  different game's floor the shelve was cloned from.

**Off-by-one grid indexing (one edge row/col never lights, or presses on
the last row/col register on the wrong tile):**
- Check X before assuming Y: before assuming `draw_screen_by_com`'s
  internal indexing is wrong, confirm `floor_layout_coors_no_use` isn't
  accidentally excluding a live tile (it's a hand-maintained list of
  dead/absent cells — stale entries look exactly like an off-by-one bug).
  Also re-run the single-tile test from checklist 3.4 at both grid
  corners `(0,0)` and `(5,15)` specifically — off-by-one bugs usually
  only show at an edge, not in the middle of the grid.

**Floor doesn't light at all:**
- Check `init_com`'s return value (logged as `HW init COM errors
  (non-fatal): ...` if non-empty) before assuming the game loop itself
  is broken — a failed port open is silent to the game (by design, so a
  serial glitch can't crash a session) but means every draw call is a
  no-op.

**Sensors don't register / register on the wrong tile:**
- This game inherits the same decompiled `read()` reverse-index
  suspicion documented for the other games (see
  `docs/HARDWARE_MODE.md`/`docs/STATUS_HARDWARE.md` if present, and
  led-hoops' hardware notes) — if presses are consistently offset by a
  fixed row/col delta, look at index math in `games/led/led_control.py`'s
  `read()`/`update_screen_state_by_com` before assuming the sensor
  hardware itself is faulty.

---

## 5. This pass's change — blank-on-stop fix

Added `_hw_blank_floor(led_table=None)` in `api/game_manager.py`, called
at every place a session/game ends: the `no_levels` early return, normal
session-end, the outer exception handler, `stop_game()` (used by
`/logout`), and `clear_all()` (called at the start of every new game).
It reuses the same `draw_screen_by_com` call as normal gameplay frames,
with an all-`[0,0,0]` grid, gated by the same
`USE_SERIAL_HD and _hw_led_control is not None` check and the same
`_hw_serial_lock`. This has only been checked with `ast.parse` for
syntax validity — **actually confirming it blanks a physical floor
requires the onsite test in checklist item 3.9.**
