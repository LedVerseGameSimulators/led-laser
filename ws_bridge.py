"""
WebSocket bridge: headless API game state → simulator UI
Connects to http://localhost:8000 API, broadcasts game state via WebSocket
"""

import asyncio
import json
import threading
import time
from typing import Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
import httpx

app = FastAPI()

# Serve static simulator files
SIMULATOR_STATIC = "/Users/apple/parallel-work/ledhexagon_clone/simulator/static"
app.mount("/static", StaticFiles(directory=SIMULATOR_STATIC), name="static")

HOST = "127.0.0.1"
PORT = 8765
API_BASE_URL = "http://localhost:8000"

class GameBridge:
    """Bridge between API and WebSocket clients"""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.lock = asyncio.Lock()
        self.current_game_id = None
        self.game_state = {}

    async def connect(self, ws: WebSocket):
        await ws.accept()
        async with self.lock:
            self.active_connections.add(ws)
        print(f"✓ Client connected. Total: {len(self.active_connections)}")

    async def disconnect(self, ws: WebSocket):
        async with self.lock:
            self.active_connections.discard(ws)
        print(f"✓ Client disconnected. Total: {len(self.active_connections)}")

    async def broadcast_state(self, game_state: dict):
        """Send game state to all connected clients in simulator format"""
        if not self.active_connections:
            return

        # Use real LED display from game state, or fallback to empty grid.
        # Each cell = 3 ring colors [[R,G,B],[R,G,B],[R,G,B]] (outer,mid,inner).
        led_display = game_state.get("led_display", [])

        def _empty_tile():
            return [[0, 0, 0], [0, 0, 0], [0, 0, 0]]

        if led_display and len(led_display) == 416:  # 16 * 26 = 416
            grid = []
            for i in range(16):
                row = []
                for j in range(26):
                    cell = led_display[i * 26 + j]
                    # 3-ring cell: list of 3 rgb triples
                    if (isinstance(cell, (list, tuple)) and len(cell) >= 3
                            and isinstance(cell[0], (list, tuple))):
                        row.append([list(cell[0]), list(cell[1]), list(cell[2])])
                    # flat rgb -> broadcast to 3 rings
                    elif isinstance(cell, (list, tuple)) and len(cell) >= 3:
                        rgb = list(cell[:3])
                        row.append([rgb, rgb, rgb])
                    else:
                        row.append(_empty_tile())
                grid.append(row)
        else:
            grid = [[_empty_tile() for _ in range(26)] for _ in range(16)]

        msg = json.dumps({
            "type": "frame",
            "rows": 16,
            "cols": 26,
            "grid": grid,
            "fps": 60,
            "game_id": self.current_game_id
        })

        async with self.lock:
            dead = set()
            for ws in self.active_connections:
                try:
                    await ws.send_text(msg)
                except Exception as e:
                    print(f"✗ Send error: {e}")
                    dead.add(ws)
            self.active_connections -= dead

bridge = GameBridge()

@app.get("/")
async def index():
    """Serve simulator UI"""
    return FileResponse(f"{SIMULATOR_STATIC}/index.html")

@app.get("/status")
async def status():
    """Health check"""
    return {
        "status": "ok",
        "game_id": bridge.current_game_id,
        "game_state": bridge.game_state,
        "connected_clients": len(bridge.active_connections)
    }

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """WebSocket endpoint for simulator UI"""
    await bridge.connect(ws)
    async with httpx.AsyncClient() as client:
        try:
            while True:
                # Client sends tile commands: {type:'press'|'release', row, col}
                msg = await ws.receive_text()
                try:
                    data = json.loads(msg)
                    if data.get("type") in ("press", "release"):
                        # Forward to API game-input endpoint
                        await client.post(
                            f"{API_BASE_URL}/game-input",
                            json={
                                "row": data.get("row"),
                                "col": data.get("col"),
                                "type": data["type"],
                            },
                            timeout=2,
                        )
                except Exception as e:
                    print(f"✗ Input forward error: {e}")
        except WebSocketDisconnect:
            await bridge.disconnect(ws)

async def poll_game_state():
    """Poll API for game state and broadcast to clients"""
    async with httpx.AsyncClient() as client:
        while True:
            try:
                # Get active game state from API
                resp = await client.get(f"{API_BASE_URL}/game-state", timeout=5)
                data = resp.json()

                if data.get("success"):
                    # Game running - update state
                    bridge.current_game_id = data["game_id"]
                    bridge.game_state = data["state"]
                    await bridge.broadcast_state(bridge.game_state)
                else:
                    # No active game
                    bridge.current_game_id = None
                    bridge.game_state = {}

                await asyncio.sleep(0.016)  # ~60fps

            except Exception as e:
                print(f"✗ Poll error: {e}")
                await asyncio.sleep(1)

@app.on_event("startup")
async def _start_poller():
    """Run poller in uvicorn's own event loop (same loop as websockets).
    Avoids cross-loop 'bound to a different event loop' errors."""
    asyncio.create_task(poll_game_state())

if __name__ == "__main__":
    print(f"WS Bridge: {HOST}:{PORT}")
    print(f"API: {API_BASE_URL}")
    print(f"Web UI: http://{HOST}:{PORT}")

    # Start WebSocket server (poller launches via startup event)
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
