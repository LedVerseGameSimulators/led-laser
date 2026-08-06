"""TDD gate: Laser effects session loop (TESTING_CONTRACT T1–T8)."""
from __future__ import annotations

import os
import time

import pytest

from tests.conftest import (
    EFFECTS,
    LEVELS,
    drain_life_on_red,
    get_state,
    poll_phase,
    poll_until,
    score_goal_wall,
    send_wall_press,
    send_wall_release,
    start_session,
)


@pytest.fixture
def quick_level():
    return str(LEVELS / "quick_score.led")


@pytest.fixture
def red_level():
    return str(LEVELS / "red_drain.led")


class TestSessionStartAndInput:
    """T1, T7, T8 — first red batch per TESTING_CONTRACT."""

    def test_t1_session_start_reaches_playing(self, client, quick_level):
        gid = start_session(client, levels=quick_level)
        poll_phase(client, gid, "countdown", timeout=10)
        st = poll_phase(client, gid, "playing", timeout=15)
        assert st.get("accepting_input") is True

    def test_t7_input_gated_during_countdown(self, client, quick_level):
        gid = start_session(client, levels=quick_level)
        st = poll_phase(client, gid, "countdown", timeout=10)
        assert st.get("accepting_input") is False
        score_before = st.get("score", 0)
        life_before = st.get("life")
        send_wall_press(client, gid, 2)
        time.sleep(0.15)
        send_wall_release(client, gid, 2)
        mid = get_state(client, gid)
        assert mid.get("phase") in ("countdown", "level_clear", "level_fail", "playing", "session_end", None)
        if mid.get("phase") == "countdown":
            assert mid.get("score", 0) == score_before
            assert mid.get("life") == life_before

    def test_t8_playing_accepts_input(self, client, quick_level):
        gid = start_session(client, levels=quick_level)
        poll_phase(client, gid, "playing", timeout=15)
        st = get_state(client, gid)
        score_before = st.get("score", 0)
        goal = (st.get("goal_walls") or [2])[0]
        send_wall_press(client, gid, goal)
        time.sleep(0.2)
        send_wall_release(client, gid, goal)
        after = poll_until(
            client, gid,
            lambda s: s.get("score", 0) > score_before or s.get("phase") != "playing",
            timeout=10,
        )
        assert after.get("score", 0) > score_before or after.get("phase") in (
            "level_clear", "countdown", "session_end"
        )


class TestClearAndFailLoops:
    """T2, T3 — mid-session transitions."""

    def test_t2_countdown_after_level_clear(self, client, quick_level):
        two = f"{quick_level},{quick_level}"
        gid = start_session(client, levels=two)
        poll_phase(client, gid, "playing", timeout=15)
        goal = (get_state(client, gid).get("goal_walls") or [2])[0]
        score_goal_wall(client, gid, goal)
        poll_until(
            client, gid,
            lambda s: s.get("score", 0) > 0,
            timeout=10,
        )
        poll_phase(client, gid, "level_clear", timeout=25)
        poll_phase(client, gid, "countdown", timeout=20)
        st = poll_phase(client, gid, "playing", timeout=20)
        assert st.get("accepting_input") is True

    def test_t3_fail_restart_same_level(self, client, red_level):
        os.environ["LASER_TEST_LIFE_VALUE"] = "3"
        gid = start_session(client, levels=red_level, game_time_sec="60")
        poll_phase(client, gid, "playing", timeout=15)
        level_before = get_state(client, gid).get("current_level")
        deadline = time.time() + 25
        saw_fail = False
        while time.time() < deadline and not saw_fail:
            score_goal_wall(client, gid, 2, hold_sec=0.08)
            st = get_state(client, gid)
            if st.get("phase") == "level_fail":
                saw_fail = True
                break
            time.sleep(0.05)
        assert saw_fail, "expected level_fail phase during life drain"
        poll_phase(client, gid, "countdown", timeout=25)
        st = poll_phase(client, gid, "playing", timeout=25)
        assert st.get("current_level") == level_before
        assert st.get("accepting_input") is True


class TestSessionEnd:
    """T4, T5, T6 — session end paths."""

    def test_t4_timer_expire_no_countdown_after(self, client, quick_level):
        gid = start_session(client, levels=quick_level, game_time_sec="2")
        poll_phase(client, gid, "playing", timeout=15)
        poll_until(
            client, gid,
            lambda s: s.get("phase") in ("level_clear", "session_end") or s.get("game_over"),
            timeout=20,
        )
        time.sleep(0.5)
        st = get_state(client, gid)
        assert st.get("phase") in ("session_end", "level_clear") or st.get("game_over")
        # Must not start another countdown after session end
        assert st.get("phase") != "countdown"

    def test_t5_life_zero_near_timeout_uses_clear_not_fail(self, client, red_level):
        gid = start_session(client, levels=red_level, game_time_sec="12")
        poll_phase(client, gid, "playing", timeout=15)
        poll_until(
            client, gid,
            lambda s: (s.get("time_left") or 999) <= 10.0,
            timeout=15,
        )
        drain_life_on_red(client, gid, hits=8)
        st = poll_until(
            client, gid,
            lambda s: s.get("phase") in ("level_clear", "session_end") or s.get("game_over"),
            timeout=25,
        )
        assert st.get("phase") in ("level_clear", "session_end") or st.get("game_over")
        assert st.get("phase") != "level_fail"

    def test_t6_last_level_cleared_session_end(self, client, quick_level):
        gid = start_session(client, levels=quick_level)
        poll_phase(client, gid, "playing", timeout=15)
        goal = (get_state(client, gid).get("goal_walls") or [2])[0]
        score_goal_wall(client, gid, goal)
        poll_until(client, gid, lambda s: s.get("score", 0) > 0, timeout=10)
        poll_phase(client, gid, "level_clear", timeout=25)
        st = poll_until(
            client, gid,
            lambda s: s.get("phase") == "session_end" or s.get("game_over"),
            timeout=25,
        )
        assert st.get("phase") in ("session_end", None) or st.get("game_over")
        time.sleep(0.3)
        final = get_state(client, gid)
        assert final.get("phase") != "countdown"


def test_effects_fixtures_exist():
    for name in ("countdown.led", "level_clear.led", "level_fail.led"):
        assert (EFFECTS / name).exists(), f"missing fixture {name}"
