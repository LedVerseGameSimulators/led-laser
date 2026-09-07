"""Coverage for Laser Group / corporate playlist from games/source_group/."""

from __future__ import annotations

import os

from api import game_manager


def test_group_corporate_order_c02_through_c01_challenge():
    seq = game_manager._build_group_level_sequence("auto")
    assert len(seq) == 9
    assert all("source_group" in p.replace("\\", "/") for p in seq)
    stems = [os.path.basename(p).rsplit(".", 1)[0] for p in seq]
    assert stems[0] == "C02"
    assert stems[7] == "C09"
    assert stems[8].startswith("C01 Challenge")


def test_create_game_accepts_group_mode():
    mgr = game_manager.get_manager()
    gid = mgr.create_game("GUEST", "auto", "normal", mode="group")
    game = mgr.get_game(gid)
    assert game is not None
    assert game.mode == "group"
    assert game.multiplayer is False
    mgr.clear_all()
