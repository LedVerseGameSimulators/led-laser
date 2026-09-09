#!/usr/bin/env python3
"""Build Laser effect .led files (countdown, level_clear, level_fail).

Usage:
  python scripts/build_effect_led.py [--fast] [--out DIR]

--fast writes short-duration fixtures under tests/fixtures/effects/
Default writes production files under games/source/effects/
"""
from __future__ import annotations

import argparse
import dbm.dumb
import os
import shelve
import sys
import tempfile
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GAMES = REPO / "games"
sys.path.insert(0, str(GAMES))

from model.game import Game  # noqa: E402
from model.group import Group  # noqa: E402
from model.setting import Color, Setting  # noqa: E402

# Levels on this venue are authored mostly as Color.RED (254,0,0). The physical
# beams look green, but the emitter controller keys off that same channel —
# Color.GREEN (0,254,0) does not light the array. Effects must match levels.
FX_COLOR = Color.RED
WORKING = [(0, 6), (0, 12)]  # cols 0-11 on 6 rows
ROWS, COLS = 6, 16


def _all_working():
    return [(r, c) for r in range(ROWS) for c in range(12)]


def _all_grid():
    return [(r, c) for r in range(ROWS) for c in range(COLS)]


# Simple digit bitmaps anchored near col 6, row 2 (valid rows 0..5)
_DIGIT_3 = [
    (1, 5), (1, 6), (1, 7),
    (2, 7),
    (3, 5), (3, 6), (3, 7),
    (4, 7),
    (5, 5), (5, 6), (5, 7),
]
_DIGIT_2 = [
    (1, 5), (1, 6), (1, 7),
    (2, 5),
    (3, 5), (3, 6), (3, 7),
    (4, 7),
    (5, 5), (5, 6), (5, 7),
]
_DIGIT_1 = [
    (1, 6), (1, 7),
    (2, 6),
    (3, 6),
    (4, 6),
    (5, 5), (5, 6), (5, 7),
]
_LETTER_G = [
    (1, 4), (1, 5), (1, 6),
    (2, 4),
    (3, 4), (3, 5), (3, 6), (3, 7),
    (4, 4), (4, 7),
    (5, 4), (5, 5), (5, 6),
]
_LETTER_O = [
    (1, 9), (1, 10), (1, 11),
    (2, 9), (2, 11),
    (3, 9), (3, 11),
    (4, 9), (4, 11),
    (5, 9), (5, 10), (5, 11),
]


def _floor_group(name, cells, t0, t1, gid):
    return Group(
        name=name,
        member=list(cells),
        start_time_min=0,
        start_time_sec=t0,
        end_time_min=0,
        end_time_sec=t1,
        color=FX_COLOR,
        speed=0,
        direct=Setting.STATIC,
        edge_run_into=Setting.DISAPPEAR,
        gtype=Setting.FLOOR_LIGHT,
        text=[],
        scale=Setting.SIDE_BOTH,
        start_area=1,
        activity_area=WORKING,
    )


def _countdown_phases(fast: bool):
    if fast:
        return [
            ("digit_3", _DIGIT_3, 0.0, 0.05),
            ("digit_2", _DIGIT_2, 0.05, 0.10),
            ("digit_1", _DIGIT_1, 0.10, 0.15),
            ("go", _LETTER_G + _LETTER_O, 0.15, 0.25),
        ]
    full = _all_working()
    pulse = 0.15
    return [
        ("digit_3", _DIGIT_3, 0.0, 1.0 - pulse),
        ("pulse_3", full, 1.0 - pulse, 1.0),
        ("digit_2", _DIGIT_2, 1.0, 2.0 - pulse),
        ("pulse_2", full, 2.0 - pulse, 2.0),
        ("digit_1", _DIGIT_1, 2.0, 3.0 - pulse),
        ("pulse_1", full, 3.0 - pulse, 3.0),
        ("go", _LETTER_G + _LETTER_O, 3.0, 5.0),
    ]


def _clear_phases(fast: bool):
    """Simple all-on / all-off blink (~2s production), then countdown follows."""
    full = _all_grid()
    if fast:
        # Tiny fixture: one on/off cycle
        return [
            ("blink_on", full, 0.0, 0.05),
            ("blink_off", [], 0.05, 0.10),
            ("blink_on2", full, 0.10, 0.15),
            ("blink_off2", [], 0.15, 0.20),
        ]
    # 2.0s total: 0.25s on / 0.25s off × 4
    phases = []
    t = 0.0
    half = 0.25
    for i in range(4):
        phases.append((f"blink_on_{i}", full, t, t + half))
        t += half
        phases.append((f"blink_off_{i}", [], t, t + half))
        t += half
    return phases


def _fail_phases(fast: bool):
    full = _all_working()
    flicker1 = [(1, 2), (2, 8), (4, 3), (5, 9), (0, 6), (3, 1), (5, 5), (2, 10)]
    flicker2 = [(0, 4), (3, 9), (5, 2), (1, 7), (4, 10), (2, 3), (5, 8), (0, 11)]
    flicker3 = [(2, 5), (4, 7), (1, 1), (5, 6), (3, 3), (0, 8), (4, 4), (2, 11)]
    block = [(r, c) for r in range(2, 5) for c in range(4, 8)]
    sparse = [(5, 0), (3, 7), (1, 9), (4, 2)]
    if fast:
        return [
            ("full_on", full, 0.0, 0.05),
            ("flicker1", flicker1, 0.05, 0.07),
            ("flicker2", flicker2, 0.07, 0.09),
            ("flicker3", flicker3, 0.09, 0.11),
            ("block", block, 0.11, 0.14),
            ("sparse", sparse, 0.14, 0.17),
            ("off", [], 0.17, 0.25),
        ]
    return [
        ("full_on", full, 0.0, 0.3),
        ("flicker1", flicker1, 0.30, 0.35),
        ("flicker2", flicker2, 0.35, 0.40),
        ("flicker3", flicker3, 0.40, 0.45),
        ("block", block, 0.6, 0.9),
        ("sparse", sparse, 0.9, 1.2),
        ("off", [], 1.2, 2.0),
    ]


def _build_dict_group(phases):
    dg = {}
    for i, (name, cells, t0, t1) in enumerate(phases):
        # Keep empty "off" timing groups so max_end includes the dark gaps.
        if cells or t1 > t0:
            dg[i] = _floor_group(name, cells or [], t0, t1, i)
    return dg


def _make_game(name: str) -> Game:
    return Game(
        name=name,
        row=ROWS,
        col=COLS,
        game_level=Setting.STANDARD,
        zone_row_from=0,
        zone_row_to=ROWS,
        zone_col_from=0,
        zone_col_to=12,
        zone_scale=Setting.NO,
        wall_light=Setting.NO,
        screen=Setting.NO,
        corner_line_start=0,
    )


def _write_led(out_path: Path, effect_name: str, dict_group):
    go = _make_game(effect_name)
    go.play_order = False

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        inner = Path(tmp) / effect_name
        inner.mkdir()
        db_path = str(inner / "game_file")
        # dbm.dumb → game_file.dat + .dir (matches legacy .led loader)
        db = shelve.Shelf(dbm.dumb.open(db_path, "c"))
        db["para_key_game"] = go
        db["dict_group"] = dict_group
        db.close()
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for fn in os.listdir(inner):
                zf.write(inner / fn, f"{effect_name}/{fn}")


def build_all(out_dir: Path, fast: bool):
    specs = {
        "countdown": _countdown_phases(fast),
        "level_clear": _clear_phases(fast),
        "level_fail": _fail_phases(fast),
    }
    for name, phases in specs.items():
        path = out_dir / f"{name}.led"
        _write_led(path, name, _build_dict_group(phases))
        print(f"Wrote {path}")


def build_test_level(out_path: Path):
    """Minimal gameplay level: one scoreable wall, short duration."""
    go = _make_game("quick_score")
    go.play_order = False
    dg = {
        0: Group(
            name="goal",
            member=[2],
            start_time_min=0,
            start_time_sec=0.0,
            end_time_min=0,
            end_time_sec=60.0,
            color=[(0, 0, 254)],
            speed=0,
            direct=Setting.STATIC,
            edge_run_into=Setting.DISAPPEAR,
            gtype=Setting.WALL_LIGHT,
            text=[],
            scale=Setting.SIDE_BOTH,
            start_area=1,
            activity_area=WORKING,
        ),
    }
    _write_led(out_path, "quick_score", dg)


def build_red_hazard_level(out_path: Path):
    """Level with red hazard wall for life drain tests.

    Includes a second scoreable wall (index 3) so the level does not
    auto-clear when remaining_scoreable hits 0 (red is not scoreable).
    """
    go = _make_game("red_drain")
    go.play_order = False
    dg = {
        0: Group(
            name="red",
            member=[2],
            start_time_min=0,
            start_time_sec=0.0,
            end_time_min=0,
            end_time_sec=999.0,
            color=[(254, 0, 0)],
            speed=0,
            direct=Setting.STATIC,
            edge_run_into=Setting.DISAPPEAR,
            gtype=Setting.WALL_LIGHT,
            text=[],
            scale=Setting.SIDE_BOTH,
            start_area=1,
            activity_area=WORKING,
        ),
        1: Group(
            name="decoy_goal",
            member=[3],
            start_time_min=0,
            start_time_sec=0.0,
            end_time_min=0,
            end_time_sec=999.0,
            color=[(0, 0, 254)],
            speed=0,
            direct=Setting.STATIC,
            edge_run_into=Setting.DISAPPEAR,
            gtype=Setting.WALL_LIGHT,
            text=[],
            scale=Setting.SIDE_BOTH,
            start_area=1,
            activity_area=WORKING,
        ),
    }
    _write_led(out_path, "red_drain", dg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true", help="Short durations for pytest")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--test-levels", action="store_true", help="Also build test level fixtures")
    args = ap.parse_args()

    if args.out:
        out_dir = args.out
    elif args.fast:
        out_dir = REPO / "tests" / "fixtures" / "effects"
    else:
        out_dir = REPO / "games" / "source" / "effects"

    build_all(out_dir, args.fast)

    if args.test_levels or args.fast:
        levels = REPO / "tests" / "fixtures" / "levels"
        build_test_level(levels / "quick_score.led")
        build_red_hazard_level(levels / "red_drain.led")
        print(f"Wrote test levels under {levels}")


if __name__ == "__main__":
    main()
