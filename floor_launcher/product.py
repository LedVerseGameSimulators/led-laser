"""Per-product constants. This is the only file that differs between game repos."""

SLUG = "laser"            # kiosk profile slug, release/zip names
DISPLAY_NAME = "LED Laser"
API_PORT = 8001           # must match frontend/src/config.js (source of truth)
BRIDGE_PORT = 8768
# Ports freed on STOP (same set STOP_GAME.bat frees; 5174 = legacy vite preview UI).
STOP_PORTS = (8001, 8768, 5174)
