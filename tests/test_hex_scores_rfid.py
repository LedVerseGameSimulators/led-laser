"""Step 0: hex_scores play facts + poll cursor (A1)."""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from api import database as db_mod
from api.database import Database, _coerce_int_or_none, _roster_ids_to_json
from tests.conftest import start_session


def _patch_scores_db(monkeypatch, tmp_path):
    scores_file = tmp_path / "setting" / "ledplaydb.sqlite"
    scores_file.parent.mkdir(parents=True)
    monkeypatch.setattr(db_mod, "_SCORES_DB", str(scores_file))
    import api.main as main_mod

    fresh = Database()
    monkeypatch.setattr(main_mod, "db", fresh)
    return fresh


def _hex_score_count(db: Database) -> int:
    with db._scores_lock:
        con = db._scores_conn()
        n = con.execute("SELECT COUNT(*) FROM hex_scores").fetchone()[0]
        con.close()
    return int(n)


def test_coercion_helpers():
    assert _coerce_int_or_none(None) is None
    assert _coerce_int_or_none("42") == 42
    assert _coerce_int_or_none("x") is None
    assert _roster_ids_to_json([1, 2]) == "[1, 2]"
    assert _roster_ids_to_json(None) is None


def test_record_and_get_scores_since_includes_play_facts(monkeypatch, tmp_path):
    scores_file = tmp_path / "setting" / "ledplaydb.sqlite"
    scores_file.parent.mkdir(parents=True)
    monkeypatch.setattr(db_mod, "_SCORES_DB", str(scores_file))

    db = Database()
    ts_before = "2000-01-01T00:00:00"
    ok = db.record_game_score({
        "card_id": "CARD-A",
        "card_id2": "",
        "multiplayer": False,
        "level": "1",
        "score": 900,
        "play_mode": "quick_play",
        "session_id": 10,
        "group_id": 3,
        "roster_size_at_play": 4,
        "roster_player_ids": [101, 102, 103, 104],
    })
    assert ok

    rows = db.get_scores_since(ts_before)
    assert len(rows) >= 1
    row = rows[-1]
    assert row["play_mode"] == "quick_play"
    assert row["session_id"] == 10
    assert row["group_id"] == 3
    assert row["roster_size_at_play"] == 4
    assert json.loads(row["roster_player_ids"]) == [101, 102, 103, 104]
    assert row["card_id2"] in ("", None) or row["card_id2"] == ""


def test_get_scores_since_uses_gte_cursor(monkeypatch, tmp_path):
    scores_file = tmp_path / "setting" / "ledplaydb.sqlite"
    scores_file.parent.mkdir(parents=True)
    monkeypatch.setattr(db_mod, "_SCORES_DB", str(scores_file))

    db = Database()
    fixed_ts = "2099-06-15T12:00:00"
    with db._scores_lock:
        con = db._scores_conn()
        con.execute(
            "INSERT INTO hex_scores (card_id, score, ts, game, play_mode) VALUES (?,?,?,?,?)",
            ("EDGE", 1, fixed_ts, db_mod.GAME_NAME, "tournament"),
        )
        con.commit()
        con.close()

    rows = db.get_scores_since(fixed_ts)
    assert any(r["ts"] == fixed_ts and r["card_id"] == "EDGE" for r in rows)


def test_logout_does_not_write_after_save_score(client, monkeypatch, tmp_path):
    db = _patch_scores_db(monkeypatch, tmp_path)
    gid = start_session(client)
    client.post("/save-score", json={
        "card_id": "TEST001",
        "level": "1",
        "score": 100,
        "play_mode": "quick_play",
    })
    assert _hex_score_count(db) == 1
    resp = client.post("/logout", json={"card_id": "TEST001", "game_id": gid})
    assert resp.status_code == 200
    assert resp.json().get("success") is True
    assert _hex_score_count(db) == 1


def test_guest_logout_writes_no_hex_scores(client, monkeypatch, tmp_path):
    db = _patch_scores_db(monkeypatch, tmp_path)
    gid = start_session(client)
    assert _hex_score_count(db) == 0
    resp = client.post("/logout", json={"card_id": "", "game_id": gid})
    assert resp.status_code == 200
    assert resp.json().get("success") is True
    assert _hex_score_count(db) == 0


def test_save_score_api_passes_play_facts(client):
    payload = {
        "card_id": "API-CARD",
        "level": "2",
        "score": 50,
        "play_mode": "tournament",
        "session_id": 7,
        "group_id": 2,
        "roster_size_at_play": 2,
        "roster_player_ids": [1, 2],
    }
    resp = client.post("/save-score", json=payload)
    assert resp.status_code == 200
    assert resp.json().get("success") is True
