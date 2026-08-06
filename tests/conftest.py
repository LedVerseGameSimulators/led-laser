"""Pytest helpers + env for Laser effects session-loop TDD."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
GAMES_ROOT = REPO / "games"
for _path in (REPO, GAMES_ROOT):
    _s = str(_path)
    if _s not in sys.path:
        sys.path.insert(0, _s)

FIXTURES = REPO / "tests" / "fixtures"
EFFECTS = FIXTURES / "effects"
LEVELS = FIXTURES / "levels"


@pytest.fixture(autouse=True)
def laser_test_env(monkeypatch):
    """Fast effects + short session defaults for all tests in this package."""
    monkeypatch.setenv("USE_SERIAL_HD", "0")
    monkeypatch.setenv("LASER_TEST_MODE", "1")
    monkeypatch.setenv("LASER_EFFECTS_DIR", str(EFFECTS))
    monkeypatch.setenv("LASER_STINGER_HOLD_SEC", "0.05")
    monkeypatch.setenv("LASER_AUDIO_DISABLED", "1")
    monkeypatch.setenv("LASER_TEST_LIFE_VALUE", "3")
    monkeypatch.setenv("LASER_TEST_LIFE_COUNT_TIME", "0.01")
    monkeypatch.setenv("LASER_TEST_GAME_TIME_SEC", "60")
    # Default single quick-score level unless test overrides
    qs = str(LEVELS / "quick_score.led")
    monkeypatch.setenv("LASER_TEST_LEVELS", qs)


@pytest.fixture
def client(laser_test_env):
    from fastapi.testclient import TestClient
    from api.main import app

    with TestClient(app) as c:
        yield c


def start_session(client, *, levels: str | None = None, game_time_sec: str | None = None):
    if levels is not None:
        os.environ["LASER_TEST_LEVELS"] = levels
    if game_time_sec is not None:
        os.environ["LASER_TEST_GAME_TIME_SEC"] = game_time_sec
    resp = client.post("/start-game", json={
        "card_id": "TEST001",
        "level": "A001",
        "difficulty": "normal",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("success"), data.get("error")
    return data["game_id"]


def get_state(client, game_id: str) -> dict:
    resp = client.get(f"/game-state/{game_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("success"), body
    return body["state"]


def poll_until(client, game_id: str, predicate, timeout: float = 30.0, interval: float = 0.05):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = get_state(client, game_id)
        if predicate(last):
            return last
        time.sleep(interval)
    raise AssertionError(f"Timed out waiting for state; last={last}")


def poll_phase(client, game_id: str, phase: str, **kwargs):
    return poll_until(client, game_id, lambda s: s.get("phase") == phase, **kwargs)


def send_wall_press(client, game_id: str, wall_index: int = 2):
    return client.post("/game-input", json={
        "game_id": game_id,
        "wall_index": wall_index,
        "type": "press",
    })


def send_wall_release(client, game_id: str, wall_index: int = 2):
    return client.post("/game-input", json={
        "game_id": game_id,
        "wall_index": wall_index,
        "type": "release",
    })


def score_goal_wall(client, game_id: str, wall_index: int = 2, hold_sec: float = 0.35):
    """Press a goal wall long enough for the game thread to score."""
    send_wall_press(client, game_id, wall_index)
    time.sleep(hold_sec)
    send_wall_release(client, game_id, wall_index)


def drain_life_on_red(client, game_id: str, wall_index: int = 2, hits: int = 5):
    for _ in range(hits):
        score_goal_wall(client, game_id, wall_index, hold_sec=0.08)
        time.sleep(0.05)
