# Source Generated with Decompyle++
# File: group.pyc (Python 3.7)

from model.setting import Color, Setting

class Group:
    
    def __init__(self, name, member, start_time_min, start_time_sec, end_time_min, end_time_sec, color, speed, direct, edge_run_into, gtype, text, scale, start_area, activity_area = (None, 0, 0, 0, 60, Color.GRAY, 0, Setting.DISAPPEAR, Setting.DISAPPEAR, 'floor', [], Setting.SIDE_BOTH, 1, [
        (0, Setting.ROW),
        (0, Setting.COL)])):
        self.name = name
        self.start_member = member
        self.start_time_min = start_time_min
        self.start_time_sec = start_time_sec
        self.end_time_min = end_time_min
        self.end_time_sec = end_time_sec
        self.color = color
        self.speed = speed
        self.direct = direct
        self.edge_run_into = edge_run_into
        self.type = gtype
        self.text = text
        self.scale = scale
        self.start_area = start_area
        self.activity_area = activity_area
        self.move_distance = 0



class Person:
    
    def __init__(self, name, age, start_time):
        self.name = name
        self.age = age
        self.start_time = start_time


