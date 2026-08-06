"""Effect .led playback helpers for Laser marathon transitions."""
from __future__ import annotations

import os
import time
from pathlib import Path

from loguru import logger

from .config import GAMES_ROOT

STINGER_HOLD_SEC = float(os.environ.get("LASER_STINGER_HOLD_SEC", "2.5"))


def effects_dir() -> Path:
    override = os.environ.get("LASER_EFFECTS_DIR")
    if override:
        return Path(override)
    return GAMES_ROOT / "source" / "effects"


def countdown_label(total_pass: float, *, fast: bool = False) -> str:
    if fast or STINGER_HOLD_SEC < 1.0:
        if total_pass < 0.05:
            return "3"
        if total_pass < 0.10:
            return "2"
        if total_pass < 0.15:
            return "1"
        return "GO"
    if total_pass < 1.0:
        return "3"
    if total_pass < 2.0:
        return "2"
    if total_pass < 3.0:
        return "1"
    return "GO"


def _is_fast_effects() -> bool:
    cd = effects_dir() / "countdown.led"
    if not cd.exists():
        return False
    # Heuristic: test fixtures live under tests/fixtures
    return "fixtures" in str(cd)


def _publish_floor(game, led_table, floor_rows, floor_cols, phase, label=None):
    floor_display = []
    for ri in range(floor_rows):
        for ci in range(floor_cols):
            fc = led_table.led_table[ri][ci]
            if isinstance(fc, (list, tuple)) and len(fc) >= 3:
                floor_display.append([int(fc[0]), int(fc[1]), int(fc[2])])
            else:
                floor_display.append([0, 0, 0])
    kwargs = dict(
        phase=phase,
        accepting_input=False,
        floor_display=floor_display,
        grid_rows=floor_rows,
        grid_cols=floor_cols,
    )
    if label is not None:
        kwargs["countdown_label"] = label
    game.update_state(**kwargs)


def hold_last_frame(game, led_table, hw_draw_fn, phase: str, seconds: float | None = None):
    hold = seconds if seconds is not None else STINGER_HOLD_SEC
    floor_rows, floor_cols = led_table.led_row, led_table.led_col
    end = time.time() + hold
    while time.time() < end and game.running:
        _publish_floor(game, led_table, floor_rows, floor_cols, phase)
        if hw_draw_fn:
            hw_draw_fn(led_table)
        time.sleep(0.01)


def play_effect_led(
    path,
    game,
    led_table,
    play,
    load_level_fn,
    *,
    phase: str,
    audio=None,
    hw_draw_fn=None,
    countdown_ticks: bool = False,
) -> bool:
    """Load and run one effect .led; returns False if load failed."""
    dg, _go = load_level_fn(path)
    if not dg:
        logger.warning(f"Effect load failed: {path}")
        return False

    fast = _is_fast_effects()
    floor_rows, floor_cols = led_table.led_row, led_table.led_col
    last_label = None

    max_end = max((getattr(g, "end_time_sec", 0) for g in dg.values()), default=0.0)

    def _effect_cb(_play_self, _dgroup, _time_pass, total_pass):
        if not game.running:
            return False
        if total_pass >= max_end:
            return False
        try:
            led_table.redraw_led_table_default(draw_canvas=False)
            label = None
            if phase == "countdown":
                label = countdown_label(total_pass, fast=fast)
                nonlocal last_label
                if audio and label != last_label:
                    if label in ("3", "2", "1") and countdown_ticks:
                        audio.tick_on_second(int(label))
                    last_label = label
            _publish_floor(game, led_table, floor_rows, floor_cols, phase, label)
            if hw_draw_fn:
                hw_draw_fn(led_table)
            time.sleep(0.01)
            return True
        except Exception as e:
            logger.error(f"Effect callback error: {e}")
            return False

    prev_cb = play.callback
    play.callback = _effect_cb
    play.running_state = True
    play.total_pass = 0
    play.game_level_speed = 1.0
    try:
        play.running(dg)
    finally:
        play.callback = prev_cb
    return True
