@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "ROOT=%CD%"

if not defined ACTIVERSE_KIOSK set "ACTIVERSE_KIOSK=1"

title LED Laser Launcher
echo.
echo ==========================================
echo          LED LASER - START GAME
echo ==========================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
        set "PATH=%LOCALAPPDATA%\Programs\Python\Python311;%LOCALAPPDATA%\Programs\Python\Python311\Scripts;%PATH%"
    ) else (
        echo ERROR: Python 3.11 is not installed.
        echo Ask tech to install Python 3.11, then run SETUP_FIRST_TIME.bat.
        goto :failed
    )
)

where npm >nul 2>&1
if errorlevel 1 (
    echo ERROR: Node.js/npm is not installed.
    echo Ask tech to install Node.js LTS, then run SETUP_FIRST_TIME.bat.
    goto :failed
)

if not exist "games\setting\led_parameter.dat" (
    echo ERROR: games\setting\led_parameter.dat is missing.
    echo Ask tech to restore venue floor settings.
    goto :failed
)

echo Checking Python packages...
python -c "import fastapi, uvicorn, httpx, serial" >nul 2>&1
if errorlevel 1 (
    echo Installing required Python packages - first time...
    python -m pip install -r "api\requirements.txt"
    if errorlevel 1 goto :failed
)

if not exist "frontend\node_modules" (
    echo Installing frontend packages - first time, may take a few minutes...
    pushd "frontend"
    call npm install
    if errorlevel 1 (
        popd
        goto :failed
    )
    popd
)

if not exist "frontend\.env" (
    if exist "frontend\.env.example" (
        echo Creating frontend\.env from example - RFID address...
        copy /Y "frontend\.env.example" "frontend\.env" >nul
        echo EDIT frontend\.env if the RFID PC IP is not 192.168.1.106
    )
)

echo Stopping any previous LED Laser copy...
call "%ROOT%\STOP_GAME.bat" /quiet
ping -n 2 127.0.0.1 >nul

echo Starting floor engine (hardware mode)...
REM /MIN before title; no space before & after set value (avoids USE_SERIAL_HD=1[space])
start /min "LED Laser API" cmd.exe /k "cd /d %ROOT% & set USE_SERIAL_HD=1& python -m uvicorn api.main:app --host 0.0.0.0 --port 8001"
ping -n 4 127.0.0.1 >nul

echo Starting simulator bridge...
start /min "LED Laser Bridge" cmd.exe /k "cd /d %ROOT% & set API_PORT=8001& set WS_BRIDGE_PORT=8768& python ws_bridge.py"
ping -n 3 127.0.0.1 >nul

echo Starting operator interface...
set "WINDOW_TITLE_UI=LED Laser UI"
call "%ROOT%\scripts\kiosk\run-ui-prod.bat" 5174
if errorlevel 1 goto :failed
ping -n 5 127.0.0.1 >nul

echo Waiting for game UI...
set /a _tries=0

:wait_ui
set /a _tries+=1
powershell -NoProfile -Command "try { (Invoke-WebRequest -Uri 'http://127.0.0.1:5174/' -UseBasicParsing -TimeoutSec 2).StatusCode } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 goto ui_ready
if %_tries% GEQ 30 goto ui_timeout
ping -n 2 127.0.0.1 >nul
goto wait_ui

:ui_timeout
echo WARNING: UI did not respond yet. Opening browser anyway.
goto check_api

:ui_ready
echo UI is ready.

:check_api
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r=Invoke-WebRequest -UseBasicParsing 'http://localhost:8001/health' -TimeoutSec 3; if ($r.StatusCode -ne 200) { exit 1 } } catch { exit 1 }" >nul 2>&1
if errorlevel 1 (
    echo ERROR: The floor engine did not start.
    echo Check the minimized "LED Laser API" window for details.
    goto :failed
)

call "%ROOT%\scripts\kiosk\open-ui.bat" 5174 laser

echo.
echo ==========================================
echo   LED LASER is running (HARDWARE)
echo   Open:  http://127.0.0.1:5174/
echo   Ctrl+Shift+K exits fullscreen kiosk
echo   To stop: double-click STOP_GAME.bat
echo ==========================================
echo.
exit /b 0

:failed
echo.
echo START FAILED. See OPERATOR_GUIDE.md or ask tech.
if /i "%START_GAME_NONINTERACTIVE%"=="1" exit /b 1
pause
exit /b 1
