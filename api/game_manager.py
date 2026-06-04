"""
Game Manager - Manages running Play instances and game state
"""
import uuid
import threading
import time
import asyncio
import os
import shelve as _shelve
from typing import Dict, Optional
from loguru import logger
from .config import GAME_TIMEOUT_SECONDS, MAX_CONCURRENT_GAMES

# Will import after config is set
# from game_play.Play import Play

# Real game settings live in the decompiled project's shelve DBs.
_CLONE_ROOT = "/Users/apple/parallel-work/ledhexagon_clone"
_LED_PARAM = f"{_CLONE_ROOT}/setting/led_parameter"
_DEBUG_PARAM = f"{_CLONE_ROOT}/setting/debug_parameter"

# Sensible fallbacks if the shelve can't be read.
_SETTINGS_DEFAULTS = {
    "game_time_sec": 300.0,    # game_time_sw (min) * 60
    "life_value": 20,          # life_value_sw  (starting HP)
    "leval_span": 0.9,         # leval_span_sw  (speed span)
    "tread_red_time": 0.01,    # debug: secs on red before life loss
    "life_value_count_time": 1.2,  # debug: min secs between life losses
}

_settings_cache = None


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
                        color = getattr(group, 'color', (0, 255, 0))
                        if hasattr(self.led_table, 'set_color_table_by_set_cell'):
                            self.led_table.set_color_table_by_set_cell(set_cell, color)
        except Exception as e:
            logger.debug(f"LED update error: {e}")

    def clear_last_wall_display(self):
        """Clear display for next frame"""
        pass


class GameInstance:
    """Single running game instance"""

    def __init__(self, game_id: str, card_id: str, level: int, difficulty: str):
        self.game_id = game_id
        self.card_id = card_id
        self.level = level
        self.difficulty = difficulty
        self.created_at = time.time()
        self.play = None  # Play object
        self.led_table = None  # LedTable instance (for press input)
        self.dict_group = None  # level groups (for consume-on-hit)
        self.flashes = {}  # cell -> wall-clock start time (display-only hit flash)
        self.score = 0  # accumulated score from presses on lit tiles
        self.scored_active = set()  # goal cells already scored this appearance
        # Per-frame cell classification (rebuilt each frame from dict_group):
        self.goal_cells = set()    # floor cells matching P1 goal color (scoreable)
        self.goal2_cells = set()   # floor cells matching P2 goal color (2-player)
        self.red_cells = set()     # in-time red hazard cells (penalty, stays)
        self.deduct_cells = set()  # DEDUCT_COLOR cells (penalty + consume)
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
        self.board_time_sec = 1e9                   # board length (max group end); set on load
        self.result = None                          # 0 lose / 1 complete / 2 timeout
        self.max_life = _s["life_value"]           # 20 HP
        self.life = self.max_life
        self.last_life_loss_time = 0.0             # for life_value_count_time gate
        self._life_count_time = _s["life_value_count_time"]

        self.current_state = {
            "score": 0,
            "time_elapsed": 0.0,
            "time_left": self.game_time_sec,
            "life": self.max_life,
            "max_life": self.max_life,
            "score2": 0,
            "multiplayer": False,
            "player_pos": [0, 0],
            "led_display": [],
            "game_over": False,
            "game_over_reason": "",
            "result": None
        }
        self.thread = None

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

    def try_score_cell(self, i, j):
        """Type-aware scoring for a press on cell (i,j):
          - red hazard cell  -> -1 point + -1 HP (HP rate-limited)
          - goal_led target  -> +1 point + consume (tile blanks) + flash
          - background decor  -> nothing (neutral)
        goal/red membership is classified per frame in the callback."""
        # Red hazard: penalty + HP loss (gated). Not edge-limited by
        # scored_active (standing on red keeps hurting, rate-limited by time).
        if (i, j) in self.red_cells:
            now = time.time()
            if now - self.last_life_loss_time >= self._life_count_time:
                self.score -= 1
                if self.score < 0:
                    self.score = 0
                if self.multiplayer:          # red hurts both players in 2P
                    self.score2 -= 1
                    if self.score2 < 0:
                        self.score2 = 0
                self.life -= 1
                self.last_life_loss_time = now
            return
        # DEDUCT tile: penalty (-1 score, -1 life) then consume (edge-triggered).
        if (i, j) in self.deduct_cells and (i, j) not in self.scored_active:
            self.scored_active.add((i, j))
            self.score -= 1
            if self.score < 0:
                self.score = 0
            self.life -= 1
            self._consume_cell(i, j)
            return
        in_p1 = (i, j) in self.goal_cells
        in_p2 = (i, j) in self.goal2_cells
        same_color = in_p1 and in_p2   # DK03-style: both players same color

        if same_color:
            # Alternate P1→P2→P1→P2 per cell so both players score fairly.
            if (i, j) in self.p2_next_cells:
                if (i, j) not in self.scored_active2:
                    self.scored_active2.add((i, j))
                    self.score2 += 1
                    self.p2_next_cells.discard((i, j))
                    self._consume_cell(i, j)
            else:
                if (i, j) not in self.scored_active:
                    self.scored_active.add((i, j))
                    self.score += 1
                    self.p2_next_cells.add((i, j))  # next time → P2
                    self._consume_cell(i, j)
            return

        # P1 goal: score + consume
        if in_p1 and (i, j) not in self.scored_active:
            self.scored_active.add((i, j))
            self.score += 1
            self._consume_cell(i, j)
            return
        # P2 goal: separate score + consume
        if in_p2 and (i, j) not in self.scored_active2:
            self.scored_active2.add((i, j))
            self.score2 += 1
            self._consume_cell(i, j)
            return
        # else: background decor — neutral, no effect.

    def _consume_cell(self, i, j):
        """Remove a stepped goal tile from its group(s) so it blanks.
        2P (.ledb multiplayer): respawns after respawn_delay.
        1P: follows native level timing — groups with staggered start_times
        provide natural wave progression; no artificial respawn."""
        reappear_at = time.time() + self.respawn_delay if self.multiplayer else None
        if self.dict_group:
            for g in self.dict_group.values():
                sm = getattr(g, "start_member", None)
                if not sm:
                    continue
                if (i, j) in sm:
                    try:
                        if isinstance(sm, set):
                            sm.discard((i, j))
                        else:
                            sm.remove((i, j))
                        if reappear_at is not None:
                            self.pending_respawn.append([g, (i, j), reappear_at])
                    except Exception:
                        pass
        # display-only hit flash (white blink) for ~0.4s
        self.flashes[(i, j)] = time.time()

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

    def apply_input(self, row: int, col: int, action: str):
        """Player input from simulator: press/release a tile.
        Press scores immediately if the tile is lit (mouse clicks are
        instantaneous, so we can't wait for the next frame)."""
        if self.led_table is None:
            return False
        # Ignore presses outside the level's active zone (e.g. 5x9).
        z = self.zone
        if z and not (z[0] <= row < z[1] and z[2] <= col < z[3]):
            return False
        with self.input_lock:
            if action == "press":
                self.led_table.press_cell(row, col)
                self.try_score_cell(row, col)  # score on press (instant clicks)
            elif action == "release":
                self.led_table.release_cell(row, col)
        return True


class GameManager:
    """Manages all running game instances"""

    def __init__(self):
        self.games: Dict[str, GameInstance] = {}
        self.lock = threading.Lock()
        logger.info("GameManager initialized")

    def clear_all(self):
        """Stop and remove all existing games (kiosk = one game at a time)."""
        with self.lock:
            for gid, g in list(self.games.items()):
                g.running = False
            self.games.clear()
        logger.info("Cleared all existing games")

    def create_game(self, card_id: str, level: int, difficulty: str) -> str:
        """Create new game instance. Clears any prior games first (kiosk model)."""
        self.clear_all()
        with self.lock:
            game_id = str(uuid.uuid4())[:8]
            game = GameInstance(game_id, card_id, level, difficulty)

            # Eagerly set multiplayer from file extension BEFORE the load
            # thread starts, so _consume_cell respawns correctly even if
            # a press arrives before the shelve is fully loaded (~7s).
            _clone = "/Users/apple/parallel-work/ledhexagon_clone"
            _ledb = os.path.join(_clone, "source", "---", f"{level}.ledb")
            if os.path.exists(_ledb):
                game.multiplayer = True
                logger.info(f"Game created: {game_id} multiplayer=True (card={card_id}, level={level})")
            else:
                logger.info(f"Game created: {game_id} (card={card_id}, level={level})")

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
                logger.info(f"Starting game loop: {game_id}")
                game.running = True

                # Import game modules
                import shelve
                import os
                from game_play.Play import Play
                from game_play.game_running import LedTable
                from model.setting import Setting

                # Initialize game components (16x26 grid from settings)
                logger.debug(f"Initializing LED table for game {game_id}")
                led_table = LedTable(wall_light_arr_len=100, led_row=16, led_col=26)

                logger.debug(f"Creating Play instance for game {game_id}")
                play = Play(led_table, game_level=game.level)

                # Sweep speed scale (cells/sec = (1/group.speed) * game_level_speed).
                # Lower = slower sweep. Tune per difficulty to match real game pace.
                difficulty_speed = {"easy": 0.25, "normal": 0.4, "hard": 0.6}
                play.game_level_speed = difficulty_speed.get(game.difficulty, 0.4)

                # Try to load real game data from .led files
                dict_group = None
                game_obj = None
                try:
                    import zipfile
                    import tempfile

                    # Resolve level file across all buckets:
                    #   Extra/*.led  → single-player test levels
                    #   source/---/*.ledb → basic 2P
                    #   source/--/*.led  → advanced 1P
                    #   source/-/*.led   → pro 1P
                    level_id = str(game.level) if game.level else "17"
                    clone = "/Users/apple/parallel-work/ledhexagon_clone"
                    candidates = [
                        os.path.join(clone, "Extra",      f"{level_id}.led"),
                        os.path.join(clone, "source", "---", f"{level_id}.ledb"),
                        os.path.join(clone, "source", "--",  f"{level_id}.led"),
                        os.path.join(clone, "source", "-",   f"{level_id}.led"),
                    ]
                    led_file = next((p for p in candidates if os.path.exists(p)), None)

                    if led_file:
                        logger.debug(f"Loading game from .led file: {led_file}")

                        # Extract zip and load shelve database.
                        # Both .led and .ledb use same structure: <id>/game_file.*
                        with tempfile.TemporaryDirectory() as tmpdir:
                            with zipfile.ZipFile(led_file, 'r') as z:
                                z.extractall(tmpdir)

                            # Inner folder may be level_id or filename stem
                            game_file_path = os.path.join(tmpdir, level_id, "game_file")
                            if not os.path.exists(game_file_path + ".dat"):
                                # Try walking to find it
                                for root, _, files in os.walk(tmpdir):
                                    if any(f.startswith("game_file") for f in files):
                                        game_file_path = os.path.join(root, "game_file")
                                        break
                            if os.path.exists(game_file_path + ".dat"):
                                db = shelve.open(game_file_path)
                                dict_group = db.get("dict_group")
                                game_obj = db.get("para_key_game")
                                db.close()

                                if dict_group and game_obj:
                                    logger.info(f"✓ Loaded real game: level {level_id}, groups={len(dict_group) if isinstance(dict_group, dict) else '?'}")
                                else:
                                    logger.warning(f"Game data missing in level {level_id}: dict_group={bool(dict_group)}, game={bool(game_obj)}")
                    else:
                        logger.warning(f"Level file not found for: {level_id}")

                except Exception as load_err:
                    logger.warning(f"Could not load .led file: {load_err}. Using mock loop.")

                game.play = play
                game.led_table = led_table  # expose for press input
                game.dict_group = dict_group  # for consume-on-hit
                # Board length = max group end_time; board ends at min(board, session).
                try:
                    if dict_group:
                        game.board_time_sec = max(
                            (getattr(g, "end_time_sec", 0) for g in dict_group.values()),
                            default=1e9)
                except Exception:
                    game.board_time_sec = 1e9
                # Active play zone from the level (e.g. 5x9); guards input.
                if game_obj is not None:
                    try:
                        game.zone = (
                            int(getattr(game_obj, "zone_row_from", 0)),
                            int(getattr(game_obj, "zone_row_to", 16)),
                            int(getattr(game_obj, "zone_col_from", 0)),
                            int(getattr(game_obj, "zone_col_to", 26)),
                        )
                        logger.info(f"Play zone: {game.zone}")
                    except Exception:
                        game.zone = None
                # Set multiplayer EAGERLY from dict_group so _consume_cell
                # schedules respawn even if press arrives before first callback frame.
                if dict_group:
                    game.multiplayer = any(
                        getattr(g, "type", None) == Setting.SCREEN_LIGHT
                        for g in dict_group.values()
                    )
                    if game.multiplayer:
                        logger.info(f"Multiplayer level detected: {level_id}")

                game_start_time = time.time()

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

                if dict_group:
                    for _g in dict_group.values():
                        try:
                            _ensure_anim(_g)
                        except Exception:
                            pass

                # Per-frame callback fired by Play.update() inside Play.running().
                # By this point Play has: moved groups (deal_all_direction by
                # speed), advanced total_pass, cleared+redrawn led_table for the
                # current frame. We score presses and publish the frame.
                # Returning False makes Play.running() stop (timeout / Stop btn).
                frame_counter = {"n": 0}

                def _frame_callback(play_self, dgroup, time_pass, total_pass):
                    try:
                        # End conditions + result code (faithful to original):
                        #   life<=0            -> result 0 (lose)
                        #   total_pass>board   -> result 1 (board complete / win)
                        #   session time up    -> result 2 (timeout)
                        if game.life <= 0:
                            game.update_state(game_over_reason="out_of_life", result=0)
                            return False
                        if total_pass > game.board_time_sec:
                            game.update_state(game_over_reason="completed", result=1)
                            return False
                        if (not game.running) or game.is_expired() \
                                or total_pass > game.game_time_sec:
                            game.update_state(game_over_reason="timeout", result=2)
                            return False

                        grid = led_table.led_table
                        state = led_table.state_table

                        # 1) Determine goal colors from indicators.
                        #    goal_led  = P1; goal2_led = P2 (multiplayer only).
                        for g in dgroup.values():
                            gtype = getattr(g, "type", None)
                            if not g.start_member:
                                continue
                            if not (g.start_time_sec <= total_pass <= g.end_time_sec):
                                continue
                            if gtype == Setting.WALL_LIGHT:
                                game.goal_color = _group_main_color(g.color)
                            elif gtype == Setting.SCREEN_LIGHT:
                                game.goal2_color = _group_main_color(g.color)
                                game.multiplayer = True

                        # 2) CLASSIFY floor (normal_led) cells:
                        #    - color == goal_color -> scoreable target
                        #    - DEDUCT_COLOR         -> penalty + consume
                        #    - red                  -> hazard (stays)
                        #    - else                 -> decor (neutral)
                        goal_cells = set()
                        goal2_cells = set()
                        red_cells = set()
                        deduct_cells = set()
                        gc = game.goal_color
                        gc2 = game.goal2_color
                        for g in dgroup.values():
                            sm = getattr(g, "start_member", None)
                            if not sm:
                                continue
                            if getattr(g, "type", None) != Setting.FLOOR_LIGHT:
                                continue
                            if not (g.start_time_sec <= total_pass <= g.end_time_sec):
                                continue
                            mc = _group_main_color(g.color)
                            is_deduct = _rgb_is_deduct(mc)
                            # Goal color OVERRIDES red classification:
                            # e.g. DK09 where P2 goal indicator = (254,0,0).
                            # A tile that matches P1 or P2 goal color is scored,
                            # not penalized, even if it looks red.
                            is_p1_color = (gc is not None and mc == gc)
                            is_p2_color = (gc2 is not None and mc == gc2)
                            is_red = (not is_deduct and not is_p1_color
                                      and not is_p2_color and _rgb_is_red(mc))
                            is_goal = is_p1_color and not is_deduct
                            is_goal2 = is_p2_color and not is_deduct
                            same_color_2p = (is_goal and is_goal2)
                            for cell in sm:
                                ci = round(cell[0]); cj = round(cell[1])
                                if not (0 <= ci < led_table.led_row and 0 <= cj < led_table.led_col):
                                    continue
                                if is_deduct:
                                    deduct_cells.add((ci, cj))
                                elif is_red:
                                    red_cells.add((ci, cj))
                                elif same_color_2p:
                                    # Checkerboard spatial split so each player
                                    # has their own distinct tiles even when
                                    # P1 and P2 share the same goal color (DK03).
                                    if (ci + cj) % 2 == 0:
                                        goal_cells.add((ci, cj))
                                    else:
                                        goal2_cells.add((ci, cj))
                                elif is_goal:
                                    goal_cells.add((ci, cj))
                                elif is_goal2:
                                    goal2_cells.add((ci, cj))
                        game.goal_cells = goal_cells
                        game.goal2_cells = goal2_cells
                        game.red_cells = red_cells
                        game.deduct_cells = deduct_cells

                        # 2) SCORE pressed cells (type-aware). Drop scored marks
                        #    for goals that are no longer active so they can score
                        #    again if they reappear.
                        with game.input_lock:
                            if game.multiplayer:
                                game.process_respawns()
                            # Keep scored marks for ACTIVE goal/deduct cells only.
                            # Deduct cells must stay in scored_active while pressed
                            # or they fire every single frame (life drain per frame).
                            active_consumables = goal_cells | goal2_cells | deduct_cells
                            game.scored_active &= active_consumables
                            game.scored_active2 &= goal2_cells
                            for i in range(led_table.led_row):
                                for j in range(led_table.led_col):
                                    if state[i][j]:
                                        game.try_score_cell(i, j)

                        # 2) Build a SEPARATE display buffer (don't touch led_table).
                        led_display = [_normalize_rings(cell)
                                       for row in grid for cell in row]
                        cols = led_table.led_col

                        # 2a) PULSE: shimmer goal-color tiles between 60-100%
                        #     brightness using a sin-wave (1s period).
                        #     LedGroup.breath() oscillates to 0 making tiles
                        #     invisible — replaced with this approach.
                        #     Decor tiles remain static (no pulse).
                        import math as _math
                        pulse = 0.60 + 0.40 * (0.5 + 0.5 * _math.sin(total_pass * _math.pi * 2))
                        goal_cs = {gc, gc2} - {None}
                        for g in dgroup.values():
                            try:
                                sm = getattr(g, "start_member", None)
                                if not sm:
                                    continue
                                if not (g.start_time_sec <= total_pass <= g.end_time_sec):
                                    continue
                                mc = _group_main_color(g.color)
                                if mc not in goal_cs:
                                    continue
                                orig_rings = (g.color
                                              if isinstance(g.color[0], (list, tuple))
                                              else [g.color] * 3)
                                bc = [[int(ch * pulse) for ch in ring]
                                      for ring in orig_rings]
                                for cell in sm:
                                    ci = round(cell[0]); cj = round(cell[1])
                                    if 0 <= ci < led_table.led_row and 0 <= cj < cols:
                                        led_display[ci * cols + cj] = bc
                            except Exception:
                                continue

                        # 2b) FLASH: stepped tiles blink white ~0.4s then vanish.
                        now = time.time()
                        for cell, t0 in list(game.flashes.items()):
                            el = now - t0
                            if el > 0.4:
                                game.flashes.pop(cell, None)
                                continue
                            fi, fj = cell
                            on = int(el / 0.1) % 2 == 0
                            col = [255, 255, 255] if on else [0, 0, 0]
                            led_display[fi * cols + fj] = [col[:], col[:], col[:]]

                        game.update_state(
                            score=game.score,
                            score2=game.score2,
                            multiplayer=game.multiplayer,
                            time_elapsed=total_pass,
                            time_left=max(0, game.game_time_sec - total_pass),
                            life=game.life,
                            game_over=False,
                            led_display=led_display,
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

                # Run the REAL game loop. Play.running() moves groups (sweeping
                # patterns), advances time, and fires _frame_callback each frame.
                if dict_group:
                    logger.info(f"Running real game logic via Play.running(): {game_id}")
                    play.callback = _frame_callback
                    try:
                        play.running(dict_group)
                    except Exception as run_err:
                        logger.error(f"Play.running() error: {run_err}", exc_info=True)
                    # Loop exited -> game over
                    game.update_state(game_over=True, time_left=0)
                else:
                    logger.debug(f"No game data, using mock loop: {game_id}")
                    # Fallback mock loop
                    frame_count = 0
                    while game.running and not game.is_expired():
                        try:
                            elapsed = time.time() - game_start_time
                            frame_count += 1
                            score = max(0, int(elapsed * 10))

                            game.update_state(
                                score=score,
                                time_elapsed=elapsed,
                                time_left=max(0, 180 - elapsed),
                                game_over=elapsed > 180
                            )

                            time.sleep(0.016)

                            if frame_count % 60 == 0:
                                logger.debug(f"Game {game_id}: score={score}, elapsed={elapsed:.1f}s")

                        except Exception as frame_error:
                            logger.error(f"Frame update error {game_id}: {frame_error}")
                            break

                game.running = False

            except Exception as e:
                logger.error(f"Game error {game_id}: {e}", exc_info=True)
                game.running = False
                game.update_state(
                    game_over=True,
                    game_over_reason=str(e)
                )

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
