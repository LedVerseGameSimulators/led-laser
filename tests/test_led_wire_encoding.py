"""Wire-encoding TDD: payload channels 0..254, header stays [255, 255]."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
GAMES = REPO / "games"
if str(GAMES) not in sys.path:
    sys.path.insert(0, str(GAMES))

# game_manager headless setup may mock `led` during collection of other tests.
for _name in list(sys.modules):
    if _name == "led" or _name.startswith("led."):
        del sys.modules[_name]

from led.wire_encoding import encode_wire_color  # noqa: E402

FRAME_HEADER = [255, 255]


def build_payload(colors):
    payload = list(FRAME_HEADER)
    for color in colors:
        payload.extend(encode_wire_color(color))
    return payload


def _iter_group_rgb(dict_group):
    for group in dict_group.values():
        colors = getattr(group, "color", None) or []
        for cell in colors:
            if isinstance(cell, (list, tuple)) and len(cell) >= 3:
                if isinstance(cell[0], (list, tuple)):
                    for sub in cell:
                        if isinstance(sub, (list, tuple)) and len(sub) >= 3:
                            yield tuple(int(x) for x in sub[:3])
                else:
                    yield tuple(int(x) for x in cell[:3])


class TestEncodeWireColor:
    def test_negative_clamped_to_zero(self):
        assert encode_wire_color((-5, 10, -1)) == (0, 10, 0)

    def test_exact_255_clamped_to_254(self):
        assert encode_wire_color((255, 255, 255)) == (254, 254, 254)

    def test_above_255_clamped_to_254(self):
        assert encode_wire_color((300, 256, 999)) == (254, 254, 254)

    def test_mid_range_unchanged(self):
        assert encode_wire_color((0, 128, 254)) == (0, 128, 254)


class TestWirePayloadAssembly:
    def test_header_preserved_with_extreme_colors(self):
        payload = build_payload([(-1, 128, 300), (255, 0, 0)])
        assert payload[:2] == FRAME_HEADER
        assert payload[2:] == [0, 128, 254, 254, 0, 0]

    def test_no_payload_channel_equals_255(self):
        payload = build_payload([(255, 255, 255), (0, 255, 0), (-10, 300, 50)])
        assert payload[:2] == FRAME_HEADER
        for channel in payload[2:]:
            assert 0 <= channel <= 254
            assert channel != 255


class TestProductionEffectRgbMax:
    """Production effect assets already use <=254; guard against regression."""

    EFFECTS = REPO / "games" / "source" / "effects"

    @pytest.mark.parametrize("name", ["countdown.led", "level_clear.led", "level_fail.led"])
    def test_effect_group_colors_at_most_254(self, name):
        from api.game_manager import _load_level_file

        path = self.EFFECTS / name
        assert path.is_file(), f"missing production effect {path}"
        dict_group, _go = _load_level_file(str(path))
        assert dict_group is not None
        for rgb in _iter_group_rgb(dict_group):
            for channel in rgb:
                assert 0 <= channel <= 254, f"{name} has out-of-range {rgb}"


class TestGameManagerFallbackColor:
    def test_headless_gui_default_group_color_is_safe_green(self):
        from api.game_manager import HeadlessGameGUI
        from model.setting import Color

        class _Group:
            start_member = object()
            start_time_sec = 0
            end_time_sec = 999

        class _Table:
            def set_color_table_by_set_cell(self, _cell, color):
                self.last_color = color

        table = _Table()
        gui = HeadlessGameGUI(table)
        gui.update_draw_led_table_idle_game({_Group(): _Group()}, total_pass=1)
        assert table.last_color == Color.GREEN
        assert max(table.last_color) <= 254
