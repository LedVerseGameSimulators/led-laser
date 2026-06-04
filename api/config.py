"""
API Configuration - Game and Database Settings
"""
import os
from pathlib import Path

# Game Configuration
GAME_NAME = "led_hex"
GAME_DIR = Path("/Users/apple/parallel-work/ledhexagon_clone")
GAME_SOURCE_DIR = GAME_DIR / "game_play"
GAME_LEVEL_DIR = GAME_DIR / "source"
GAME_SETTING_DIR = GAME_DIR / "setting"

# Add game source to path for imports
import sys
if str(GAME_SOURCE_DIR) not in sys.path:
    sys.path.insert(0, str(GAME_SOURCE_DIR))

if str(GAME_DIR) not in sys.path:
    sys.path.insert(0, str(GAME_DIR))

# Database Configuration
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "root")
DB_NAME = os.getenv("DB_NAME", "ledplaydb")

# API Configuration
API_HOST = "0.0.0.0"
API_PORT = int(os.getenv("API_PORT", 8000))
API_DEBUG = os.getenv("API_DEBUG", "False").lower() == "true"

# Game Configuration
MAX_CONCURRENT_GAMES = 10
GAME_TIMEOUT_SECONDS = 600  # 10 minutes
GAME_STATE_UPDATE_INTERVAL = 0.016  # ~60fps

# Session Configuration
SESSION_DURATION_SECONDS = 3600  # 60 minutes
