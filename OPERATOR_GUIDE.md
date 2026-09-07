# LED Laser Operator Guide

Daily operation only. No development commands.

## Start the game

1. Power on the LED floor controllers and USB serial cables.
2. Double-click **`START_GAME.bat`**.
3. Wait for three minimized windows (API / Bridge / UI).
4. Browser opens at <http://localhost:5174>.
5. Leave those windows open while guests play.

First start on a new PC may install packages and take a few minutes.

## Stop the game

1. Finish the current player if possible.
2. Double-click **`STOP_GAME.bat`**.
3. Wait for the stopped message.

Always use `STOP_GAME.bat` before shutting down the PC.

## Addresses

- UI: <http://localhost:5174>
- API health: <http://localhost:8001/health>
- Bridge: <http://localhost:8768>

## Common fixes

### Missing Python or Node.js

Ask tech to run **`SETUP_FIRST_TIME.bat`** (or install Python 3.11 + Node.js LTS), then start again.

### Floor settings missing

Restore `games\setting\led_parameter.dat` (and matching `.bak` / `.dir`). Do not invent settings.

### UI opens but floor is dark

1. `STOP_GAME.bat`
2. Check USB serial cables and controller power
3. `START_GAME.bat` again
4. If still dark, open the minimized **LED Laser API** window and send the error to tech

### RFID card scan fails

Ask tech to check `frontend\.env` has the correct RFID PC IP:
`VITE_RFID_API_URL=http://192.168.1.106:9000`

## Operator rules

- One copy of Laser only (`START_GAME.bat` closes the old one).
- Do not close the minimized service windows during play.
- Do not edit `games\setting`.
- Do not unplug USB while a game is running.
- Use `STOP_GAME.bat` at end of day.
