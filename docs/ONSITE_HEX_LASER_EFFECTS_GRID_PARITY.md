# Onsite Hex / Laser Effects — Grid Parity Plan

**Date:** 2026-09-09  
**Scope:** Transition and game-start effects (`countdown.led`, `level_clear.led`, `level_fail.led`) for **led-hexagon** and **led-laser**, using **led-grid** as the onsite-proven reference.  
**Related (Laser handoff):** [ONSITE_LASER_EFFECTS_NOT_PLAYING.md](./ONSITE_LASER_EFFECTS_NOT_PLAYING.md)

**Grid reference (GitHub):**
- Repo: https://github.com/LedVerseGameSimulators/led-grid
- Effects runner: https://github.com/LedVerseGameSimulators/led-grid/blob/main/api/effects_runner.py
- Game manager (HW init / draw): https://github.com/LedVerseGameSimulators/led-grid/blob/main/api/game_manager.py

---

## Goal

Bring Hex and Laser transition effects to **Grid-equivalent reliability onsite**:

1. Every level start runs `countdown.led` with floor + UI roughly in sync.
2. Mid-session clear/fail runs the correct `.led` hold, stinger, then countdown (or session-end black with no countdown).
3. Hardware draw failures are **visible in logs**, not silent blank floors.
4. Input stays gated (`accepting_input=false`) during all effect phases.

Grid already satisfies (1)–(4) onsite. Hex and Laser have wired effect loops and assets, but diverge in frame publishing, HW I/O, and error handling — those gaps are what this doc tracks.

---

## Current State Table (Grid / Hex / Laser)

| Area | **Grid** (onsite reference) | **Hex** | **Laser** |
|------|----------------------------|---------|-----------|
| **Effect module** | `api/effects_runner.py` → `run_effect_led()` | Inline `_run_effect_led()` in `api/game_manager.py` | `api/effects_runner.py` → `play_effect_led()` + `hold_last_frame()` |
| **Frame source** | Builds flat RGB from `floor_light` groups via `_effect_led_display()` | Reads full `led_table.led_table`; normalizes **3 rings** via `_normalize_rings()` | Calls `led_table.redraw_led_table_default(draw_canvas=False)` then reads flat `(r,g,b)` cells |
| **Effect load path** | `_run_level_attempt()` + `transition_consumer=begin_level_transition` | Direct `_load_level_file()` + `play.running(dg_eff)` | `_load_level_file()` inside `play_effect_led()` |
| **HW draw (effects)** | `_publish_led_frame()` → `_hw_draw_floor()` under `_hw_serial_lock`; throttled by `_HW_DRAW_INTERVAL` | Inline `draw_screen_by_com()` in effect callback; log: `HW I/O (effect): …` | `_hw_draw_effect()` passed into runner; log: `HW effect draw failed: …` |
| **HW init** | `_hw_init()` from shelve; logs `Hardware ready: N port(s), R×C`; COM errors **non-fatal** warning; sets `com_is_block=False` | Same shelve read (**5×9 onsite**); forces `Setting.USE_SERIAL_HD=True`; COM errors non-fatal; **no** `com_is_block` override | Same shelve read (**6×12 floor**); COM errors non-fatal; **no** `com_is_block` override |
| **Transition gating** | `begin_level_transition()` / `finish_level_transition()` on gameplay reload; effects call `begin_level_transition` via `_run_level_attempt` | Gameplay uses begin/finish; **effects only** call `_set_phase()` — no transition lock around effect playback | Manual `accepting_input=False`; effects do **not** call `begin_level_transition()` |
| **Stinger timing** | Stinger after effect `.led` completes; no explicit frame-hold loop | `_run_clear_hold()` / `_run_fail_hold()` → effect then `audio.play_stinger()` | Effect → `hold_last_frame()` (~2.5 s republish) → stinger |
| **Countdown sync field** | `countdown_digit` (3 \| 2 \| 1) | `countdown_step` / `phase_step` (3 \| 2 \| 1; **no GO**) | `countdown_label` (`"3"` \| `"2"` \| `"1"` \| `"GO"`) |
| **Floor footprint** | 16×26 logical; HW dims from shelve | **16×26 `LedTable`** for gameplay; **HW + effect `.led` at 5×9 / 33 live cells** | 6×12 floor + separate **wall lights** |
| **Wall during countdown** | N/A (floor only) | N/A (floor only) | `wall_display` forced blank during countdown / session_end |
| **Effect assets** | ✅ `games/source/effects/*.led` | ✅ present | ✅ present |
| **Missing-effect behavior** | Warn `Effect archive missing:` → phase set, **session continues** (blank floor) | Warn `Missing effect archive:` → phase set, **continues** | Warn `Effect load failed:` → `play_effect_led` returns `False`, **callers ignore return** |
| **Session-end path** | `_finish_session()` → clear hold (unless chain exhausted) → stinger → black | `_finish_session()` → clear hold → stinger → `_hw_blank_floor()` | `_finish_session()` / `_run_transition(clear)` → stinger hold → black + blank walls |

### Effect path diagram (simplified)

```
                    ┌─────────────┐
  level boundary ──►│ countdown   │──► gameplay + BGM
                    └─────────────┘
                           ▲
     clear/fail ──► transition .led ──► stinger ──┘
                           │
              session end ─┴──► clear .led ──► stinger ──► black (no countdown)
```

---

## Shared Bugs (all three — fix via Grid patterns)

### 1. Silent fail on missing / broken effect files

All three games log a warning and **continue the marathon loop** when an effect archive is missing or fails to load. The frontend may show `phase=countdown` while the physical floor stays black.

| Game | Log string | Code path |
|------|-----------|-----------|
| Grid | `Effect archive missing:` / `Effect load failed` | `led-grid/api/effects_runner.py` |
| Hex | `Missing effect archive:` | `led-hexagon/api/game_manager.py` `_run_effect_led()` |
| Laser | `Effect load failed:` | `led-laser/api/effects_runner.py` `play_effect_led()` |

**Grid parity target:** treat load failure as a **degraded but logged** transition (publish phase, skip HW draw, optionally set `effect_error` in `/game-state`). Do not crash the session; do make the failure grep-able onsite.

### 2. Ignored return values

- **Laser:** `play_effect_led()` returns `bool`; `_run_countdown()` and `_run_transition()` never check it.
- **Grid / Hex:** no boolean return; failures are warn-and-return inside the helper.

**Grid parity target:** check effect runner success; log `Effect playback skipped: <path>` when false; still advance phase so UI does not hang.

### 3. Serial init treated as non-fatal

All three `_hw_init()` implementations log `HW init COM errors (non-fatal): [...]` and proceed. Subsequent effect draws then fail repeatedly (`HW effect draw failed` / `HW I/O (effect)` / `send led color data` tracebacks in `led_control.py`).

**Grid parity target (shared):**

- Log `Hardware ready: …` once on success (already present).
- On COM open failure, log at **warning** and surface `hw_ready=false` (or equivalent) in `/game-state` so onsite knows before starting a player session.
- Port Grid's `com_is_block=False` + short `timeout`/`write_timeout` tuning to Hex and Laser headless API paths.

---

## Hex-Specific Risks (5×9 effect coords)

Hex is the only game in this trio with a **split footprint**: gameplay uses a 16×26 logical buffer; onsite hardware and effect authoring use a **5×9 bounding box with 33 live hex tiles** (12 dead cells).

| Risk | Why it matters | Mitigation |
|------|----------------|------------|
| **Effect coords off-zone** | `.led` groups targeting rows/cols outside 0–4 × 0–8 paint nothing on HW | Author all effect members on the 33 shelve live coords; unit-test group member count = 33 |
| **Dead cells lit in buffer** | Effect callback publishes the full 16×26 flatten; dead coords may carry stale RGB in sim | Zero dead cells each effect frame (or build display from zone-only groups like Grid's `_effect_led_display`) |
| **3-ring encoding** | HW expects `[[R,G,B],[R,G,B],[R,G,B]]` per tile; flat RGB sends wrong colors | Keep `_normalize_rings()` on every effect publish and HW draw (match `_hw_blank_floor` 3-ring blank pattern) |
| **HW 5×9 vs LedTable 16×26** | `draw_screen_by_com` uses shelve rows/cols (5×9); indexing mismatch → wrong tile or `rect_position_arr` errors | Confirm `_hw_init` logs `5×9`; validate effect `.led` `para_key_game` zone matches shelve |
| **Countdown semantics** | Hex spec: solid color steps (red→blue→green), **no GO digit** on floor | Keep `countdown_step` 3/2/1 only; do not port Grid/Laser digit glyphs |

**Authoritative footprint doc:** `led-hexagon/docs/EFFECTS_SPEC.md` (5×9 ASCII map).

---

## Laser-Specific Risks (flag / redraw path)

Laser gameplay drives the floor through **flag tables** (`red_table`, `blue_table`, `plus_table`, …) consumed by `redraw_led_table_default()`. Effect playback reuses that path — different from Grid's direct group→RGB builder.

| Risk | Why it matters | Mitigation |
|------|----------------|------------|
| **Flag / redraw dependency** | `play_effect_led()` calls `redraw_led_table_default()` each frame; if effect `.led` groups do not tag flags, floor stays black | Verify effect archives populate floor groups the same way gameplay levels do; add fallback direct RGB builder (Grid pattern) if redraw yields empty |
| **Wall vs floor split** | Countdown must blank **walls** while showing floor digits/patterns | Keep `_blank_wall_display()` on countdown / session_end; confirm wall HW not written during effect phases |
| **Stinger hold loop** | `hold_last_frame()` republishes + `_hw_draw_effect` for ~2.5 s — extra serial traffic | Accept for Laser UX; ensure exceptions inside hold loop log `HW effect draw failed` (already wrapped) |
| **6×12 anchor coords** | `level_clear.led` expand animation anchored at row 3 / col 6 per spec | Re-run `scripts/build_effect_led.py` after spec fixes; do not copy Grid 16×26 matrices |
| **Dual serial domains** | Floor + wall strips have separate `init_com` paths in legacy GUI | API marathon must init **floor** COM via `_hw_init()`; wall scoring/display is separate — do not assume one draw call clears both |

**Laser effect builder:** `led-laser/scripts/build_effect_led.py`  
**Laser spec:** `led-laser/docs/EFFECTS_SPEC.md`

---

## What to Port from Grid vs Game-Specific

### Port from Grid (shared — do first)

| Pattern | Grid location | Apply to Hex / Laser |
|---------|---------------|----------------------|
| Dedicated `effects_runner.run_effect_led()` | `led-grid/api/effects_runner.py` | Extract Hex inline runner; align Laser runner API |
| `_publish_led_frame()` helper with throttled HW draw + unified log `HW effect draw failed` | `led-grid/api/game_manager.py` `_publish_led_frame` | Replace duplicated inline HW blocks |
| `_hw_draw_floor()` + `_hw_blank_floor()` | `led-grid/api/game_manager.py` | Hex: extend for 3-ring cells; Laser: keep wall blank separate |
| `begin_level_transition()` before effect load | via `_run_level_attempt(..., transition_consumer=…)` | Call at start of every `_run_countdown` / clear / fail |
| `finish_level_transition()` after gameplay reload | gameplay `_run_level_attempt` | Already on Hex gameplay; add to Laser level reload path |
| Effect load error logging | `Effect archive missing` / `Effect load failed` | Standardize message prefix: `Effect playback:` |
| Headless serial tuning | `com_is_block=False`, port timeouts | Copy to Hex + Laser `_hw_init()` |
| Session-end pseudocode | stop BGM → clear.led → stinger → black, no countdown | Already documented in GLOBAL_RULES; verify Laser `sequence_exhausted_after_clear` skip |

### Keep game-specific (do not blindly copy Grid)

| Game | Keep |
|------|------|
| **Hex** | 3-ring `_normalize_rings()`; 5×9 / 33-cell effect authoring; solid-color countdown (no digits); `countdown_step` not `countdown_digit` |
| **Laser** | Wall display blanking; `countdown_label` with GO; `hold_last_frame()` stinger hold; 6×12 floor matrices; `redraw_led_table_default()` **or** replace with Grid-style builder **only after** validating `.led` group types |
| **Grid** | 16×26 matrices; green digit groups in `countdown.led`; no wall channel |

---

## Implementation Checklist (phased)

### Phase 1 — Shared Grid patterns (Hex + Laser)

- [ ] **P1.1** Standardize effect runner interface: `run_effect_led(path, *, game, phase, publish_frame, hw_draw_fn, audio, stop_flag) -> bool`
- [ ] **P1.2** Unify HW draw wrapper; log **`HW effect draw failed:`** on all exceptions (replace Hex `HW I/O (effect):` alias)
- [ ] **P1.3** Port Grid `_hw_init()` serial tuning (`com_is_block=False`, port timeouts) to Hex and Laser
- [ ] **P1.4** Call `begin_level_transition()` at the start of every countdown / clear / fail effect
- [ ] **P1.5** Check effect runner return value; log **`Effect playback skipped:`** when load/play fails
- [ ] **P1.6** Publish `accepting_input=false` for entire effect + stinger window (verify `/game-input` returns ignored)
- [ ] **P1.7** Session-end: `level_clear.led` → stinger → `_hw_blank_floor()` → `phase=session_end` with **no** following countdown (all three)
- [ ] **P1.8** Life=0 with ≤10 s left → clear path only, **not** `level_fail.led` (all three)

### Phase 2 — Hex-only

- [ ] **P2.1** Validate effect `.led` archives: 3 countdown groups + 1 clear + 1 fail; **33 members** each on 5×9 live coords
- [ ] **P2.2** Effect publish path zeros **12 dead cells** or builds from zone groups (Grid `_effect_led_display` style)
- [ ] **P2.3** HW draw sends **3-ring** cells; confirm onsite log `Hardware ready: … 5×9`
- [ ] **P2.4** Extract inline `_run_effect_led()` to `led-hexagon/api/effects_runner.py` matching Grid module shape
- [ ] **P2.5** Align frontend on `countdown_step` / `phase_step` (~0.8 s); no GO label on floor

### Phase 3 — Laser-only

- [ ] **P3.1** Audit effect callback: confirm `redraw_led_table_default()` produces non-black frames for all three `.led` files
- [ ] **P3.2** If redraw fails, add Grid-style `_effect_led_display()` fallback for effect phases only
- [ ] **P3.3** Countdown: floor pattern + **`wall_display` all black**; verify wall serial not spammed during effects
- [ ] **P3.4** Keep `hold_last_frame()` through stinger unless Grid-style hold proves sufficient onsite
- [ ] **P3.5** Rebuild effect assets from `scripts/build_effect_led.py` with col-6 clear anchor per spec

**Checklist total: 18 items** (P1: 8 · P2: 5 · P3: 5)

---

## Onsite Verification (log strings to grep)

Run a full session on hardware (`USE_SERIAL_HD=1`) and grep API / ws_bridge logs:

| When | Grep for | Expect |
|------|----------|--------|
| Game start / HW init | `Hardware ready:` | `5×9` (Hex) · `6×12` (Laser) · Grid dims match shelve |
| COM problems | `HW init COM errors (non-fatal)` | Empty on healthy rig; if present, fix before player-facing test |
| Level start | `phase=countdown` or state poll `countdown` | Floor shows countdown pattern |
| Effect HW fault | `HW effect draw failed` | **Absent** during normal play |
| Legacy serial fault | `send  led color data` | **Absent** (indicates uncaught `led_control` exception) |
| Missing asset | `Effect archive missing` · `Missing effect archive` · `Effect load failed` | **Absent** in production deploy |
| Skipped playback (after P1.5) | `Effect playback skipped` | **Absent** in production deploy |
| Mid-session clear | `✓ Level` then `level_clear` phase | Followed by countdown, not straight to `playing` |
| Life restart | `↻ Life restart` | Preceded by `level_fail` phase |
| Session end | `HW: blank frame sent` (Hex) or quiet blank after stinger | Floor dark; no countdown after `session_end` |
| Input gating | (functional) POST `/game-input` during `countdown` | Ignored / no score change |

**Suggested command:**

```bash
grep -E 'Hardware ready|HW init COM|HW effect draw failed|HW I/O \(effect\)|Effect archive missing|Missing effect archive|Effect load failed|Effect playback skipped|send  led color data|↻ Life restart|✓ Level|session_end|blank frame' /path/to/api.log
```

---

## Out of Scope

The following are **not** part of this Grid-parity effects pass:

| Topic | Reason | See instead |
|-------|--------|-------------|
| **Wave / stagger progression** during gameplay levels | Gameplay mechanic, not transition `.led` | [`led-hexagon/docs/LEVELS.md`](../led-hexagon/docs/LEVELS.md) — pro-series 40 s wave intervals |
| **Sweep speed tuning** on the physical hex floor | Gameplay `game_level_speed` calibration | [`led-hexagon/docs/STATUS_HARDWARE.md`](../led-hexagon/docs/STATUS_HARDWARE.md) § Step 5 — Sweep speed |
| **Respawn / 2P `.ledb` progression** | Level content, not effects | [`led-hexagon/docs/LEVELS.md`](../led-hexagon/docs/LEVELS.md) |
| **Laser wall scoring / hazard flags during gameplay** | Gameplay loop, not transition effects | `led-laser/api/game_manager.py` frame callback |
| **16×26 → 5×9 LedTable migration (Hex Phase B)** | Deferred footprint refactor | [`led-hexagon/docs/EFFECTS_IMPLEMENTATION_PLAN.md`](../led-hexagon/docs/EFFECTS_IMPLEMENTATION_PLAN.md) § Phase B |

---

## Quick Reference — Key Files

| Game | Effect runner | Marathon loop | HW draw |
|------|---------------|---------------|---------|
| Grid | `led-grid/api/effects_runner.py` | `led-grid/api/game_manager.py` ~L1890+ | `_hw_draw_floor()` |
| Hex | `led-hexagon/api/game_manager.py` `_run_effect_led()` | same ~L1740+ | inline in effect callback |
| Laser | `led-laser/api/effects_runner.py` | `led-laser/api/game_manager.py` ~L1660+ | `_hw_draw_effect()` |
