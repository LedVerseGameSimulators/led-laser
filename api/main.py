"""
LED Play Game API - FastAPI Backend
Decoupled game logic from Tkinter UI. React frontend connects via HTTP + WebSocket.
"""
from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import json
from loguru import logger
import datetime

from .config import API_HOST, API_PORT, API_DEBUG, GAME_NAME
from .models import (
    LoginRequest, LoginResponse, PlayerInfo,
    StartGameRequest, StartGameResponse,
    GameState, GameInput, GameResult, LogoutRequest, LogoutResponse
)
from .database import get_db
from .game_manager import get_manager

# Setup logging
logger.add("logs/api.log", rotation="500 MB", level="INFO")
logger.info(f"Starting API for game: {GAME_NAME}")

# FastAPI app
app = FastAPI(
    title=f"LED Play API - {GAME_NAME}",
    version="1.0.0",
    debug=API_DEBUG
)

# CORS middleware (for React frontend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Get singletons
db = get_db()
game_manager = get_manager()


# ============= LOGIN ENDPOINT =============
@app.post("/login")
async def login(request: LoginRequest) -> LoginResponse:
    """
    Lookup player by RFID card ID.
    Returns player info or error.
    """
    logger.info(f"Login request: card_id={request.card_id}")

    try:
        player_data = db.get_player_by_card(request.card_id)

        if not player_data:
            logger.warning(f"Card not found: {request.card_id}")
            return LoginResponse(
                success=False,
                error="Card not recognized"
            )

        # Parse player data (varies by index, check db_operation.py)
        # Format: (custom_id, phone, name, public, time_left, pwd, card_id, ...)
        player_info = PlayerInfo(
            custom_id=int(player_data[0]),
            phone=str(player_data[1]),
            name=str(player_data[2]),
            time_left=float(player_data[4]),
            card_id=request.card_id
        )

        logger.info(f"Login success: {player_info.name}")
        return LoginResponse(success=True, player=player_info)

    except Exception as e:
        logger.error(f"Login error: {e}")
        return LoginResponse(success=False, error=str(e))


# ============= START GAME ENDPOINT =============
@app.post("/start-game")
async def start_game(request: StartGameRequest) -> StartGameResponse:
    """
    Start new game instance.
    Returns game_id and WebSocket URL for real-time updates.
    """
    logger.info(f"Start game request: card={request.card_id}, level={request.level}")

    try:
        # Check session remaining time (60-min timer)
        time_left = db.check_session_remaining(request.card_id)
        if time_left is not None and time_left <= 0:
            logger.warning(f"Session expired for card: {request.card_id}")
            return StartGameResponse(
                success=False,
                error="Session time expired (60-minute limit)"
            )

        # Create game instance
        game_id = game_manager.create_game(
            request.card_id,
            request.level,
            request.difficulty
        )

        # Start game loop in background
        game_manager.start_game(game_id)

        ws_url = f"/game/{game_id}"
        logger.info(f"Game started: {game_id}")

        return StartGameResponse(
            success=True,
            game_id=game_id,
            ws_url=ws_url
        )

    except Exception as e:
        logger.error(f"Start game error: {e}")
        return StartGameResponse(success=False, error=str(e))


# ============= GAME STATE WEBSOCKET =============
@app.websocket("/game/{game_id}")
async def game_websocket(websocket: WebSocket, game_id: str):
    """
    WebSocket for real-time game state streaming.
    Game → React: score, LEDs, game state updates
    React → Game: input events (button presses, etc.)
    """
    logger.info(f"WebSocket connected: {game_id}")

    await websocket.accept()
    game = game_manager.get_game(game_id)

    if not game:
        await websocket.close(code=1008, reason="Game not found")
        return

    try:
        while game.running:
            # Send game state to client
            state = game.get_state()
            await websocket.send_json({
                "type": "game_state",
                "data": state
            })

            # Check for input from client
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=0.05)
                input_msg = json.loads(data)
                logger.debug(f"Input received: {input_msg}")
                # TODO: Feed input to Play.py
            except asyncio.TimeoutError:
                pass  # No input, continue

            await asyncio.sleep(0.016)  # ~60fps

        # Game ended
        await websocket.send_json({
            "type": "game_state",
            "data": {**game.get_state(), "game_over": True}
        })

    except Exception as e:
        logger.error(f"WebSocket error {game_id}: {e}")
    finally:
        await websocket.close()
        logger.info(f"WebSocket closed: {game_id}")


# ============= RESULT ENDPOINT =============
@app.get("/result/{game_id}")
async def get_result(game_id: str) -> GameResult:
    """
    Get game result and leaderboard after game ends.
    """
    logger.info(f"Result request: {game_id}")

    try:
        game = game_manager.get_game(game_id)

        if game:
            # Game still exists (not cleaned up yet)
            final_state = game.get_state()
        else:
            # Game already cleaned up, return last known state
            final_state = {}

        # Get leaderboard
        leaderboard = db.get_leaderboard(game_id, limit=10)

        result = GameResult(
            success=True,
            score=final_state.get("score", 0),
            player_name=final_state.get("player_name", "Unknown"),
            time_used=final_state.get("time_elapsed", 0.0),
            difficulty="normal",  # TODO: get from game
            leaderboard=leaderboard
        )

        logger.info(f"Result returned: score={result.score}")
        return result

    except Exception as e:
        logger.error(f"Result error: {e}")
        return GameResult(success=False, error=str(e))


# ============= LOGOUT ENDPOINT =============
@app.post("/logout")
async def logout(request: LogoutRequest) -> LogoutResponse:
    """
    End game session and record score.
    """
    logger.info(f"Logout request: game_id={request.game_id}, card={request.card_id}")

    try:
        result = game_manager.stop_game(request.game_id)

        if result["success"]:
            # Record score to database
            score_data = {
                "card_id": request.card_id,
                "game_id": request.game_id,
                "score": result["state"].get("score", 0),
                "timestamp": datetime.datetime.now().isoformat()
            }
            db.record_game_score(score_data)

        return LogoutResponse(success=result["success"])

    except Exception as e:
        logger.error(f"Logout error: {e}")
        return LogoutResponse(success=False, error=str(e))


# ============= HEALTH CHECK =============
@app.get("/health")
async def health():
    """Health check endpoint"""
    stats = game_manager.get_stats()
    return {
        "status": "ok",
        "game": GAME_NAME,
        "stats": stats
    }


# ============= GAME SETTINGS ENDPOINT =============
@app.get("/game-settings")
async def get_game_settings():
    """Load game settings from setting folder"""
    import shelve

    try:
        setting_path = "/Users/apple/parallel-work/ledhexagon_clone/setting/led_parameter"
        db = shelve.open(setting_path)

        # Load LED layout and dimensions
        wall_layout = db.get("wall_light_layout_real")
        grid_dims = db.get("grid_dimensions")

        settings = {
            "success": True,
            "wall_layout": str(wall_layout)[:100] if wall_layout else "16x26",
            "grid_dims": grid_dims or {"rows": 16, "cols": 26},
            "timeout_seconds": 180,
            "max_score": 1000
        }

        db.close()
        return settings
    except Exception as e:
        logger.warning(f"Could not load settings: {e}, using defaults")
        return {
            "success": True,
            "wall_layout": "16x26",
            "grid_dims": {"rows": 16, "cols": 26},
            "timeout_seconds": 180,
            "max_score": 1000
        }


# ============= GAME LEVELS ENDPOINT =============
@app.get("/levels")
async def get_levels():
    """All levels grouped into 4 categories. Fast — no shelve scan (dir+ext only).

    Categories:
      extra    - Extra/*.led       (1P, test levels 17-26)
      basic    - source/---/*.ledb (2P, DK/YCDK series)
      advanced - source/--/*.led   (1P, YC series)
      pro      - source/-/*.led    (1P, 00-16 large)
    """
    import os, glob as _glob

    clone = "/Users/apple/parallel-work/ledhexagon_clone"

    BUCKETS = [
        ("extra",    os.path.join(clone, "Extra", "*.led"),          False, "led"),
        ("basic",    os.path.join(clone, "source", "---", "*.ledb"), True,  "ledb"),
        ("advanced", os.path.join(clone, "source", "--", "*.led"),   False, "led"),
        ("pro",      os.path.join(clone, "source", "-", "*.led"),    False, "led"),
    ]

    levels = []
    for bucket, pattern, multiplayer, ftype in BUCKETS:
        for f in sorted(_glob.glob(pattern)):
            stem = os.path.basename(f).rsplit(".", 1)[0]
            display = f"Level {stem}" if stem.isdigit() else stem
            levels.append({
                "id":          stem,
                "name":        display,
                "path":        f,
                "category":    bucket,
                "multiplayer": multiplayer,
                "file_type":   ftype,
            })

    by_cat = {}
    for lv in levels:
        by_cat.setdefault(lv["category"], []).append(lv)

    return {
        "success":    True,
        "levels":     levels,
        "categories": by_cat,
        "count":      len(levels),
    }


# ============= GAME INPUT ENDPOINT =============
@app.post("/game-input")
async def game_input(payload: dict):
    """Player input from simulator: press/release a tile.
    Body: {row, col, type: 'press'|'release', game_id?(optional)}.
    Applies to specified game, or first active game if id omitted."""
    row = payload.get("row")
    col = payload.get("col")
    action = payload.get("type", "press")
    game_id = payload.get("game_id")

    if row is None or col is None:
        return {"success": False, "error": "row and col required"}

    game = None
    if game_id:
        game = game_manager.get_game(game_id)
    else:
        for _gid, g in game_manager.games.items():
            game = g
            break

    if not game:
        return {"success": False, "error": "No active game"}

    ok = game.apply_input(int(row), int(col), action)
    return {"success": ok, "score": game.score}


# ============= SAVE SCORE =============
@app.post("/save-score")
async def save_score(payload: dict):
    """Persist a finished game to the leaderboard.
    Body: {card_id, level, score, life, time_used}."""
    try:
        ok = db.record_game_score({
            "card_id": payload.get("card_id", ""),
            "level": payload.get("level", ""),
            "score": payload.get("score", 0),
            "score2": payload.get("score2", 0),
            "life": payload.get("life", 0),
            "lives_start": payload.get("lives_start", 0),
            "result": payload.get("result"),
            "time_used": payload.get("time_used", 0.0),
        })
        return {"success": ok}
    except Exception as e:
        logger.error(f"save-score error: {e}")
        return {"success": False, "error": str(e)}


# ============= LEADERBOARD =============
@app.get("/leaderboard/{level}")
async def leaderboard(level: str, limit: int = 10):
    """Top scores for a level."""
    return {"success": True, "level": level,
            "entries": db.get_leaderboard(level=level, limit=limit)}


# ============= ACTIVE GAME (resume on reload) =============
@app.get("/active-game")
async def active_game():
    """Return the currently-running game (if any) with its full config so the
    frontend can resume the simulator after a page reload instead of starting
    over at login."""
    for gid, g in game_manager.games.items():
        if g.running and not g.get_state().get("game_over"):
            return {
                "success": True,
                "game_id": gid,
                "card_id": g.card_id,
                "level": g.level,
                "difficulty": g.difficulty,
                "state": g.get_state(),
            }
    return {"success": False}


# ============= GAME STATE BY ID =============
@app.get("/game-state/{game_id}")
async def get_game_state_by_id(game_id: str):
    """Get state of a SPECIFIC game (simulator polls its own game)."""
    game = game_manager.get_game(game_id)
    if not game:
        return {"success": False, "error": "Game not found"}
    return {"success": True, "game_id": game_id, "state": game.get_state()}


# ============= GAME STATE ENDPOINT =============
@app.get("/game-state")
async def get_game_state():
    """Get current active game state (for simulator)"""
    stats = game_manager.get_stats()

    if stats["active_games"] == 0:
        return {"success": False, "error": "No active games"}

    # Get first active game
    for game_id, game in game_manager.games.items():
        return {
            "success": True,
            "game_id": game_id,
            "state": game.get_state()
        }

    return {"success": False, "error": "No games found"}


# ============= STARTUP/SHUTDOWN =============
@app.on_event("startup")
async def startup():
    logger.info(f"API starting on {API_HOST}:{API_PORT}")
    logger.info(f"Game: {GAME_NAME}")


@app.on_event("shutdown")
async def shutdown():
    logger.info("API shutting down")
    db.close()


# ============= RUN =============
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=API_HOST,
        port=API_PORT,
        log_level="info"
    )
