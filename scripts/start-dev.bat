@echo off
REM Start Laser dev stack (API 8001, ws_bridge 8768, UI 5174).
setlocal
cd /d "%~dp0.."

echo ==^> LED Laser dev stack from %CD%

start "LED Laser API" cmd /k "cd /d %CD% && set USE_SERIAL_HD=1 && python -m uvicorn api.main:app --host 0.0.0.0 --port 8001"
timeout /t 2 /nobreak >nul
start "LED Laser ws_bridge" cmd /k "cd /d %CD% && set API_PORT=8001 && set WS_BRIDGE_PORT=8768 && python ws_bridge.py"
timeout /t 2 /nobreak >nul
start "LED Laser Frontend" cmd /k "cd /d %CD%\frontend && npm run dev"

echo.
echo Laser ready:
echo   UI:        http://localhost:5174
echo   API:       http://localhost:8001
echo   ws_bridge: http://localhost:8768
echo.
echo Close the three command windows to stop the stack.
endlocal
