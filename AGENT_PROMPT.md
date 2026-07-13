# Onsite Agent Prompt — LED Laser Trap First-Time Hardware Bring-Up

Copy everything below this line and hand it to a fresh Claude Code agent
running ON the physical Windows machine, after this repo's zip has been
extracted there.

---

You are running on a **Windows machine** on-site, physically wired to a
6×16 LED floor (Laser Trap game) plus wall/screen light hardware, as one
of 6 machines on a LAN. This repo was extracted from a zip. Assume the
repo root is `C:\activerse\led-laser` (matching `ONSITE.md`'s documented
extraction path) — if you find the repo at a different path, use that
actual path for every command below instead, but keep everything
consistent within one session.

**This is a Windows machine.** Use `python` (not `python3`), use
PowerShell or Command Prompt syntax (not bash) for env vars and paths —
e.g. `set USE_SERIAL_HD=1` in cmd.exe or `$env:USE_SERIAL_HD=1` in
PowerShell, not `export USE_SERIAL_HD=1`. Use backslashes in paths where
Windows requires them. `ONSITE.md` already assumes Command Prompt run as
Administrator — match that.

**Critical context: this is a FIRST-TIME real-hardware test, not a
re-test.** The hardware driver code in `api/game_manager.py`
(`_hw_init()`, `USE_SERIAL_HD`, the per-frame `led.led_control` calls)
has never been run against a physical LED floor before. It was written
by analogy from other games' (led-hoops, led-climb) real hardware
findings, not validated on this game's own hardware. Do not assume
anything works just because it's similar to another game's setup —
verify every step for real, and be more careful/thorough than you would
be re-confirming already-known-working code. If anything looks wrong,
don't paper over it or assume it's fine — stop and report the specific
discrepancy.

## Step-by-step

1. **Read these three files in this exact order before doing anything
   else:**
   - `ONSITE.md` — single-machine setup: extracting the zip, checking
     Python, installing deps, verifying the shelve config and COM ports,
     running `games/test_hardware.py`, starting the 3 services (API,
     `ws_bridge.py`, frontend).
   - `ONSITE_LAN_INTEGRATION_PLAN.md` — cross-machine network setup:
     static IP, firewall rule for this machine's API port (8001),
     `frontend/.env` pointing at the RFID machine. Only relevant once
     this machine needs to talk to the other 5 — you can do single-machine
     hardware validation before this is fully done, but don't skip it if
     RFID login is part of what you're testing.
   - `HARDWARE_VALIDATION.md` — what "hardware integration" means for
     this specific game (grid size, COM port count, the `USE_SERIAL_HD`
     mechanism, a known gap around wall/screen lights not being wired to
     hardware yet), the fact that none of it has been validated before,
     and the concrete onsite checklist you need to run.

2. **Execute `ONSITE.md`'s setup steps** (Python check, `pip install -r
   requirements.txt`, verify the `led_parameter` shelve, verify COM ports
   are visible in Device Manager, `npm install` for the frontend). Do not
   touch the RFID server, SQL server, or any other service already
   running on this PC — `ONSITE.md` calls this out explicitly.

3. **Run the hardware checklist from `HARDWARE_VALIDATION.md` section 3,
   carefully and in order.** Specifically:
   - Run `games/test_hardware.py` and confirm floor lights green + sensor
     presses register.
   - Verify the full 6×16 grid maps correctly to physical positions —
     check for row/col offset, mirroring, or transposition (these are
     common first-time hardware bring-up bugs and would NOT have been
     caught by simulator-only testing, since the simulator has no
     physical orientation to get wrong).
   - Start the full stack with `USE_SERIAL_HD=1` and confirm the log
     line `Hardware ready: N port(s), 6×16, layout=X` appears (not
     `Hardware init failed`).
   - Play one full marathon session end-to-end on the real floor (not
     just one level) — login through natural session end.
   - Judge laser-beam hazard timing on the physical floor, not just by
     how it looked in the browser simulator during development — physical
     scale and any serial latency can make timing feel different even if
     the code is unchanged.
   - Confirm the blank-on-stop fix (new in this pass) actually blanks the
     physical floor at all 4 end paths: timeout, life-exhausted, manual
     `/logout`, and starting a new game over a stale one.
   - Check whether wall lights are expected to work at all before
     treating a dark wall perimeter as a bug — see the known-gap note in
     `HARDWARE_VALIDATION.md` section 1.

   If something doesn't match how it behaved in the simulator, consult
   `HARDWARE_VALIDATION.md` section 4's troubleshooting mini-section
   (COM port ordering, row/col transposition, off-by-one indexing) before
   assuming the game logic itself is broken — first-time hardware bugs
   are very often a shelve config or wiring mismatch, not a code bug.

4. **Report back pass/fail for every checklist item, with specific
   detail — not vague summaries.** The person reading your report may
   need to debug remotely without being on-site, so:
   - Bad: "some tiles didn't light up."
   - Good: "row 3 col 5 and row 3 col 6 didn't light during the
     single-tile test in checklist 3.4; all other tiles in that pattern
     test lit correctly. Grid otherwise appears correctly oriented (row 0
     confirmed at the entrance edge, col 0 confirmed at the left edge)."
   - Bad: "hardware mode works."
   - Good: "USE_SERIAL_HD=1 startup logged 'Hardware ready: 1 port(s),
     6x16, layout=5'; test_hardware.py lit all 96 floor tiles green and
     registered PRESS on 4/4 tiles stepped on; ran one full marathon
     session (level sequence: A001→A004, cleared 3/4, ended on timeout)
     with no HW I/O errors in logs/api.log."
   - For any FAIL, include: which checklist item, exact command run,
     exact output/log line, and what you expected instead.
   - Explicitly call out the wall-light status (working / not working /
     not expected to work per venue owner) since that's a known open
     question, not an assumed-working feature.

Do not modify `led_parameter` (the shelve) or any other game's repo. Do
not commit anything unless explicitly asked to. Do not skip Step 1 —
guessing at the setup instead of reading `ONSITE.md` and
`HARDWARE_VALIDATION.md` first risks missing the known wall-light gap and
re-discovering already-documented issues from scratch.
