# Source Generated with Decompyle++
# File: gui_editor_game.pyc (Python 3.7)

import datetime
import os.path as os
import shelve
import sys
import time
import traceback
from loguru import logger
from audio_play import audio
from game_play.game_util import GameUtil
from gui.gui_game_fragment_result import GameFragmentRst
from gui.gui_ui import GuiUI
from gui.language import language
from led import led_control
from model.setting import Setting, Color
from model_in.led_group import LedGroup

class EditorGame:
    MAX_TIME = 7200
    
    def __init__(self, parent, parent_last, life_value, list_game, game_time, player_min_num, last_root, game_unzip_dir = (None, '')):
        logger.info('gui editor game1')
        self.game_util = GameUtil()
        self.game_time = game_time
        self.game_start_time = time.time()
        self.game_record_rt = parent.game_record_rt
        self.game_record_rt.running_to_obj = self
        self.game_record_rt.game_result = 2
        self.game_record_rt.game_blood = life_value
        self.main_obj = parent
        self.last_time = 0
        self.life_value = life_value
        self.game_level = parent.game_level
        self.setting = parent.setting
        self.led_col = None
        self.parent = parent
        self.parent_game_running = parent_last
        self.db = parent.db
        self.cur_game_name = None
        self.cur_game_fragment = None
        self.led_col_wall_light = None
        self.led_col_wall_screen = None
        self.led_row = int(self.setting.value_high.get())
        self.led_col = int(self.setting.value_width.get())
        self.blue_hide_max_time = self.setting.blue_hide_max_time.get()
        self.life_cal = None
        self.list_game = list_game
        self.circle_game = True
        if player_min_num == 0:
            player_min_num = 1
        self.player_nums = player_min_num
        if self.player_nums > 6:
            self.player_nums = 6
        setting = self.setting
        self.list_group_blink = []
        self.trigger_span = 1
        self.prompt_cost = self.setting.hidden_prompt_score.get()
        self.prompt_time = self.setting.hidden_show_time.get()
        self.hidn_tread_show_time = self.setting.hidn_tread_show_time.get()
        self.laser_detct_tm = self.setting.laser_detect_time.get()
        
        try:
            f = shelve.open('./setting/debug_parameter')
            self.trigger_span = float(f.get('life_value_count_time'))
            f.close()
        except:
            self.trigger_span = 1

        cur_game_fragment = self.parent_game_running.cur_game_fragment
        self.audio_shoot_on = cur_game_fragment.blue_tread
        self.audio_shoot_off = cur_game_fragment.red_tread
        leval_span = self.setting.leval_span.get()
        self.game_level_speed = self.game_util.get_game_speed(self.game_level, leval_span)
        wall_light_arr_len = len(self.setting.wall_light_table)
        row = int(self.setting.value_high.get())
        col = int(self.setting.value_width.get())
        wall_line = self.setting.corner_line_start.get()
        self.ui = GuiUI(self, life_value, row, col, wall_light_arr_len, wall_line, 0, **('mode',))
        self.play_running(game_unzip_dir, self.setting)

    
    def init_position_info(self):
        for i in range(self.led_row):
            for j in range(self.led_col):
                self.position_info[i][j] = [
                    [],
                    0]
            
        

    
    def screen_mouse_click_state_get(self):
        coors_click = self.ui.led_table.led_coors_click
        self.ui.led_table.get_state_table()[coors_click[0][0]][coors_click[0][1]] = coors_click[1]
        coors_click = self.ui.led_table.led_coors_click_wall
        self.ui.led_table.get_wall_light_state_array()[coors_click[0][1]] = coors_click[1]

    
    def update_draw_led_table_end_of_play(self):
        
        try:
            self.ui.led_table.clear_led_table()
            led_control.draw_led_color(None, self.ui.led_table.led_table)
        except:
            logger.error('update_draw_led_table_end_ok_f_play{}', traceback.format_exc())


    
    def customized_function(self):
        audio.Audio().stop()
        self.parent_game_running.customized_function()
        self.circle_game = False
        self.running_state = False
        logger.info('editor ui close')

    
    def update_hw_led_new(self):
        
        try:
            if Setting.USE_SERIAL_HD:
                self.parent_game_running.draw_hw_led_color_inc_wal(self.ui.led_table)
                self.ui.update_ui(self.game_record_rt)
                self.parent_game_running.get_hw_led_state_inc_wal(self.ui.led_table)
            else:
                self.ui.update_ui(self.game_record_rt)
                self.screen_mouse_click_state_get()
        except:
            logger.error(traceback.format_exc())


    
    def get_hw_led_state(self):
        
        try:
            if Setting.USE_SERIAL_HD:
                self.parent_game_running.get_hw_led_state_inc_wal(self.ui.led_table)
            else:
                self.screen_mouse_click_state_get()
        except:
            logger.error(traceback.format_exc())


    
    def draw_hw_led_color(self):
        
        try:
            if Setting.USE_SERIAL_HD:
                self.parent_game_running.draw_hw_led_color_inc_wal(self.ui.led_table)
                self.ui.update_ui(self.game_record_rt)
            else:
                self.ui.update_ui(self.game_record_rt)
        except:
            logger.error(traceback.format_exc())


    
    def get_group_state(self, group_member):
        table_state = self.ui.led_table.table_state
        for coors in group_member:
            if table_state[coors[0]][coors[1]]:
                return True
        
        return False

    
    def min_num(self, arr):
        min_ = 10000
        for i in arr:
            if i < min_ and i != 0:
                min_ = i
        return min_

    
    def find_cover_color_coors(self, list_group, time_cur, coors_list, coors_list_red):
        o_led_table = self.ui.led_table
        time_threshold = self.blue_hide_max_time + 5
        for group in list_group:
            if group.type == Setting.FLOOR_LIGHT and group.speed == 0 or time_cur < time_cur:
                if time_cur < group.end_time_sec:
                    pass
                else:
                    group.start_time_sec + time_threshold
                if group.color in self.cover_color or group.color == Color.RED:
                    for cell in group.start_member:
                        i = round(cell[0])
                        j = round(cell[1])
                        if not o_led_table.plus_table[i][j] is not None:
                            if o_led_table.deduct_table[i][j]:
                                coors_list_red.append((i, j))
                            continue
                            for cell in group.start_member:
                                i = round(cell[0])
                                j = round(cell[1])
                                if not o_led_table.plus_table[i][j] is not None:
                                    if o_led_table.deduct_table[i][j]:
                                        coors_list.append((i, j))
                                return None

    
    def color_cover_over_times_prompt(self, dict_group, time_cur):
        pass
