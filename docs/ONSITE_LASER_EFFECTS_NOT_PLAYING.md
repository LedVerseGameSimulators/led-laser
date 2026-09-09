# Onsite — Laser Effects Not Playing (RCA + Fix Handoff)

**Date:** 2026-09-09  
**Repo:** `led-laser` (`main`)  
**Symptom:** Countdown / level-clear (and often level-fail) effects do **not** light the floor on real hardware. API phase may still flip (`countdown` → `playing`), so levels look like they skip transitions.

---

## Read these first (in this repo)

| Doc | Why |
|-----|-----|
| **This file** | Laser-focused RCA + what to do onsite |
| [ONSITE_HEX_LASER_EFFECTS_GRID_PARITY.md](./ONSITE_HEX_LASER_EFFECTS_GRID_PARITY.md) | Full Grid vs Hex vs Laser comparison + 18-item checklist |
| [EFFECTS_SPEC.md](./EFFECTS_SPEC.md) | Laser effect asset / timing rules |
| [EFFECTS_IMPLEMENTATION_PLAN.md](./EFFECTS_IMPLEMENTATION_PLAN.md) | Existing Laser effects plan |

---

## Grid reference (clone / browse — working onsite)

Grid is the proven reference for transition effects. Use its code; do **not** invent a new effects pipeline from scratch.

| What | Link |
|------|------|
| **Grid repo** | https://github.com/LedVerseGameSimulators/led-grid |
| **Clone** | `git clone https://github.com/LedVerseGameSimulators/led-grid.git` |
| **Effect runner** | https://github.com/LedVerseGameSimulators/led-grid/blob/main/api/effects_runner.py |
| **HW init + draw** (`com_is_block=False`, `_hw_draw_floor`, `_publish_led_frame`) | https://github.com/LedVerseGameSimulators/led-grid/blob/main/api/game_manager.py |
| **Laser repo (this)** | https://github.com/LedVerseGameSimulators/led-laser |

Laser files to change locally:

- `api/effects_runner.py` — `play_effect_led()`, `hold_last_frame()`
- `api/game_manager.py` — `_hw_init()`, `_hw_draw_effect()`, `_run_countdown()`, `_run_transition()`
- Assets: `games/source/effects/{countdown,level_clear,level_fail}.led`

---

## Ranked causes (Laser)

1. **Fragile effect pixels** — effects use flag tables + `redraw_led_table_default()`; Grid builds RGB **directly from floor groups**. If redraw yields black, HW stays dark while phase advances.
2. **`play_effect_led` return ignored** — load failure → session continues with zero-duration “effect”.
3. **`_hw_init` missing Grid serial hardening** — no `com_is_block=False` / short port timeouts; draw exceptions logged as `HW effect draw failed:` and swallowed.
4. **Effect draw path ≠ gameplay draw** — raw `led_table` vs `floor_display`, no throttle; last-frame hold can republish black.

Level advance does **not** wait on effect success — missing effects look like skipped countdown/clear, not a stuck level.

---

## Fix direction (match Grid patterns; keep Laser-specific)

**Port from Grid**

- Direct group→RGB effect frame builder (or proven non-black redraw)
- Check `play_effect_led` return; log `Effect playback skipped:`
- `_hw_init`: `com_is_block=False` + port timeouts; force `Setting.USE_SERIAL_HD=True` when env HW is on
- Unified HW draw helper + clear `HW effect draw failed:` logs

**Keep Laser-specific**

- Blank **walls** during countdown (`wall_display`)
- `countdown_label` including GO
- `hold_last_frame` if still needed for stinger UX
- 6×12 floor matrices (do **not** copy Grid 16×26 assets)

Full checklist: Phase 1 (shared) + Phase 3 (Laser) in [ONSITE_HEX_LASER_EFFECTS_GRID_PARITY.md](./ONSITE_HEX_LASER_EFFECTS_GRID_PARITY.md).

---

## Onsite verify (grep API logs)

```bash
grep -E 'Hardware ready|HW init COM|HW effect draw failed|Effect load failed|Effect playback skipped|send  led color data' /path/to/laser-api.log
```

| Expect | Meaning |
|--------|---------|
| `Hardware ready: … 6×12` (or shelve dims) | Init OK |
| No `Effect load failed` | Assets present under `games/source/effects/` |
| No `HW effect draw failed` during countdown/clear | Serial draw OK |
| Floor lights during `phase=countdown` / `level_clear` | Effects actually playing |

Confirm deploy includes `games/source/effects/*.led` and `USE_SERIAL_HD=1`.

---

## Out of scope for this effects pass

- Wave / level-length content (Hoops/Hex long-level docs — other games)
- Laser life-loss cooldown tuning (separate product ask)
- Blindly copying Hex 3-ring / 5×9 logic into Laser
