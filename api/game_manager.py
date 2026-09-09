"""
Game Manager - Laser Trap
Manages running Play instances and game state for the Laser wall-button game.
Headless: no tkinter GUI. Input via API (wall_index press/release), output via wall LEDs.
"""
import uuid
import threading
import time
import asyncio
import os
import sys
import math
import json
import shelve as _shelve
from typing import Dict, Optional
from unittest.mock import MagicMock
from loguru import logger
from .config import (
    GAME_TIMEOUT_SECONDS,
    MAX_CONCURRENT_GAMES,
    GAMES_ROOT,
    GAME_GROUP_LEVEL_DIR,
)

USE_SERIAL_HD = os.environ.get("USE_SERIAL_HD", "0") == "1"
if USE_SERIAL_HD:
    _games_dir = str(GAMES_ROOT)
    if _games_dir not in sys.path:
        sys.path.insert(0, _games_dir)

# Mock hardware/network dependencies before importing game_play
# These are not needed for headless game logic:
# - tkinter: GUI (game_running.py imports tkinter.messagebox)
# - encryption: hardware dongle check (yanqian.py checks connected pedrive at module level)
# - led.led_control: hardware LED driver
# - net: network communication

# Mock ALL external dependencies (hardware, GUI, media, etc)
# Standard approach: mock before any imports to prevent ModuleNotFoundError
mocks = {
    # GUI/Display
    'tkinter': MagicMock(),
    'tkinter.messagebox': MagicMock(),
    'tkinter.font': MagicMock(),
    'gui': MagicMock(),
    'gui.app_gui': MagicMock(),
    'gui.gui_debugging': MagicMock(),
    'gui.gui_setting': MagicMock(),
    'gui.language': MagicMock(),
    'gui2': MagicMock(),
    'gui2.gui_led_table_editor': MagicMock(),
    'gui2.gui_led_canvas2': MagicMock(),
    'gui2.gui_table_editor': MagicMock(),
    'gui2.ui_player_setting': MagicMock(),
    'gui2.ui_table': MagicMock(),
    'gui2.gui_util': MagicMock(),
    'ui_design': MagicMock(),
    # Hardware
    **({} if USE_SERIAL_HD else {
        'serial': MagicMock(),
        'serial.tools': MagicMock(),
        'serial.tools.list_ports': MagicMock(),
        'led': MagicMock(),
        'led.led_control': MagicMock(),
        'led.communication': MagicMock(),
        'led.position_convert': MagicMock(),
        'led.led_serial_thread': MagicMock(),
        'led.led_control_c': MagicMock(),
    }),
    'net': MagicMock(),
    'socket': MagicMock(),
    # Audio/Video — do NOT mock pygame/audio_play (venue BGM/SFX need real mixer)
    'moviepy': MagicMock(),
    'moviepy.editor': MagicMock(),
    'cv2': MagicMock(),
    # Input
    'pynput': MagicMock(),
    'pynput.keyboard': MagicMock(),
    'pynput.mouse': MagicMock(),
    # Encryption
    'encryption': MagicMock(),
    'encryption.yanqian': MagicMock(),
    'rsa': MagicMock(),
    'Crypto': MagicMock(),
    'Crypto.Hash': MagicMock(),
    'Crypto.Cipher': MagicMock(),
    'Crypto.PublicKey': MagicMock(),
    'Crypto.Signature': MagicMock(),
    # Database
    'mysql': MagicMock(),
    'mysql.connector': MagicMock(),
    # Image processing
    'numpy': MagicMock(),
    'PIL': MagicMock(),
    'PIL.Image': MagicMock(),
    'PIL.ImageTk': MagicMock(),
}

for mod_name, mock in mocks.items():
    sys.modules[mod_name] = mock

_HW_DEFAULT_ROWS = 6
_HW_DEFAULT_COLS = 16
_HW_DRAW_INTERVAL = float(os.environ.get("HW_DRAW_INTERVAL", "0.045"))
_hw_serial_lock = threading.Lock()

# COM9 emitters (module) + COM7 wall buttons + COM6 beam receivers (LedControl instances)
_hw_led_control = None
_hw_layout_type = 0
_hw_ready = False
_hw_wall_ctrl = None
_hw_wall_ready = False
_hw_recv_ctrl = None
_hw_recv_ready = False
_hw_effect_draw_count = 0
_hw_effect_last_nonzero = 0
_hw_effect_last_phase = None

# COM6: raw True = dark. Intact lit beam → False tread. Do not invert.
_HW_RAW_TRUE_MEANS_INTACT = False


def _normalize_rgb(cell):
    """Ensure [R,G,B] ints. Play.clear_led_table can leave nested tuples."""
    if isinstance(cell, (list, tuple)):
        if len(cell) >= 3 and isinstance(cell[0], (int, float)):
            return [int(cell[0]), int(cell[1]), int(cell[2])]
        if len(cell) == 1:
            return _normalize_rgb(cell[0])
    return [0, 0, 0]


def _hw_init():
    """Open COM9 emit + COM7 wall + COM6 recv independently (soft-fail per port)."""
    global _hw_led_control, _hw_layout_type, _hw_ready
    global _hw_wall_ctrl, _hw_wall_ready, _hw_recv_ctrl, _hw_recv_ready
    if _hw_led_control is not None or _hw_wall_ctrl is not None or _hw_recv_ctrl is not None:
        return _hw_led_control
    try:
        import shelve as _s
        from led import led_control as _lc
        from led.led_control_c import LedControl
        db = _s.open(str(GAMES_ROOT / 'setting' / 'led_parameter'), flag='r')
        list_com_info = db.get('list_com_info', [])
        list_wall_com_info = db.get('list_wall_com_info', [])
        list_screen_com_info = db.get('list_screen_com_info', [])
        layout_type = int(db.get('led_layout_type', 0))
        no_use = db.get('floor_layout_coors_no_use', [])
        rows = int(float(db.get('value_high', _HW_DEFAULT_ROWS)))
        cols = int(float(db.get('value_width', _HW_DEFAULT_COLS)))
        db.close()

        _hw_layout_type = layout_type

        try:
            _lc.init_layout(layout_type, rows, cols, no_use)
            errors = _lc.init_com(list_com_info)
            if errors:
                logger.warning(f"HW emitters (COM9) open errors (non-fatal): {errors}")
            _hw_led_control = _lc
            _hw_ready = bool(list_com_info) and not errors
        except Exception as e:
            logger.warning(f"HW emitters (COM9) init failed: {e}")

        try:
            _wall = LedControl()
            wall_errors = _wall.init_com(list_wall_com_info)
            if wall_errors:
                logger.warning(f"HW wall buttons (COM7) open errors (non-fatal): {wall_errors}")
            _hw_wall_ctrl = _wall
            _hw_wall_ready = bool(list_wall_com_info) and not wall_errors
        except Exception as e:
            logger.warning(f"HW wall buttons (COM7) init failed: {e}")

        try:
            _recv = LedControl()
            recv_errors = _recv.init_com(list_screen_com_info)
            if recv_errors:
                logger.warning(f"HW receivers (COM6) open errors (non-fatal): {recv_errors}")
            _hw_recv_ctrl = _recv
            _hw_recv_ready = bool(list_screen_com_info) and not recv_errors
        except Exception as e:
            logger.warning(f"HW receivers (COM6) init failed: {e}")

        logger.info(
            f"Hardware init: emit(COM9)={_hw_ready} wall(COM7)={_hw_wall_ready} "
            f"recv(COM6)={_hw_recv_ready}, {rows}×{cols}, layout={layout_type}"
        )
    except Exception as e:
        logger.error(f"Hardware init failed: {e}")
    return _hw_led_control


def _hw_blank_floor(led_table=None):
    """Blank emitters (COM9) and wall lamps (COM7) on every stop path."""
    if not USE_SERIAL_HD:
        return
    if _hw_led_control is not None:
        try:
            rows = getattr(led_table, "led_row", None) or _HW_DEFAULT_ROWS
            cols = getattr(led_table, "led_col", None) or _HW_DEFAULT_COLS
            blank = [[0, 0, 0] for _ in range(cols)]
            with _hw_serial_lock:
                _hw_led_control.draw_screen_by_com(_hw_layout_type, [blank[:] for _ in range(rows)])
        except Exception as e:
            logger.warning(f"HW floor blank failed: {e}")
    if _hw_wall_ctrl is not None:
        try:
            with _hw_serial_lock:
                _hw_wall_ctrl.draw_wall_light_by_com([[0, 0, 0], [0, 0, 0]])
        except Exception as e:
            logger.warning(f"HW wall blank failed: {e}")

# Will import after config is set
# from game_play.Play import Play

# Laser scoreable wall colors (PLUS_ARR from model/setting.py).
# WALL_LIGHT groups matching these colors score on press.
_LASER_COLOR_ARR = [
    (254, 128, 0),   # orange  - P2 in DK 2P levels
    (0, 0, 254),     # blue    - P1 in DK 2P levels
    (254, 254, 0),   # yellow
    (0, 254, 254),   # cyan
    (254, 0, 254),   # magenta
    (254, 254, 254), # white
]
_LASER_HAZARD_COLORS = {(254, 0, 0), (240, 0, 0)}  # RED variants
WALL_TAP_SCORE = 10

# Settings from Laser led_parameter shelve.
_LED_PARAM  = str(GAMES_ROOT / "setting" / "led_parameter")
_DEBUG_PARAM = str(GAMES_ROOT / "setting" / "debug_parameter")

# Sensible fallbacks if the shelve can't be read.
_SETTINGS_DEFAULTS = {
    "game_time_sec": 300.0,    # game_time_sw (min) * 60
    "life_value": 20,          # life_value_sw  (starting HP)
    "leval_span": 0.9,         # leval_span_sw  (speed span)
    "tread_red_time": 0.01,    # debug: secs on red before life loss
    "life_value_count_time": 1.2,  # debug: min secs between life losses
    "laser_detect_time": 0.1,  # beam-broken duration before first floor hit
    "grid_rows": 6,            # value_high  — floor layout rows
    "grid_cols": 16,           # value_width — floor layout cols
    "wall_count": 14,          # len(wall_light_table)
    "wall_light_table": [      # from original led_parameter (6×16 venue)
        [0, 3], [0, 6], [0, 9], [0, 12], [0, 15],
        [2, 17], [5, 17], [7, 15], [7, 12], [7, 9], [7, 6], [7, 3],
        [6, 0], [3, 0],
    ],
    "wall_dots_per_side": 7,
    "scode_divide_person": True,   # game_scode_divide_person
    "scode_divide_time": True,     # game_scode_divide_time
    "player_num": 1,               # player_num_sw (overridden by 2P levels)
}

_settings_cache = None

# Venue has TWO physical walls (left + right). wall_light_layout_real [1,2] maps
# two hardware read channels to logical indices 0 (left bank) and 1 (right bank).
# Levels drive WALL_LIGHT start_member 0 or 1 — one blue target at a time.


def _floor_press_cell(er: int, ec: int, rows: int, cols: int):
    """Map editor wall_light_table coord → floor tile the player steps on to press."""
    fr = max(0, min(rows - 1, er))
    fc = max(0, min(cols - 1, ec))
    if ec <= 0:
        fc = 0
    elif ec >= cols:
        fc = cols - 1
    if er <= 0 and 0 < ec < cols - 1:
        fr = 0
    elif er >= rows and 0 < ec < cols - 1:
        fr = rows - 1
    return fr, fc


def build_wall_sim_slots(rows: int, cols: int, wall_light_table: list, dots_per_side: int = 7):
    """Evenly spaced wall dots for left/right corridor view (not every LED cell).

    wall_index in each slot is the *logical channel* (0=left bank, 1=right bank) —
    same indices used by WALL_LIGHT start_member and wall_display[]. Perimeter
    positions from wall_light_table only determine which floor row to step on.
    """
    rows_wanted = [
        max(0, min(rows - 1, int(round((rows - 1) * i / max(1, dots_per_side - 1)))))
        for i in range(dots_per_side)
    ]

    def _side_slots(channel_wi: int):
        return [{"wall_index": channel_wi, "row": row, "dot": i}
                for i, row in enumerate(rows_wanted)]

    return {
        "left": _side_slots(0),
        "right": _side_slots(1),
        "dots_per_side": dots_per_side,
    }


def load_real_settings() -> dict:
    """Read game settings from the decompiled project's shelve DBs once.
    Returns a parsed dict; falls back to defaults on any error."""
    global _settings_cache
    if _settings_cache is not None:
        return _settings_cache
    s = dict(_SETTINGS_DEFAULTS)
    # led_parameter: game length, HP, speed span
    try:
        db = _shelve.open(_LED_PARAM, flag="r")
        try:
            gt = db.get("game_time_sw")
            if gt is not None:
                s["game_time_sec"] = float(gt) * 60.0   # stored in minutes
            lv = db.get("life_value_sw")
            if lv is not None:
                s["life_value"] = int(float(lv))
            ls = db.get("leval_span_sw")
            if ls is not None:
                s["leval_span"] = float(ls)
            vh = db.get("value_high")
            if vh is not None:
                s["grid_rows"] = int(float(vh))
            vw = db.get("value_width")
            if vw is not None:
                s["grid_cols"] = int(float(vw))
            dp = db.get("game_scode_divide_person")
            if dp is not None:
                s["scode_divide_person"] = bool(dp)
            dt = db.get("game_scode_divide_time")
            if dt is not None:
                s["scode_divide_time"] = bool(dt)
            pn = db.get("player_num_sw")
            if pn is not None:
                s["player_num"] = int(float(pn))
            ldt = db.get("laser_detect_time")
            if ldt is not None:
                s["laser_detect_time"] = float(ldt)
            wlt = db.get("wall_light_table")
            if wlt is not None and len(wlt) > 0:
                s["wall_light_table"] = list(wlt)
                s["wall_count"] = len(wlt)
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"Could not read led_parameter: {e}; using defaults")
    # debug_parameter: red-penalty timing
    try:
        db = _shelve.open(_DEBUG_PARAM, flag="r")
        try:
            trt = db.get("tread_red_time")
            if trt is not None:
                s["tread_red_time"] = float(trt)
            lct = db.get("life_value_count_time")
            if lct is not None:
                s["life_value_count_time"] = float(lct)
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"Could not read debug_parameter: {e}; using defaults")
    _settings_cache = s
    logger.info(f"Loaded real settings: {s}")
    return s


# Level-progression tiers (dirs under source/, easy->hard). Laser is all
# .led (1-player) — no 2P tier exists, so the chain never crosses categories.
# Naming: intro (numeric ids) -> casual (A-prefix) -> level (B-prefix) ->
# advanced (C-prefix).
_TIERS_1P = ["----", "-", "--", "---"]
_TIERS_2P = []   # no 2P levels in Laser
# Corporate / Group: Extreme tier only under source_group/---/
_TIERS_GROUP = ["---"]
# Explicit order: note listed C02–C10; C10 missing → C01 Challenge is the 10th (last).
# Filename sort alone would put "C01 Challenge…" before C02.
_GROUP_CORPORATE_ORDER = [
    "C02.led",
    "C03.led",
    "C04.led",
    "C05.led",
    "C06.led",
    "C07.led",
    "C08.led",
    "C09.led",
    "C01 Challenge - 240 Pts.led",
]


def _level_sort_key(p):
    stem = os.path.basename(p).rsplit(".", 1)[0]
    return (0, int(stem)) if stem.isdigit() else (1, stem.lower())


def _build_group_level_sequence(start_level=None):
    """Corporate playlist from games/source_group/ (Group mode only).

    Prefer the locked Extreme order (_GROUP_CORPORATE_ORDER). Fall back to
    dash-folder scan if files were renamed.
    """
    import glob as _glob
    root = str(GAME_GROUP_LEVEL_DIR)
    ordered = []
    for name in _GROUP_CORPORATE_ORDER:
        path = os.path.join(root, "---", name)
        if os.path.isfile(path):
            ordered.append(path)
    if ordered:
        sl = str(start_level or "").strip()
        if sl.lower() in ("", "auto", "none"):
            return ordered
        for i, f in enumerate(ordered):
            stem = os.path.basename(f).rsplit(".", 1)[0]
            if stem == sl or stem.startswith(sl):
                return ordered[i:]
        return ordered

    chain = [
        (d, sorted(_glob.glob(os.path.join(root, d, "*.led")), key=_level_sort_key))
        for d in _TIERS_GROUP
    ]
    chain = [(d, files) for d, files in chain if files]
    if not chain:
        return []
    sl = str(start_level or "").strip()
    if sl.lower() in ("", "auto", "none"):
        sl = ""
    loc = None
    if sl:
        for ti, (_d, files) in enumerate(chain):
            for fi, f in enumerate(files):
                stem = os.path.basename(f).rsplit(".", 1)[0]
                if stem == sl or stem.startswith(sl):
                    loc = (ti, fi)
                    break
            if loc is not None:
                break
    if loc is None:
        loc = (0, 0)
    ti, fi = loc
    seq = list(chain[ti][1][fi:])
    for j in range(ti + 1, len(chain)):
        seq.extend(chain[j][1])
    return seq


def _build_level_sequence(start_level):
    """Ordered list of level FILE PATHS forming the marathon: remaining
    levels in the start tier, then all levels of every later tier. Laser
    has only the 1P chain (_TIERS_2P is empty), so this always resolves to
    _TIERS_1P; kept in the shared 1P/2P shape for consistency with the
    other games."""
    import glob as _glob
    src = str(GAMES_ROOT)
    sl = str(start_level or "").strip()

    def _sort_key(p):
        stem = os.path.basename(p).rsplit(".", 1)[0]
        return (0, int(stem)) if stem.isdigit() else (1, stem.lower())

    def _chain(dirs, ext):
        return [(d, sorted(_glob.glob(os.path.join(src, "source", d, f"*.{ext}")),
                           key=_sort_key)) for d in dirs]

    chain_1p = _chain(_TIERS_1P, "led")
    chain_2p = _chain(_TIERS_2P, "led")   # empty for Laser

    def _find(chain):
        for ti, (_d, files) in enumerate(chain):
            for fi, f in enumerate(files):
                stem = os.path.basename(f).rsplit(".", 1)[0]
                if stem == sl or stem.startswith(sl):
                    return ti, fi
        return None

    loc = _find(chain_1p)
    chain = chain_1p
    if loc is None:
        loc = _find(chain_2p)
        chain = chain_2p
    if loc is None:                       # unknown start -> begin at 1P tier 0
        chain, loc = chain_1p, (0, 0)
        if not chain or not chain[0][1]:
            return []

    ti, fi = loc
    seq = list(chain[ti][1][fi:])         # remaining levels in the start tier
    for j in range(ti + 1, len(chain)):   # then all later SAME-category tiers
        seq.extend(chain[j][1])
    return seq


def _load_level_file(path):
    """Load one .led/.ledb: unzip, find the main gameplay shelve (the one with
    play_order=False; audio/anim dirs have play_order=True), return
    (dict_group, game_obj) as in-memory objects. (None, None) on failure."""
    import zipfile, tempfile, shelve
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            with zipfile.ZipFile(path, 'r') as z:
                z.extractall(tmpdir)
            best_go = best_dg = None
            for root, _, files in os.walk(tmpdir):
                if not any(f.startswith("game_file") for f in files):
                    continue
                gf = os.path.join(root, "game_file")
                if not os.path.exists(gf + ".dat"):
                    continue
                try:
                    db = shelve.open(gf)
                    go = db.get("para_key_game")
                    dg = db.get("dict_group")
                    db.close()
                    if go is None or dg is None:
                        continue
                    if not getattr(go, "play_order", True):
                        return dg, go          # main gameplay — done
                    elif best_go is None:
                        best_go, best_dg = go, dg
                except Exception:
                    continue
            return best_dg, best_go
    except Exception as e:
        logger.warning(f"Could not load level file {path}: {e}")
        return None, None


class HeadlessLedTable:
    """In-memory LED table — replaces tkinter LedTable for headless API operation.
    Same interface as gui2/gui_led_table_editor.LedTable but zero GUI deps.
    Ported from LED-Hex SimulatorLedTable.
    """

    def __init__(self, wall_light_arr_len: int, led_row: int, led_col: int):
        self.led_row = led_row
        self.led_col = led_col
        self.row = led_row
        self.col = led_col
        # Floor LED colors: led_table[row][col] = [R, G, B]
        self.led_table = [[[0, 0, 0] for _ in range(led_col)] for _ in range(led_row)]
        # Tile press state: True = being stepped on
        self._state_table = [[False] * led_col for _ in range(led_row)]
        self.table_state = self._state_table   # shared ref
        self.state_table = self._state_table   # alias (game_manager callback uses this)
        self.state_2array = [[5] * led_col for _ in range(led_row)]
        self.g_wall_has_been_tread_arr2 = [[False] * led_col for _ in range(led_row)]
        # Wall arrays
        self._wall_light_arr = [[0, 0, 0] for _ in range(wall_light_arr_len)]
        self._wall_light_state_array = [False] * wall_light_arr_len
        self._wall_screen_arr = [0] * wall_light_arr_len
        self._wall_count = wall_light_arr_len
        # Per-tile scoring state
        self.red_table = [[False] * led_col for _ in range(led_row)]
        self.green_table = [[False] * led_col for _ in range(led_row)]
        self.safe_table = [[False] * led_col for _ in range(led_row)]
        self.deduct_table = [[False] * led_col for _ in range(led_row)]
        self.plus_table = [[None] * led_col for _ in range(led_row)]
        self.other_color_table = [[None] * led_col for _ in range(led_row)]
        self.blue_table = [[False] * led_col for _ in range(led_row)]
        self.tread_short_stay = [[None] * led_col for _ in range(led_row)]
        # Laser floor sensor debounce (vary_with_color_state)
        self.table_state_light = [[0.0] * led_col for _ in range(led_row)]
        self.table_state_dark = [[0.0] * led_col for _ in range(led_row)]
        self.table_state_last = [[False] * led_col for _ in range(led_row)]
        self.last_trigger_span = [[0.0] * led_col for _ in range(led_row)]
        self.goal_color = None
        self.goal_color2 = None
        self.safe_color = None
        self.canvas = None
        self.led_coors_click = [[0, 0], False]
        self.led_coors_click_wall = [[0, 0], False]

    # ── State table ────────────────────────────────────────────────────
    def get_state_table(self):
        return self._state_table

    def get_state_2array(self):
        return self.state_2array

    def get_g_wall_has_been_tread_arr2(self):
        return self.g_wall_has_been_tread_arr2

    # ── Wall accessors ─────────────────────────────────────────────────
    def get_wall_light_arr(self):
        return self._wall_light_arr

    def get_wall_light_state_array(self):
        return self._wall_light_state_array

    def get_wall_screen_arr(self):
        return self._wall_screen_arr

    # ── Color output (faithful to gui2/gui_led_table_editor) ─────────────
    def set_color_table_by_set_cell(self, start_member, color) -> None:
        """Tag floor cells by hazard/score type; colors applied in redraw."""
        from model.setting import Color
        c = _normalize_color_tuple(color)
        for cell in (start_member or []):
            try:
                i = int(round(cell[0]))
                j = int(round(cell[1]))
                if not (0 <= i < self.led_row and 0 <= j < self.led_col):
                    continue
                if c == Color.BLUE:
                    self.blue_table[i][j] = True
                elif c == Color.RED or c == Color.RED_BLINK or _rgb_is_red(c):
                    self.red_table[i][j] = True
                elif c == self.safe_color and self.safe_color is not None:
                    self.safe_table[i][j] = True
                elif c == Color.GREEN:
                    self.green_table[i][j] = True
                elif c == Color.DEDUCT_COLOR:
                    self.deduct_table[i][j] = True
                elif c in Color.PLUS_ARR:
                    self.plus_table[i][j] = c
                else:
                    self.other_color_table[i][j] = c
            except (IndexError, TypeError, ValueError):
                pass

    def set_table_color(self, table, color=None):
        c = list(color) if isinstance(color, (tuple, list)) else [0, 0, 0]
        for row in table:
            for i in range(len(row)):
                row[i] = c[:]

    def redraw_led_table_default(self, line=0, draw_canvas=True):
        """Apply tagged floor flags → led_table RGB (consumes flags each frame)."""
        from model.setting import Color
        for i in range(self.led_row):
            for j in range(self.led_col):
                if self.deduct_table[i][j]:
                    self.led_table[i][j] = list(Color.DEDUCT_COLOR)
                    self.deduct_table[i][j] = False
                if self.plus_table[i][j] is not None:
                    self.led_table[i][j] = list(self.plus_table[i][j])
                    self.plus_table[i][j] = None
                if self.other_color_table[i][j] is not None:
                    self.led_table[i][j] = list(self.other_color_table[i][j])
                    self.other_color_table[i][j] = None
                if self.safe_table[i][j]:
                    if self.safe_color is not None:
                        self.led_table[i][j] = list(self.safe_color)
                    self.safe_table[i][j] = False
                if self.red_table[i][j]:
                    self.led_table[i][j] = list(Color.RED)
                    self.red_table[i][j] = False
                if self.green_table[i][j]:
                    self.led_table[i][j] = list(Color.GREEN)
                    self.green_table[i][j] = False
                if self.blue_table[i][j]:
                    self.led_table[i][j] = list(Color.BLUE)
                    self.blue_table[i][j] = False

    def draw_led_color(self):
        pass

    def clear_led_table(self):
        for r in range(self.led_row):
            for c in range(self.led_col):
                self.led_table[r][c] = [0, 0, 0]
        for i in range(len(self._wall_light_arr)):
            self._wall_light_arr[i] = [0, 0, 0]
        self._wall_screen_arr = [0] * len(self._wall_light_arr)

    def press_wall(self, idx: int):
        if 0 <= idx < len(self._wall_light_state_array):
            self._wall_light_state_array[idx] = True

    def release_wall(self, idx: int):
        if 0 <= idx < len(self._wall_light_state_array):
            self._wall_light_state_array[idx] = False

    def screen_mouse_click_state_get(self):
        pass

    # ── Input (press/release from simulator) ──────────────────────────
    def press_cell(self, row: int, col: int):
        if 0 <= row < self.led_row and 0 <= col < self.led_col:
            self._state_table[row][col] = True

    def release_cell(self, row: int, col: int):
        if 0 <= row < self.led_row and 0 <= col < self.led_col:
            self._state_table[row][col] = False

    def clear_wall_light_state(self):
        for i in range(len(self._wall_light_state_array)):
            self._wall_light_state_array[i] = False

    # ── tkinter-compat stubs ───────────────────────────────────────────
    def pack(self, **kw): pass
    def grid(self, **kw): pass
    def update(self): pass
    def update_idletasks(self): pass
    def configure(self, **kw): pass
    def config(self, **kw): pass
    def destroy(self): pass
    def bind(self, *a, **kw): pass
    def unbind(self, *a, **kw): pass
    def after(self, ms, func=None, *args):
        import threading
        if func:
            t = threading.Timer(ms / 1000.0, func, args)
            t.daemon = True
            t.start()
    def after_cancel(self, *a): pass
    def winfo_width(self): return self.led_col * 44
    def winfo_height(self): return self.led_row * 38
    def get_canvas_table_size(self): return (self.led_row, self.led_col)


def _normalize_rings(cell):
    """Normalize a led_table cell to 3 ring colors [[r,g,b],[r,g,b],[r,g,b]]
    (outer, mid, inner). Cell is normally a 3-ring list, but tolerate a flat
    (r,g,b) (broadcast to all rings)."""
    try:
        if isinstance(cell, (list, tuple)) and len(cell) > 0:
            if isinstance(cell[0], (list, tuple)):
                rings = [[int(c[0]), int(c[1]), int(c[2])] for c in cell[:3]]
                while len(rings) < 3:
                    rings.append(rings[-1])
                return rings
            # flat (r,g,b) -> all rings same
            rgb = [int(cell[0]), int(cell[1]), int(cell[2])]
            return [rgb, rgb, rgb]
    except Exception:
        pass
    return [[0, 0, 0], [0, 0, 0], [0, 0, 0]]


def _cell_is_lit(cell):
    """True if any ring of the cell has a non-zero channel."""
    for ring in _normalize_rings(cell):
        if ring[0] or ring[1] or ring[2]:
            return True
    return False


def _cell_is_red(cell):
    """True if any ring is RED-dominant ((254,0,0)-like). Red = penalty tile."""
    for r, g, b in _normalize_rings(cell):
        if r >= 200 and g < 80 and b < 80:
            return True
    return False


def _group_main_color(color):
    """A group's representative color = its middle ring (ring[1]); ring[0] is a
    constant green marker. Returns an (r,g,b) tuple."""
    rings = _normalize_rings(color)
    return tuple(rings[1])


def _normalize_color_tuple(color):
    """Flat (r,g,b) for floor flag tagging."""
    if isinstance(color, (list, tuple)) and color:
        if isinstance(color[0], (list, tuple)):
            return tuple(int(x) for x in _group_main_color(color))
        if len(color) >= 3:
            return (int(color[0]), int(color[1]), int(color[2]))
    return (0, 0, 0)


def _rgb_is_deduct(rgb):
    """DEDUCT_COLOR (254,0,48): consume + penalty (distinct from plain red)."""
    return rgb[0] >= 200 and rgb[1] < 80 and 30 <= rgb[2] <= 90


def _rgb_is_red(rgb):
    """Plain RED (254,0,0): hazard, stays, repeats. Excludes DEDUCT (b~48)."""
    return rgb[0] >= 200 and rgb[1] < 80 and rgb[2] < 30


class HeadlessGameGUI:
    """Mock GUI parent for Play.running_new() - provides LED update callback"""

    def __init__(self, led_table):
        self.led_table = led_table

    def update_draw_led_table_idle_game(self, dict_group, total_pass=0, time_pass=0):
        """Called by Play.running_new() to update LED display"""
        try:
            if dict_group:
                for key, value in dict_group.items():
                    group = value
                    set_cell = group.start_member
                    start_time = group.start_time_sec
                    end_time = group.end_time_sec
                    if set_cell is not None and total_pass > start_time and total_pass < end_time:
                        from model.setting import Color
                        color = getattr(group, 'color', Color.GREEN)
                        if hasattr(self.led_table, 'set_color_table_by_set_cell'):
                            self.led_table.set_color_table_by_set_cell(set_cell, color)
        except Exception as e:
            logger.debug(f"LED update error: {e}")

    def clear_last_wall_display(self):
        """Clear display for next frame"""
        pass


class GameInstance:
    """Single running game instance"""

    def __init__(
        self,
        game_id: str,
        card_id: str,
        level: int,
        difficulty: str,
        mode: str = None,
    ):
        self.game_id = game_id
        self.card_id = card_id
        self.level = level
        self.difficulty = difficulty
        self.mode = (mode or "").strip().lower() or None  # "group" or None
        self.created_at = time.time()
        self.play = None  # Play object
        self.led_table = None  # LedTable instance (for press input)
        self.dict_group = None  # level groups (for consume-on-hit)
        self.flashes = {}  # wall index -> wall-clock start time (display-only hit flash)
        self.score = 0  # accumulated score from wall button presses
        self.scored_active = set()  # wall indices already scored this appearance
        # Per-frame wall classification (rebuilt each frame from WALL_LIGHT groups):
        self.goal_walls = set()    # wall indices matching scoreable colors
        self.goal2_walls = set()   # P2 wall indices (unused — Laser is 1P only)
        self.red_walls = set()     # in-time red hazard wall indices
        self.deduct_walls = set()  # DEDUCT_COLOR wall indices
        self.goal_color = None     # P1 goal color (from goal_led indicator)
        self.goal2_color = None    # P2 goal color (from goal2_led indicator)
        self.score2 = 0            # P2 score (0 in single-player)
        self.scored_active2 = set()# P2 scored cells this appearance
        self.multiplayer = False   # True when level has goal2_led
        self.zone = None          # (row_from,row_to,col_from,col_to) active area
        # 2P respawn: consumed goal tiles reappear after delay (only for .ledb multiplayer)
        self.pending_respawn = []  # [[group, (i,j), reappear_wall_time], ...]
        self.respawn_delay = 8.0   # seconds; tunable
        # Same-color 2P (e.g. DK03 cyan==cyan): alternate P1→P2→P1→P2 per cell.
        # Cells in this set score P2 next; others score P1.
        self.p2_next_cells = set()
        self.input_lock = threading.Lock()  # guards state_table writes
        self.running = False

        # Real settings (game length + HP). Loaded from led_parameter.
        _s = load_real_settings()
        self.game_time_sec = _s["game_time_sec"]   # session limit (300s)

        # Runtime override pushed from the central RFID server (Settings page):
        # default_difficulty/session_minutes. Applied after the shelve-derived
        # defaults above but only takes effect for difficulty when the caller
        # didn't already pass one explicitly (StartGameRequest.difficulty is
        # required today, so this is a no-op until a caller omits it).
        _override_path = GAMES_ROOT / "setting" / "runtime_overrides.json"
        if _override_path.exists():
            try:
                with open(_override_path) as _f:
                    _overrides = json.load(_f)
                if _overrides.get("session_minutes"):
                    self.game_time_sec = float(_overrides["session_minutes"]) * 60.0
                if _overrides.get("default_difficulty") and not getattr(self, "difficulty", None):
                    self.difficulty = _overrides["default_difficulty"]
            except Exception as _e:
                logger.warning(f"Could not read runtime overrides: {_e}")

        self.board_time_sec = 1e9                   # board length (max group end); set on load
        self.result = None                          # 0 lose / 1 complete / 2 timeout
        self.max_life = _s["life_value"]           # 20 HP
        self.life = self.max_life
        # Final-score normalization (game_scode_rule): divide raw score by
        # player count and/or game-time (minutes). Applied at session end only;
        # live `score` stays raw for display.
        self._scode_divide_person = _s.get("scode_divide_person", True)
        self._scode_divide_time = _s.get("scode_divide_time", True)
        # Default 1 player; _setup_level bumps to 2 for actual 2P (DK) levels.
        # (player_num_sw is the machine's max-player config, not per-game.)
        self._player_num = 1
        self.last_life_loss_time = 0.0             # for life_value_count_time gate
        self._life_count_time = _s["life_value_count_time"]
        self._laser_detect_time = float(_s.get("laser_detect_time", 0.1))
        self._life_hit_gap = 0.05                  # secs between floor hits while still blocked

        # ── SESSION (5-min marathon) state ──────────────────────────────
        # Score + lives persist across levels; session ends on life<=0 or
        # timer<=0. Player picks a starting level; we marathon to series end.
        self.session_start = None      # wall-clock when first level begins
        self.level_sequence = []       # ordered list of level FILE PATHS
        self.current_level_id = None   # e.g. "A005" (for frontend display)
        self.levels_cleared = 0        # how many levels finished this session
        self._session_over = False     # True -> stop the session loop
        self._level_cleared = False    # True -> advance to next level
        self._restart_level = False    # True -> replay same level (life=0, time left)
        self._end_reason = None        # why the session loop exited (for result honesty)
        self.accepting_input = False

        # Test overrides (pytest effects session loop)
        if os.environ.get("LASER_TEST_LIFE_VALUE"):
            _test_life = int(os.environ["LASER_TEST_LIFE_VALUE"])
            self.max_life = _test_life
            self.life = _test_life
        if os.environ.get("LASER_TEST_GAME_TIME_SEC"):
            self.game_time_sec = float(os.environ["LASER_TEST_GAME_TIME_SEC"])
        if os.environ.get("LASER_TEST_LIFE_COUNT_TIME"):
            self._life_count_time = float(os.environ["LASER_TEST_LIFE_COUNT_TIME"])

        self.current_state = {
            "score": 0,
            "time_elapsed": 0.0,
            "time_left": self.game_time_sec,
            "life": self.max_life,
            "max_life": self.max_life,
            "display_lives": 5,   # always 5 hearts at full HP, whatever max_life is
            "display_max": 5,
            "score2": 0,
            "multiplayer": False,
            "player_pos": None,
            "led_display": [],
            "wall_display": [],
            "wall_count": 14,
            "wall_slots": {"left": [], "right": []},
            "dots_per_side": 7,
            "floor_display": [],
            "game_over": False,
            "game_over_reason": "",
            "result": None,
            "current_level": None,
            "levels_cleared": 0,
            "started_at": "",
            "phase": "idle",
            "accepting_input": False,
            "countdown_label": None,
            "backend_audio_active": False,
        }
        self.thread = None

    def compute_final_score(self, raw_score):
        """Leaderboard score normalization (faithful to game_scode_rule):
          final = raw / player_count (if divide_person) / minutes (if divide_time)
        game_time is in MINUTES (game_time_sw). Live display uses raw score;
        this is only for the saved/leaderboard result."""
        scode = float(raw_score)
        if self._scode_divide_person and self._player_num:
            scode /= self._player_num
        if self._scode_divide_time:
            minutes = self.game_time_sec / 60.0
            if minutes > 0:
                scode /= minutes
        return round(scode, 2)

    def reset_for_level(self):
        """Clear PER-LEVEL board state before loading the next level.
        Score, score2, life, session timer all PERSIST (not reset)."""
        self.flashes = {}
        self.scored_active = set()
        self.scored_active2 = set()
        self.pending_respawn = []
        self.p2_next_cells = set()
        self.goal_walls = set()
        self.goal2_walls = set()
        self.red_walls = set()
        self.deduct_walls = set()
        self.last_life_loss_time = 0.0
        self._level_cleared = False
        self._restart_level = False
        self.player_floor_pos = None  # (row, col) — simulates standing on floor
        if self.led_table:
            self.led_table.clear_wall_light_state()

    def is_expired(self) -> bool:
        """Check if game timed out"""
        elapsed = time.time() - self.created_at
        return elapsed > GAME_TIMEOUT_SECONDS

    def get_state(self) -> dict:
        """Get current game state"""
        return self.current_state

    def update_state(self, **kwargs):
        """Update game state"""
        self.current_state.update(kwargs)

    def _floor_press_for_wall(self, wi: int):
        rows = self.led_table.led_row if self.led_table else 6
        cols = self.led_table.led_col if self.led_table else 16
        if wi in (0, 1):
            mid = rows // 2
            return (mid, 0) if wi == 0 else (mid, cols - 1)
        if wi < len(self._wall_light_table):
            er, ec = self._wall_light_table[wi]
            return _floor_press_cell(int(er), int(ec), rows, cols)
        return None

    def vary_with_color_state(self, dict_group, time_pass: float, total_pass: float):
        """Laser floor life/score from tread + red_table/blue_table flags.
        Ported from gui_editor_game.vary_with_color_state (hardware table_state)."""
        if not self.accepting_input or self.current_state.get("phase") != "playing":
            return
        lt = self.led_table
        if lt is None:
            return
        from model.setting import Color
        rows, cols = lt.led_row, lt.led_col
        table_state = lt.get_state_table()
        red_tb = lt.red_table
        blue_tb = lt.blue_table
        green_tb = lt.green_table
        tsl = lt.table_state_light
        tsd = lt.table_state_dark
        lts = lt.last_trigger_span
        laser_tm = self._laser_detect_time
        hit_gap = self._life_hit_gap

        for i in range(rows):
            for j in range(cols):
                tread = bool(table_state[i][j])
                if red_tb[i][j]:
                    if not green_tb[i][j]:
                        if tread:
                            tsd[i][j] += time_pass
                            if tsd[i][j] > 0.01 and (
                                tsl[i][j] > hit_gap or tsd[i][j] >= laser_tm
                            ):
                                tsl[i][j] = 0.0
                                if total_pass - lts[i][j] >= hit_gap:
                                    lts[i][j] = total_pass
                                    self.life = max(0, self.life - 1)
                                    self.score -= 1
                                    logger.info(
                                        f"LASER_HIT cell=({i},{j}) tsd={tsd[i][j]:.3f}s "
                                        f"detect_need={laser_tm:.3f}s gap={hit_gap:.1f}s "
                                        f"score={self.score} life={self.life} "
                                        f"total_pass={total_pass:.2f}"
                                    )
                        else:
                            tsd[i][j] = 0.0
                    else:
                        if tread:
                            tsl[i][j] += time_pass
                        if tsl[i][j] > hit_gap:
                            tsl[i][j] = hit_gap
                        tsd[i][j] = 0.0
                elif blue_tb[i][j]:
                    if not green_tb[i][j] and not red_tb[i][j]:
                        if tread:
                            tsd[i][j] += time_pass
                            if tsd[i][j] > 0.01 and (
                                tsl[i][j] > hit_gap or tsd[i][j] >= laser_tm
                            ):
                                tsl[i][j] = 0.0
                                if total_pass - lts[i][j] >= hit_gap:
                                    lts[i][j] = total_pass
                                    self.score += 1
                        else:
                            tsd[i][j] = 0.0
                    else:
                        if tread:
                            tsl[i][j] += time_pass
                        if tsl[i][j] > hit_gap:
                            tsl[i][j] = hit_gap
                        tsd[i][j] = 0.0
                else:
                    tsl[i][j] = 0.0
                    tsd[i][j] = 0.0

    def score_wall_light_groups(self, dict_group, total_pass: float):
        """Wall button scoring — calculation_one_second_wall_light_dict_group."""
        if not self.accepting_input or self.current_state.get("phase") != "playing":
            return
        lt = self.led_table
        if lt is None or not dict_group:
            return
        from model.setting import Setting, Color
        arr_state = lt.get_wall_light_state_array()
        scoreset = set(_LASER_COLOR_ARR)
        for g in dict_group.values():
            if getattr(g, "type", None) != Setting.WALL_LIGHT:
                continue
            mc = _normalize_color_tuple(g.color)
            if mc not in scoreset:
                continue
            st, et = g.start_time_sec, g.end_time_sec
            if not (st < total_pass < et):
                continue
            sm = getattr(g, "start_member", None)
            if not sm:
                continue
            for cell in list(sm):
                wi = int(cell)
                if wi < 0 or wi >= len(arr_state):
                    continue
                if arr_state[wi]:
                    self.score += WALL_TAP_SCORE
                    self._consume_wall(wi, total_pass)

    def try_score_wall(self, wi: int, total_pass: float):
        """Type-aware scoring for a press on wall button index wi."""
        if not self.accepting_input or self.current_state.get("phase") != "playing":
            return
        # Red hazard: penalty + HP loss (gated). Not edge-limited by
        # scored_active (standing on red keeps hurting, rate-limited by time).
        if wi in self.red_walls:
            now = time.time()
            if now - self.last_life_loss_time >= self._life_count_time:
                self.score -= 1
                self.life = max(0, self.life - 1)
                self.last_life_loss_time = now
            return
        # DEDUCT tile: -1 SCORE only (NO life loss), then consume.
        # Faithful to original gui_editor_game.py (DEDUCT_COLOR block):
        # scode_value -= ONE_SCODE_VALUE, no life_value change.
        if wi in self.deduct_walls and wi not in self.scored_active:
            self.scored_active.add(wi)
            self.score -= 1
            self._consume_wall(wi, total_pass)
            return
        if wi in self.goal_walls and wi not in self.scored_active:
            self.scored_active.add(wi)
            self.score += WALL_TAP_SCORE
            self._consume_wall(wi, total_pass)
            return

    def _consume_wall(self, wi: int, total_pass: float):
        """Remove wall index from the WALL_LIGHT group whose time window is
        CURRENTLY ACTIVE, so the button blanks. Must filter by time window —
        the same wall index is commonly reused across multiple sequential
        groups (e.g. wall 0 lit at t=0-60, then again at t=195-330), and
        without this filter, consuming one occurrence wipes every future
        occurrence too (they all share the same `wi`), causing
        remaining_scoreable to hit 0 and the level to end after only a
        fraction of its real target count."""
        if self.dict_group:
            for g in self.dict_group.values():
                if getattr(g, "type", None) != "wall_light":
                    continue
                st = getattr(g, "start_time_sec", 0)
                et = getattr(g, "end_time_sec", 0)
                if not (st < total_pass < et):
                    continue
                sm = getattr(g, "start_member", None)
                if not sm:
                    continue
                try:
                    if isinstance(sm, set):
                        sm.discard(wi)
                    elif wi in sm:
                        sm.remove(wi)
                except Exception:
                    pass
        self.flashes[wi] = time.time()

    def process_respawns(self):
        """Re-add consumed 2P goal tiles after respawn_delay. Per-frame."""
        if not self.pending_respawn:
            return
        now = time.time(); still = []
        for entry in self.pending_respawn:
            g, cell, t = entry
            if now >= t:
                sm = getattr(g, "start_member", None)
                try:
                    if isinstance(sm, set): sm.add(cell)
                    elif sm is not None and cell not in sm: sm.append(cell)
                except Exception:
                    pass
            else:
                still.append(entry)
        self.pending_respawn = still

    def apply_input(self, wall_index: int, action: str):
        """Direct wall index (hardware / debug)."""
        if not self.accepting_input or self.current_state.get("phase") != "playing":
            return False
        if self.led_table is None:
            return False
        wi = int(wall_index)
        if wi < 0 or wi >= len(self.led_table.get_wall_light_state_array()):
            return False
        with self.input_lock:
            if action == "press":
                self.led_table.press_wall(wi)
            elif action == "release":
                self.led_table.release_wall(wi)
        return True

    def apply_floor_input(self, row: int, col: int, action: str):
        """Simulator floor step. When COM6/COM7 live, do not wipe HW-derived state."""
        if not self.accepting_input or self.current_state.get("phase") != "playing":
            return False
        if self.led_table is None:
            return False
        r, c = int(row), int(col)
        rows, cols = self.led_table.led_row, self.led_table.led_col
        if r < 0 or r >= rows or c < 0 or c >= cols:
            return False
        hw_live = USE_SERIAL_HD and (_hw_wall_ready or _hw_recv_ready)
        with self.input_lock:
            st = self.led_table.get_state_table()
            if action == "press":
                if not hw_live:
                    for ri in range(rows):
                        for ci in range(cols):
                            st[ri][ci] = False
                self.led_table.press_cell(r, c)
                self.player_floor_pos = (r, c)
                if not hw_live:
                    self.led_table.clear_wall_light_state()
                    for wi in (self.goal_walls | self.red_walls | self.deduct_walls):
                        press = self._floor_press_for_wall(wi)
                        if press == (r, c):
                            self.led_table.press_wall(wi)
            elif action == "release":
                self.led_table.release_cell(r, c)
                if self.player_floor_pos == (r, c):
                    self.player_floor_pos = None
                if not hw_live:
                    self.led_table.clear_wall_light_state()
        return True


class GameManager:
    """Manages all running game instances"""

    def __init__(self):
        self.games: Dict[str, GameInstance] = {}
        self.lock = threading.Lock()
        self._create_lock = threading.Lock()
        self.zombie_threads = []
        logger.info("GameManager initialized")

    def clear_all(self):
        """Stop and remove all existing games. Joins threads (3s timeout) before clearing."""
        with self.lock:
            for gid, g in list(self.games.items()):
                g.running = False
            threads = [(gid, g.thread) for gid, g in self.games.items() if getattr(g, "thread", None)]
            led_tables = [g.led_table for g in self.games.values() if getattr(g, "led_table", None) is not None]
            self.games.clear()
        for gid, t in threads:
            t.join(timeout=3.0)
            if t.is_alive():
                logger.warning(f"Thread {gid} didn't stop in 3s — zombie")
                self.zombie_threads.append(gid)
        # Blank the physical floor so a stale frame doesn't linger from
        # whichever game was just cleared out (kiosk model: clear_all()
        # runs at the start of every new game via create_game()).
        for lt in led_tables:
            _hw_blank_floor(lt)
        logger.info("Cleared all existing games")

    def create_game(
        self, card_id: str, level: int, difficulty: str, mode: str = None
    ) -> str:
        """Create new game instance. Clears any prior games first (kiosk model)."""
        self.clear_all()
        with self.lock:
            game_id = str(uuid.uuid4())[:8]
            if (mode or "").strip().lower() == "group":
                mode = "group"
            game = GameInstance(game_id, card_id, level, difficulty, mode=mode)

            # Eagerly set multiplayer from file extension BEFORE the load
            # thread starts, so _consume_cell respawns correctly even if
            # a press arrives before the shelve is fully loaded (~7s).
            # Group / corporate mode is always 1P.
            if game.mode == "group":
                game.multiplayer = False
                logger.info(
                    f"Game created: {game_id} mode=group "
                    f"(card={card_id}, level={level})"
                )
            else:
                _clone = str(GAMES_ROOT)
                _ledb = os.path.join(_clone, "source", "---", f"{level}.ledb")
                if os.path.exists(_ledb):
                    game.multiplayer = True
                    logger.info(
                        f"Game created: {game_id} multiplayer=True "
                        f"(card={card_id}, level={level})"
                    )
                else:
                    logger.info(
                        f"Game created: {game_id} (card={card_id}, level={level})"
                    )

            self.games[game_id] = game
            return game_id

    def get_game(self, game_id: str) -> Optional[GameInstance]:
        """Get game by ID"""
        with self.lock:
            return self.games.get(game_id)

    def start_game(self, game_id: str):
        """Start game loop in background thread"""
        game = self.get_game(game_id)
        if not game:
            raise ValueError(f"Game not found: {game_id}")

        def _run_game():
            try:
                # Double-check: reinstall mocks in this thread
                if not USE_SERIAL_HD:
                    if 'serial' not in sys.modules:
                        sys.modules['serial'] = MagicMock()
                    if 'led' not in sys.modules:
                        sys.modules['led'] = MagicMock()
                    if 'led.led_control' not in sys.modules:
                        sys.modules['led.led_control'] = MagicMock()
                else:
                    _hw_init()

                logger.info(f"Starting game loop: {game_id}")

                # Import game modules (with fallback to mock loop on import error)
                Play = None
                LedTable = None
                Setting = None
                try:
                    logger.info(f"Importing game modules for {game_id}")
                    import shelve
                    import os
                    from game_play.Play import Play
                    from game_play.game_running import LedTable
                    from model.setting import Setting
                    logger.info(f"✓ Game modules imported")
                except Exception as import_err:
                    logger.warning(f"Game module import failed, using mock loop: {import_err}")
                    import traceback
                    logger.warning(f"Import traceback: {traceback.format_exc()}")
                    Play = None
                    LedTable = None
                    Setting = None
                    # If imports failed, force dict_group to None to skip to mock loop
                    dict_group = None

                # Initialize game components — always use HeadlessLedTable
                # (never the mocked gui2 LedTable — that's MagicMock, comparisons fail)
                _s = load_real_settings()
                _rows = _s.get("grid_rows", 6)
                _cols = _s.get("grid_cols", 16)
                _wall_n = _s.get("wall_count", 14)
                led_table = HeadlessLedTable(wall_light_arr_len=_wall_n, led_row=_rows, led_col=_cols)
                game._wall_light_table = list(
                    _s.get("wall_light_table") or _SETTINGS_DEFAULTS["wall_light_table"]
                )
                game._wall_sim_slots = build_wall_sim_slots(
                    _rows, _cols, game._wall_light_table,
                    int(_s.get("wall_dots_per_side", 7)),
                )
                logger.info(f"HeadlessLedTable ready: floor {_rows}x{_cols}, wall buttons={_wall_n}")

                # Create mock settings object with required attributes
                # Climb's Play.__init__ expects setting.leval_span.get(), setting.blue_hide_max_time.get(), etc.
                class MockSetting:
                    def __init__(self):
                        class MockAttr:
                            def get(self):
                                return 0.9  # leval_span default
                        self.leval_span = MockAttr()
                        self.blue_hide_max_time = MockAttr()
                        self.blue_hide_max_time.get = lambda: 5.0
                        self.corner_line_start = MockAttr()
                        self.corner_line_start.get = lambda: 0

                mock_setting = MockSetting()

                # Create dummy callback (Play expects partial_fun_cb for UI updates)
                def dummy_callback(*args, **kwargs):
                    pass

                # game_level: numeric difficulty (1=easy, 2=normal, 3=hard), not level ID
                difficulty_map = {"easy": 1, "normal": 2, "hard": 3}
                game_level_num = difficulty_map.get(game.difficulty, 2)  # default to normal

                play = None
                try:
                    logger.debug(f"Creating Play instance for game {game_id}")
                    play = Play(led_table, mock_setting, dummy_callback, game_level=game_level_num)
                    # Sweep speed scale (cells/sec = (1/group.speed) * game_level_speed).
                    # Lower = slower sweep. Tune per difficulty to match real game pace.
                    difficulty_speed = {"easy": 0.25, "normal": 0.4, "hard": 0.6}
                    play.game_level_speed = difficulty_speed.get(game.difficulty, 0.4)
                except Exception as e:
                    logger.warning(f"Play creation failed, using mock loop: {e}")
                    play = None

                # ── SESSION SETUP ────────────────────────────────────────────
                # Build the level marathon sequence from the chosen start level
                # to the end of its series (A001..A025 / B01..B31 / DK01..DK10).
                game.play = play
                game.led_table = led_table          # expose for press input
                game.session_start = time.time()
                game._end_reason = None
                import datetime as _dt
                game.update_state(started_at=_dt.datetime.now().isoformat(timespec="seconds"))
                _test_levels = os.environ.get("LASER_TEST_LEVELS")
                if _test_levels:
                    game.level_sequence = [p.strip() for p in _test_levels.split(",") if p.strip()]
                elif getattr(game, "mode", None) == "group":
                    game.level_sequence = _build_group_level_sequence(game.level)
                    if game.level_sequence:
                        game.level = os.path.basename(
                            game.level_sequence[0]
                        ).rsplit(".", 1)[0]
                    game.multiplayer = False
                else:
                    game.level_sequence = _build_level_sequence(game.level)
                logger.info(
                    f"Session: {len(game.level_sequence)} levels from "
                    f"'{game.level}' mode={getattr(game, 'mode', None) or 'single'} "
                    f"(5-min marathon)"
                )

                game_start_time = game.session_start  # legacy alias for mock loop

                BLACK3 = [(0, 0, 0), (0, 0, 0), (0, 0, 0)]

                def _ensure_anim(g):
                    """Pickled groups lack breath state; init it lazily so
                    group.breath() works (shimmer effect)."""
                    if not isinstance(getattr(g, "breath_color_float", None), list) \
                            or not (g.breath_color_float and isinstance(g.breath_color_float[0], (list, tuple))):
                        col = g.color if (isinstance(g.color, (list, tuple)) and g.color
                                          and isinstance(g.color[0], (list, tuple))) else BLACK3
                        g.breath_color = [list(c) for c in col]
                        g.breath_color_float = [list(c) for c in col]
                        g.breath_switch = [True, True, True]
                    if not hasattr(g, "trigger_span_tm"):
                        g.trigger_span_tm = 0

                def _setup_level(dg, go):
                    """Configure game state for a freshly-loaded level. Score,
                    score2, life, session timer all PERSIST (set elsewhere)."""
                    game.dict_group = dg
                    # Per-level board time = max group end_time.
                    try:
                        game.board_time_sec = max(
                            (getattr(g, "end_time_sec", 0) for g in dg.values()),
                            default=1e9)
                    except Exception:
                        game.board_time_sec = 1e9
                    # Play zone (guards input).
                    if go is not None:
                        try:
                            game.zone = (int(getattr(go, "zone_row_from", 0)),
                                         int(getattr(go, "zone_row_to", 16)),
                                         int(getattr(go, "zone_col_from", 0)),
                                         int(getattr(go, "zone_col_to", 26)))
                        except Exception:
                            game.zone = None
                    # Multiplayer: 2P levels have BOTH blue(P1) and orange(P2)
                    # scoreable groups. Upgrade only (never override to False).
                    _P1 = (0, 0, 254); _P2 = (254, 128, 0)
                    has_p1 = has_p2 = False
                    for g in dg.values():
                        mc = _group_main_color(g.color)
                        if mc == _P1: has_p1 = True
                        elif mc == _P2: has_p2 = True
                    if has_p1 and has_p2:
                        game.multiplayer = True
                        game._player_num = 2   # 2P: divide score by 2 players
                    # Init breath/anim state for all groups.
                    for g in dg.values():
                        try:
                            _ensure_anim(g)
                        except Exception:
                            pass

                # Per-frame callback fired by Play.update() inside Play.running().
                # By this point Play has: moved groups (deal_all_direction by
                # speed), advanced total_pass, cleared+redrawn led_table for the
                # current frame. We score presses and publish the frame.
                # Returning False makes Play.running() stop (timeout / Stop btn).
                frame_counter = {"n": 0}

                def _frame_callback(play_self, dgroup, time_pass, total_pass):
                    # total_pass is PER-LEVEL (reset each level). Session timing
                    # is wall-clock from game.session_start.
                    try:
                        session_elapsed = time.time() - game.session_start

                        # ── SESSION-END conditions (stop the whole marathon) ──
                        #   life<=0          -> result 0 (out of lives)
                        #   session timer up -> result 2 (5-min timeout)
                        if game.life <= 0:
                            time_left = game.game_time_sec - session_elapsed
                            if time_left > 10.0:
                                # Lives gone but time remains: restart same level,
                                # keep score. Session loop refills HP and replays.
                                game._restart_level = True
                                return False
                            game._session_over = True
                            game.update_state(game_over_reason="out_of_life", result=0)
                            return False
                        if (not game.running) or session_elapsed > game.game_time_sec:
                            game._session_over = True
                            game.update_state(game_over_reason="timeout", result=2)
                            return False
                        # ── LEVEL-END by TIME (advance to next level) ──
                        # board_time_sec = max group end_time. For short levels
                        # this fires; long (600s) levels advance by all-cleared.
                        if total_pass > game.board_time_sec:
                            game._level_cleared = True
                            return False

                        wall_state = led_table.get_wall_light_state_array()
                        wall_n = len(wall_state)

                        # ── HARDWARE READ (COM7 buttons + COM6 breaks) ──────
                        if USE_SERIAL_HD and game.running:
                            with game.input_lock, _hw_serial_lock:
                                if _hw_wall_ready and _hw_wall_ctrl is not None:
                                    try:
                                        _btn = [False, False]
                                        _hw_wall_ctrl.update_wall_light_state_by_com(_btn)
                                        if wall_n >= 2:
                                            wall_state[0] = bool(_btn[0])
                                            wall_state[1] = bool(_btn[1])
                                    except Exception as _hw_err:
                                        logger.warning(f"HW wall read: {_hw_err}")
                                if _hw_recv_ready and _hw_recv_ctrl is not None \
                                        and getattr(game, "_hw_draw_count", 0) > 0:
                                    try:
                                        _rrows, _rcols = led_table.led_row, led_table.led_col
                                        _raw = [[False] * _rcols for _ in range(_rrows)]
                                        _hw_recv_ctrl.update_screen_state_by_com(
                                            _hw_layout_type, _raw, _raw)
                                        _st = led_table.get_state_table()
                                        for _ri in range(_rrows):
                                            for _ci in range(_rcols):
                                                _bit = _raw[_ri][_ci]
                                                _st[_ri][_ci] = (not _bit) if \
                                                    _HW_RAW_TRUE_MEANS_INTACT else _bit
                                    except Exception as _hw_err:
                                        logger.warning(f"HW recv read: {_hw_err}")

                        # ── LASER WALL CLASSIFICATION ───────────────────────
                        goal_walls = set()
                        red_walls = set()
                        deduct_walls = set()
                        green_walls = set()
                        _GREEN = (0, 254, 0)
                        wall_win = {}
                        _scoreset = set(_LASER_COLOR_ARR)

                        def _wall_color(g):
                            c = g.color
                            if isinstance(c, (list, tuple)) and c and isinstance(c[0], (list, tuple)):
                                return _group_main_color(c)
                            if isinstance(c, (list, tuple)) and len(c) >= 3:
                                return (int(c[0]), int(c[1]), int(c[2]))
                            return (0, 0, 0)

                        for g in dgroup.values():
                            if getattr(g, "type", None) != Setting.WALL_LIGHT:
                                continue
                            sm = getattr(g, "start_member", None)
                            if not sm:
                                continue
                            if not (total_pass > g.start_time_sec and total_pass < g.end_time_sec):
                                continue
                            mc = _wall_color(g)
                            if mc == _GREEN:
                                rank, cat = 3, "green"
                            elif _rgb_is_deduct(mc):
                                rank, cat = 2, "deduct"
                            elif mc in _LASER_HAZARD_COLORS:
                                rank, cat = 2, "red"
                            elif mc in _scoreset:
                                rank, cat = 1, "goal"
                            else:
                                rank, cat = 0, "decor"
                            for idx in sm:
                                wi = int(idx)
                                if wi < 0 or wi >= wall_n:
                                    continue
                                prev = wall_win.get(wi)
                                if prev is None or rank > prev[0]:
                                    wall_win[wi] = (rank, cat, mc)

                        for wi, (rank, cat, mc) in wall_win.items():
                            if cat == "green":
                                green_walls.add(wi)
                            elif cat == "deduct":
                                deduct_walls.add(wi)
                            elif cat == "red":
                                red_walls.add(wi)
                            elif cat == "goal":
                                goal_walls.add(wi)

                        game.goal_walls = goal_walls
                        game.red_walls = red_walls
                        game.deduct_walls = deduct_walls

                        remaining_scoreable = 0
                        for g in dgroup.values():
                            if getattr(g, "type", None) != Setting.WALL_LIGHT:
                                continue
                            mc = _wall_color(g)
                            if mc in _scoreset:
                                sm = getattr(g, "start_member", None)
                                if sm:
                                    remaining_scoreable += len(sm)

                        if total_pass > 1.5 and remaining_scoreable == 0:
                            logger.info(f"Level cleared (all wall buttons): "
                                        f"score={game.score}, life={game.life}")
                            game._level_cleared = True
                            return False

                        if total_pass > 1.5 and remaining_scoreable > 0 and not goal_walls:
                            next_start = None
                            for g in dgroup.values():
                                if getattr(g, "type", None) != Setting.WALL_LIGHT:
                                    continue
                                mc = _wall_color(g)
                                if mc not in _scoreset:
                                    continue
                                sm = getattr(g, "start_member", None)
                                if not sm:
                                    continue
                                st = g.start_time_sec
                                if st > total_pass and (next_start is None or st < next_start):
                                    next_start = st
                            if next_start is not None:
                                play_self.total_pass = next_start
                                game.last_life_loss_time = 0.0

                        floor_rows, floor_cols = led_table.led_row, led_table.led_col
                        # Floor rules use red_table/blue_table flags (before redraw).
                        prev_score = game.score
                        prev_life = game.life
                        game.vary_with_color_state(dgroup, time_pass, total_pass)
                        led_table.redraw_led_table_default(draw_canvas=False)
                        with game.input_lock:
                            game.score_wall_light_groups(dgroup, total_pass)
                            for wi in range(wall_n):
                                if wall_state[wi] and wi in (red_walls | deduct_walls):
                                    game.try_score_wall(wi, total_pass)
                        if audio.active:
                            if game.score > prev_score:
                                audio.play_score_positive()
                            elif game.score < prev_score or game.life < prev_life:
                                audio.play_score_negative()

                        import math as _math
                        pulse = 0.75 + 0.25 * (0.5 + 0.5 * _math.sin(total_pass * _math.pi * 2))
                        wall_arr = led_table.get_wall_light_arr()
                        floor_display = []
                        for ri in range(floor_rows):
                            for ci in range(floor_cols):
                                fc = led_table.led_table[ri][ci]
                                if isinstance(fc, (list, tuple)) and fc and isinstance(fc[0], (list, tuple)):
                                    floor_display.append(list(_group_main_color(fc)))
                                elif isinstance(fc, (list, tuple)) and len(fc) >= 3:
                                    floor_display.append([int(fc[0]), int(fc[1]), int(fc[2])])
                                else:
                                    floor_display.append([0, 0, 0])

                        safe_press_tiles = set()
                        for wi in goal_walls:
                            pt = game._floor_press_for_wall(wi)
                            if pt:
                                safe_press_tiles.add(pt)
                        for fri, fci in safe_press_tiles:
                            idx = fri * floor_cols + fci
                            if 0 <= idx < len(floor_display):
                                floor_display[idx] = [0, 0, 0]

                        wall_display = []
                        for wi in range(wall_n):
                            c = wall_arr[wi]
                            if isinstance(c, (list, tuple)) and c and isinstance(c[0], (list, tuple)):
                                rgb = list(_group_main_color(c))
                            elif isinstance(c, (list, tuple)) and len(c) >= 3:
                                rgb = [int(c[0]), int(c[1]), int(c[2])]
                            else:
                                rgb = [0, 0, 0]
                            if wi in wall_win and wall_win[wi][1] == "goal":
                                mc = wall_win[wi][2]
                                rgb = [min(255, int(ch * pulse)) for ch in mc]
                            wall_display.append(rgb)

                        now = time.time()
                        for wi, t0 in list(game.flashes.items()):
                            el = now - t0
                            if el > 0.4:
                                game.flashes.pop(wi, None)
                                continue
                            on = int(el / 0.1) % 2 == 0
                            wall_display[wi] = [255, 255, 255] if on else [0, 0, 0]

                        # ── HARDWARE WRITE (COM9 emitters + COM7 lamps) ─────
                        _now = time.time()
                        if USE_SERIAL_HD and game.running and \
                                _now - getattr(game, "_hw_last_draw", 0) >= _HW_DRAW_INTERVAL:
                            with _hw_serial_lock:
                                if _hw_led_control is not None:
                                    try:
                                        _rc = led_table.led_row
                                        _cc = led_table.led_col
                                        _ld2 = [[_normalize_rgb(floor_display[r * _cc + c]) for c in range(_cc)] for r in range(_rc)]
                                        _hw_led_control.draw_screen_by_com(_hw_layout_type, _ld2)
                                        game._hw_draw_count = getattr(game, "_hw_draw_count", 0) + 1
                                    except Exception as _hw_err:
                                        logger.warning(f"HW emit write: {_hw_err}")
                                if _hw_wall_ready and _hw_wall_ctrl is not None:
                                    try:
                                        _lamp = [
                                            _normalize_rgb(wall_arr[0]) if len(wall_arr) > 0 else [0, 0, 0],
                                            _normalize_rgb(wall_arr[1]) if len(wall_arr) > 1 else [0, 0, 0],
                                        ]
                                        _hw_wall_ctrl.draw_wall_light_by_com(_lamp)
                                    except Exception as _hw_err:
                                        logger.warning(f"HW wall write: {_hw_err}")
                                game._hw_last_draw = _now

                        ppos = list(game.player_floor_pos) if game.player_floor_pos else None
                        game.update_state(
                            score=game.score,
                            score2=0,
                            multiplayer=False,
                            time_elapsed=session_elapsed,
                            time_left=max(0, game.game_time_sec - session_elapsed),
                            life=game.life,
                            # 5 hearts scaled to THIS game's own max_life (laser's
                            # real life_value is 200, not hoops' 20 -- divisor must
                            # scale per game, not a hardcoded /4).
                            display_lives=math.ceil(game.life * 5 / game.max_life) if game.max_life else 0,
                            display_max=5,
                            game_over=False,
                            wall_display=wall_display,
                            floor_display=floor_display,
                            wall_count=wall_n,
                            wall_slots=game._wall_sim_slots,
                            dots_per_side=int(_s.get("wall_dots_per_side", 7)),
                            wall_light_table=game._wall_light_table,
                            grid_rows=floor_rows,
                            grid_cols=floor_cols,
                            player_pos=ppos,
                            goal_walls=list(goal_walls),
                            current_level=game.current_level_id,
                            levels_cleared=game.levels_cleared,
                            phase="playing",
                            accepting_input=True,
                            countdown_label=None,
                        )

                        frame_counter["n"] += 1
                        if frame_counter["n"] % 120 == 0:
                            logger.debug(f"Game {game_id}: score={game.score}, "
                                         f"t={total_pass:.1f}s")
                        # Pace ~100fps. running() is a tight loop with no sleep;
                        # wall-clock timing keeps movement correct regardless.
                        time.sleep(0.01)
                        return True
                    except Exception as cb_err:
                        logger.error(f"Frame callback error {game_id}: {cb_err}")
                        return False

                # ── SESSION LOOP ─────────────────────────────────────────────
                # Marathon through level_sequence with effect transitions
                # (countdown / level_clear / level_fail) between gameplay.
                if play is None or not game.level_sequence:
                    logger.warning(f"No Play object or empty level sequence; "
                                   f"session cannot run: {game_id}")
                    game.update_state(game_over=True, game_over_reason="no_levels",
                                      time_left=0, phase="session_end",
                                      accepting_input=False)
                    game.running = False
                    _hw_blank_floor(led_table)
                    return

                from .audio_manager import create_audio_manager
                from .effects_runner import (
                    effects_dir,
                    play_effect_led,
                )

                audio = create_audio_manager()
                _fx_dir = effects_dir()
                countdown_led = _fx_dir / "countdown.led"
                clear_led = _fx_dir / "level_clear.led"
                fail_led = _fx_dir / "level_fail.led"
                bgm_path = GAMES_ROOT / "audio" / "bgm_laser.mp3"
                if not bgm_path.exists():
                    bgm_path = GAMES_ROOT / "audio" / "bgm.mp3"
                game.update_state(backend_audio_active=audio.active)

                def _hw_draw_effect(lt):
                    global _hw_effect_draw_count, _hw_effect_last_nonzero, _hw_effect_last_phase
                    if not (USE_SERIAL_HD and _hw_led_control is not None):
                        logger.warning(
                            f"HW effect draw skipped: USE_SERIAL_HD={USE_SERIAL_HD} "
                            f"ctrl={_hw_led_control is not None}"
                        )
                        return
                    try:
                        rows, cols = lt.led_row, lt.led_col
                        _ld2 = [[_normalize_rgb(lt.led_table[r][c]) for c in range(cols)]
                                for r in range(rows)]
                        nonzero = sum(1 for row in _ld2 for cell in row if any(cell))
                        _hw_effect_draw_count += 1
                        _hw_effect_last_nonzero = nonzero
                        _hw_effect_last_phase = game.current_state.get("phase")
                        if _hw_effect_draw_count <= 3 or _hw_effect_draw_count % 50 == 0:
                            logger.info(
                                f"HW effect draw #{_hw_effect_draw_count} "
                                f"phase={_hw_effect_last_phase} nonzero_cells={nonzero} "
                                f"grid={rows}x{cols}"
                            )
                        with _hw_serial_lock:
                            _hw_led_control.draw_screen_by_com(_hw_layout_type, _ld2)
                    except Exception as _hw_err:
                        logger.warning(f"HW effect draw failed: {_hw_err}")

                def _blank_wall_display():
                    wall_n = len(led_table.get_wall_light_arr())
                    return [[0, 0, 0] for _ in range(wall_n)]

                def _run_countdown():
                    game.accepting_input = False
                    game.update_state(
                        phase="countdown",
                        accepting_input=False,
                        countdown_label=None,
                        wall_display=_blank_wall_display(),
                    )
                    audio.stop_bgm()
                    logger.info(
                        f"Countdown effect path={countdown_led} exists={countdown_led.exists()} "
                        f"size={countdown_led.stat().st_size if countdown_led.exists() else 0}"
                    )
                    if not play_effect_led(
                        countdown_led,
                        game,
                        led_table,
                        play,
                        _load_level_file,
                        phase="countdown",
                        audio=audio,
                        hw_draw_fn=_hw_draw_effect,
                        countdown_ticks=True,
                    ):
                        logger.error(
                            f"Countdown effect missing/failed — no laser array animation: {countdown_led}"
                        )
                    else:
                        logger.info(
                            f"Countdown effect finished HW draws={_hw_effect_draw_count} "
                            f"last_nonzero={_hw_effect_last_nonzero}"
                        )

                def _reset_hazard_timers():
                    if not game.led_table:
                        return
                    lt = game.led_table
                    rows, cols = lt.led_row, lt.led_col
                    lt.table_state_light = [[0.0] * cols for _ in range(rows)]
                    lt.table_state_dark = [[0.0] * cols for _ in range(rows)]
                    lt.last_trigger_span = [[0.0] * cols for _ in range(rows)]
                    st = lt.get_state_table()
                    for r in range(rows):
                        for c in range(cols):
                            st[r][c] = False

                def _run_transition(path, phase_name):
                    game.accepting_input = False
                    audio.stop_bgm()
                    if not play_effect_led(
                        path,
                        game,
                        led_table,
                        play,
                        _load_level_file,
                        phase=phase_name,
                        audio=audio,
                        hw_draw_fn=_hw_draw_effect,
                    ):
                        logger.error(
                            f"Transition effect missing/failed ({phase_name}): {path}"
                        )
                    # No stinger hold — go straight to countdown / session end after (a).
                    audio.play_stinger()
                    _reset_hazard_timers()
                    game._effect_last_floor = None

                def _finish_session():
                    if game.running:
                        _run_transition(clear_led, "level_clear")
                    rows, cols = led_table.led_row, led_table.led_col
                    game.update_state(
                        phase="session_end",
                        accepting_input=False,
                        countdown_label=None,
                        wall_display=_blank_wall_display(),
                        floor_display=[[0, 0, 0] for _ in range(rows * cols)],
                    )
                    _hw_blank_floor(led_table)

                play.callback = _frame_callback
                sequence_exhausted_after_clear = False
                for lvl_idx, lvl_path in enumerate(game.level_sequence):
                    if game._session_over or not game.running:
                        break
                    session_elapsed = time.time() - game.session_start
                    if session_elapsed > game.game_time_sec:
                        game._session_over = True
                        game._end_reason = "timeout"
                        _finish_session()
                        break

                    lvl_id = os.path.basename(lvl_path).rsplit(".", 1)[0]

                    # ── RESTART LOOP: replay this level whenever lives hit 0 with
                    #    >10s left (score persists, HP refills). Exits on level
                    #    clear, session timeout, or true game-over (life=0, <10s).
                    while True:
                        if game._session_over or not game.running:
                            break
                        session_elapsed = time.time() - game.session_start
                        if session_elapsed > game.game_time_sec:
                            game._session_over = True
                            game._end_reason = "timeout"
                            _finish_session()
                            break

                        _run_countdown()
                        _reset_hazard_timers()
                        if game._session_over or not game.running:
                            break

                        dg, go = _load_level_file(lvl_path)
                        if not dg:
                            logger.warning(f"Level {lvl_id} failed to load; aborting level")
                            break
                        game.current_level_id = lvl_id
                        game.reset_for_level()
                        _setup_level(dg, go)
                        session_elapsed = time.time() - game.session_start
                        logger.info(f"▶ Level {lvl_id}: groups={len(dg)}, "
                                    f"mp={game.multiplayer}, board_time={game.board_time_sec}s, "
                                    f"score={game.score}, life={game.life}, "
                                    f"t_left={game.game_time_sec - session_elapsed:.0f}s")

                        game.accepting_input = True
                        game.update_state(
                            phase="playing",
                            accepting_input=True,
                            countdown_label=None,
                            backend_audio_active=audio.active,
                        )
                        if bgm_path.exists():
                            audio.start_bgm(str(bgm_path))

                        play.running_state = True
                        play.total_pass = 0
                        try:
                            play.running(dg)
                        except Exception as run_err:
                            import traceback
                            logger.warning(f"Level {lvl_id} run error: {run_err}\n"
                                           f"{traceback.format_exc()}")
                            game._session_over = True
                            break
                        finally:
                            audio.stop_bgm()
                            game.accepting_input = False

                        if game._session_over:
                            reason = (game.get_state().get("game_over_reason")
                                      or game._end_reason or "")
                            if reason in ("timeout", "out_of_life"):
                                _finish_session()
                            break

                        if game._restart_level:
                            _run_transition(fail_led, "level_fail")
                            game.life = game.max_life
                            game.last_life_loss_time = 0.0
                            _reset_hazard_timers()
                            game._restart_level = False
                            logger.info(f"↻ Life restart: level={lvl_id}, score={game.score}")
                            continue

                        if game._level_cleared:
                            game.levels_cleared += 1
                            _run_transition(clear_led, "level_clear")
                            logger.info(f"✓ Level {lvl_id} cleared "
                                        f"(total cleared={game.levels_cleared})")
                            if lvl_idx == len(game.level_sequence) - 1:
                                sequence_exhausted_after_clear = True
                                game._session_over = True
                                game.update_state(
                                    phase="session_end",
                                    accepting_input=False,
                                    countdown_label=None,
                                )
                                _hw_blank_floor(led_table)
                            break

                        break

                    if game._session_over:
                        break

                if not sequence_exhausted_after_clear and game._session_over:
                    pass  # _finish_session already ran for timeout/out_of_life


                # Session finished (timer/lives/sequence end).
                game._session_over = True
                # Result honesty: 1 = cleared the whole level chain within time,
                # 2 = ran out of session time, 0 = out of life. Only a genuine
                # chain-exhaustion (loop finished with no timeout/out-of-life
                # reason) counts as "complete".
                state_result = game.get_state().get("result")
                if state_result is not None:
                    final_result = state_result          # frame callback already decided (out-of-life/timeout)
                elif game._end_reason == "timeout":
                    final_result = 2
                else:
                    final_result = 1                     # chain fully cleared in time
                final_reason = (game.get_state().get("game_over_reason")
                                or game._end_reason or "session_end")
                final_score = game.compute_final_score(game.score)
                final_score2 = game.compute_final_score(game.score2)
                logger.info(f"Session over: reason={final_reason}, "
                            f"raw_score={game.score} -> final={final_score}, "
                            f"raw_score2={game.score2} -> final2={final_score2}, "
                            f"levels_cleared={game.levels_cleared}")
                game.update_state(game_over=True, time_left=0,
                                  game_over_reason=final_reason, result=final_result,
                                  levels_cleared=game.levels_cleared,
                                  final_score=final_score, final_score2=final_score2)
                game.running = False
                # Session over (timer/lives/sequence end) — blank the
                # physical floor; nothing else will draw to it now.
                _hw_blank_floor(led_table)

            except Exception as e:
                import traceback
                logger.error(f"Game error {game_id}: {e}")
                logger.error(f"Traceback: {traceback.format_exc()}")
                game.running = False
                game.update_state(
                    game_over=True,
                    game_over_reason=str(e)
                )
                # Best-effort blank even on a crash path; game.led_table
                # may still be None if the crash happened before setup.
                _hw_blank_floor(getattr(game, "led_table", None))

        game.running = True   # set synchronously — clear_all() won't skip this thread
        game._sim_pressed = set()
        game.thread = threading.Thread(target=_run_game, daemon=True)
        game.thread.start()

    def stop_game(self, game_id: str) -> dict:
        """Stop game and return final state"""
        game = self.get_game(game_id)
        if not game:
            return {"success": False, "error": f"Game not found: {game_id}"}

        game.running = False
        if game.thread:
            game.thread.join(timeout=5)

        # Manual stop (e.g. via /logout) — blank the physical floor so it
        # doesn't stay lit with the last frame drawn before the stop.
        _hw_blank_floor(getattr(game, "led_table", None))

        final_state = game.get_state()

        with self.lock:
            del self.games[game_id]

        logger.info(f"Game stopped: {game_id}")
        return {"success": True, "state": final_state}

    def cleanup_expired(self):
        """Remove expired games"""
        with self.lock:
            expired = [gid for gid, game in self.games.items() if game.is_expired()]
            for gid in expired:
                del self.games[gid]
                logger.warning(f"Game expired and removed: {gid}")

    def get_stats(self) -> dict:
        """Get manager statistics"""
        with self.lock:
            return {
                "active_games": len(self.games),
                "max_games": MAX_CONCURRENT_GAMES,
                "timeout_seconds": GAME_TIMEOUT_SECONDS
            }


# Global instance
_manager = None

def get_manager() -> GameManager:
    """Get GameManager singleton"""
    global _manager
    if _manager is None:
        _manager = GameManager()
    return _manager
