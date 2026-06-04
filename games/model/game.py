# Source Generated with Decompyle++
# File: game.pyc (Python 3.7)

from model.setting import Setting, Color

class Game:
    
    def __init__(self, name, row, col, game_level, zone_row_from, zone_row_to, zone_col_from, zone_col_to, zone_scale, wall_light, screen, corner_line_start, game_area_adaption = (Setting.ROW, Setting.COL, Setting.STANDARD, 0, None, 0, None, Setting.NO, Setting.NO, Setting.NO, 0, True)):
        self.name = name
        self.row = row
        self.col = col
        self.game_level = game_level
        self.zone_row_from = zone_row_from
        if zone_row_to is None:
            self.zone_row_to = row
        else:
            self.zone_row_to = zone_row_to
        self.zone_col_from = zone_col_from
        if zone_col_to is None:
            self.zone_col_to = col
        else:
            self.zone_col_to = zone_col_to
        self.zone_scale = zone_scale
        self.wall_light = wall_light
        self.screen = screen
        self.corner_line_start = corner_line_start
        self.game_area_adaption = game_area_adaption
        self.game_type = None
        self.play_order = True
        self.rule_introduce = None
        self.count_down = None
        self.red_tread = None
        self.clap_light = None
        self.error_clap = None
        self.correct = None
        self.blue_tread = None
        self.game_accomplished = None
        self.ad_video = None
        self.background = Color.BLACK
        self.safe_color = None
        self.cover_action = 'disappear'


