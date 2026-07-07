"""
WebSocket bridge: headless API game state → Laser wall simulator UI
"""

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
import httpx

app = FastAPI()

SIMULATOR_STATIC = str(Path(__file__).resolve().parent / "simulator" / "static")
app.mount("/static", StaticFiles(directory=SIMULATOR_STATIC), name="static")

HOST = "127.0.0.1"
_DEFAULT_API_PORT = 8001
_DEFAULT_WS_PORT = 8768
API_PORT = int(os.getenv("API_PORT", _DEFAULT_API_PORT))
PORT = int(os.getenv("WS_BRIDGE_PORT", _DEFAULT_WS_PORT))
API_BASE_URL = os.getenv("API_BASE_URL", f"http://localhost:{API_PORT}")


class GameBridge:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.lock = asyncio.Lock()
        self.current_game_id = None
        self.game_state = {}

    async def connect(self, ws: WebSocket):
        await ws.accept()
        async with self.lock:
            self.active_connections.add(ws)

    async def disconnect(self, ws: WebSocket):
        async with self.lock:
            self.active_connections.discard(ws)

    async def broadcast_state(self, game_state: dict):
        if not self.active_connections:
            return

        def _rgb(cell):
            if isinstance(cell, (list, tuple)) and len(cell) >= 3:
                return [int(cell[0]), int(cell[1]), int(cell[2])]
            return [0, 0, 0]

        floor_display = game_state.get("floor_display", [])
        wall_display = [_rgb(w) for w in game_state.get("wall_display", [])]
        rows = int(game_state.get("grid_rows", 6))
        cols = int(game_state.get("grid_cols", 16))
        dots = int(game_state.get("dots_per_side", 7))
        wall_slots = game_state.get("wall_slots") or {"left": [], "right": []}
        player = game_state.get("player_pos")
        goal_walls = game_state.get("goal_walls") or []

        floor = [_rgb(floor_display[i]) if i < len(floor_display) else [0, 0, 0]
                 for i in range(rows * cols)]

        msg = json.dumps({
            "type": "corridor_frame",
            "wall_display": wall_display,
            "wall_slots": wall_slots,
            "dots_per_side": dots,
            "goal_walls": goal_walls,
            "player": player,
            "floor": floor,
            "rows": rows,
            "cols": cols,
            "fps": 60,
            "game_id": self.current_game_id,
        })

        async with self.lock:
            dead = set()
            for ws in self.active_connections:
                try:
                    await ws.send_text(msg)
                except Exception:
                    dead.add(ws)
            self.active_connections -= dead

    async def broadcast_blank(self, rows: int, cols: int):
        if not self.active_connections:
            return
        msg = json.dumps({
            "type": "corridor_frame",
            "wall_display": [],
            "wall_slots": {"left": [], "right": []},
            "dots_per_side": 7,
            "goal_walls": [],
            "player": None,
            "floor": [[0, 0, 0]] * (rows * cols),
            "rows": rows,
            "cols": cols,
            "fps": 30,
            "game_id": None,
        })
        async with self.lock:
            dead = set()
            for ws in self.active_connections:
                try:
                    await ws.send_text(msg)
                except Exception:
                    dead.add(ws)
            self.active_connections -= dead


bridge = GameBridge()


@app.get("/")
async def index():
    return FileResponse(f"{SIMULATOR_STATIC}/index.html")


@app.get("/status")
async def status():
    return {
        "status": "ok",
        "game_id": bridge.current_game_id,
        "connected_clients": len(bridge.active_connections),
    }


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    client_game_id = ws.query_params.get("game_id")
    await bridge.connect(ws)
    async with httpx.AsyncClient() as client:
        try:
            while True:
                msg = await ws.receive_text()
                try:
                    data = json.loads(msg)
                    if data.get("type") in ("press", "release"):
                        body = {"type": data["type"], "game_id": data.get("game_id")}
                        if data.get("row") is not None:
                            body["row"] = data["row"]
                            body["col"] = data["col"]
                        else:
                            body["wall_index"] = data.get("wall_index")
                        await client.post(
                            f"{API_BASE_URL}/game-input",
                            json=body,
                            timeout=2,
                        )
                except Exception as e:
                    print(f"Input forward error: {e}")
        except WebSocketDisconnect:
            await bridge.disconnect(ws)


async def poll_game_state():
    async with httpx.AsyncClient() as client:
        while True:
            try:
                resp = await client.get(f"{API_BASE_URL}/active-game", timeout=5)
                data = resp.json()
                if data.get("success"):
                    bridge.current_game_id = data["game_id"]
                    bridge.game_state = data["state"]
                    await bridge.broadcast_state(bridge.game_state)
                else:
                    bridge.current_game_id = None
                    bridge.game_state = {}
                    await bridge.broadcast_blank(6, 16)
                await asyncio.sleep(0.033)
            except Exception as e:
                print(f"Poll error: {e}")
                await asyncio.sleep(1)


@app.on_event("startup")
async def _start_poller():
    asyncio.create_task(poll_game_state())


if __name__ == "__main__":
    print(f"Laser WS Bridge: {HOST}:{PORT}")
    print(f"API: {API_BASE_URL}")
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
