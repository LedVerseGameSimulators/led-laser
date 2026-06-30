# On-Site Hardware Integration Guide — LED Laser Trap

> **For Cursor agent:** Follow every step in order. Do not skip verification steps. Do not touch the RFID server, SQL server, or any service already running on this PC.

---

## Game Config

| Key | Value |
|-----|-------|
| Game | LED Laser Trap |
| Grid | 6 rows × 16 cols (floor) + wall lights |
| COM ports | 3 (read from shelve — see Step 4) |
| Layout type | read from shelve |
| Display var | `floor_display` (NOT `led_display` — laser is different) |
| Zip extract dir | `C:\activerse\led-laser` |
| Python version | 3.10 or 3.11 |
| Server port | 8001 (adjust if already assigned differently) |

---

## Step 1 — Extract the zip

1. Extract so the structure is:
   ```
   C:\activerse\led-laser\
     api\
     games\
     requirements.txt
     ...
   ```
2. Open **Command Prompt as Administrator**. Use for all remaining steps.

---

## Step 2 — Check Python

```cmd
python --version
pip --version
```

**If missing:** install Python 3.11 via winget or python.org (see HOOPS_ONSITE.md Step 2 for full instructions). Add to PATH.

---

## Step 3 — Install dependencies

```cmd
cd C:\activerse\led-laser
pip install -r requirements.txt
```

---

## Step 4 — Verify shelve (hardware config)

```cmd
cd C:\activerse\led-laser\games
python -c "import shelve; db=shelve.open('setting/led_parameter',flag='r'); [print(k,'=',db[k]) for k in db.keys()]; db.close()"
```

**Expected output includes:**
- `list_com_info` — 3 COM port entries
- `led_layout_type` — integer
- `value_high` — 6 (rows)
- `value_width` — 16 (cols)

Note all 3 COM port names from `list_com_info`.

---

## Step 5 — Verify all 3 COM ports visible

```cmd
python -c "import serial.tools.list_ports; [print(p) for p in serial.tools.list_ports.comports()]"
```

All 3 COM ports from the shelve must appear. If any missing: check USB cables / install CH340 or CP2102 driver.

---

## Step 6 — Run hardware diagnostic

```cmd
cd C:\activerse\led-laser\games
python test_hardware.py
```

**Expected:**
1. `All COM ports opened OK` (3 ports)
2. Floor lights **green** for 3s (6×16 grid)
3. Sensor read: step on tiles → `PRESS detected: row=X col=Y`
4. `Floor cleared. Done.`

> **Note:** Laser Trap also has wall lights (separate from floor). `test_hardware.py` only tests the floor. Wall lights are driven by `wall_display` during gameplay — they will light correctly when the actual game runs.

---

## Step 7 — Start game server with hardware enabled

```cmd
cd C:\activerse\led-laser
set USE_SERIAL_HD=1
python -m uvicorn api.main:app --host 0.0.0.0 --port 8001
```

**Expected startup log:**
```
Hardware ready: 3 port(s), 6×16, layout=X
```

**PowerShell:**
```powershell
$env:USE_SERIAL_HD="1"
python -m uvicorn api.main:app --host 0.0.0.0 --port 8001
```

---

## Step 8 — Verify sim + hardware

1. Browser → `http://localhost:8001`
2. Start a Laser Trap game
3. Floor receives laser pattern (physical LEDs follow game state)
4. Walking into a laser beam registers hit
5. Wall lights respond to game events

---

## What NOT to touch

- RFID server / SQL server running on this PC — leave untouched
- `games/setting/led_parameter` shelve — do not modify

---

## Troubleshooting

**One of 3 COM ports fails to open:** that section of the floor won't light. Check cable for that controller board. Re-run `test_hardware.py` — it prints which ports errored.

**`floor_display` error in logs:** Laser Trap uses `floor_display` (not `led_display`). This is already handled in the patched code — if you see this error it means the wrong game_manager.py was deployed. Verify you extracted the correct zip.

**Port 8001 in use:** `netstat -ano | findstr :8001` → `taskkill /PID <pid> /F`
