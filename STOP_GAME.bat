@echo off
setlocal EnableExtensions
title LED Laser Shutdown
cd /d "%~dp0"

set "QUIET=%~1"
if /i not "%QUIET%"=="/quiet" (
  echo.
  echo ==========================================
  echo           LED LASER - STOP GAME
  echo ==========================================
  echo.
  echo Ending the active game and blanking the floor...
)

REM Ask the API to stop cleanly first so physical LEDs get a black frame.
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $a=Invoke-RestMethod 'http://localhost:8001/active-game' -TimeoutSec 2; if ($a.success) { $body=@{card_id=$a.card_id;game_id=$a.game_id}|ConvertTo-Json -Compress; Invoke-RestMethod -Method Post -Uri 'http://localhost:8001/logout' -ContentType 'application/json' -Body $body -TimeoutSec 4 | Out-Null } } catch {}" >nul 2>&1
timeout /t 1 /nobreak >nul

echo Stopping floor engine, bridge, and interface...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ports=8001,8768,5174; Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $ports -contains $_.LocalPort } | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }" >nul 2>&1
taskkill /FI "WINDOWTITLE eq LED Laser API*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq LED Laser Bridge*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq LED Laser UI*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq LED Laser Frontend*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq LED Laser ws_bridge*" /T /F >nul 2>&1

if /i "%QUIET%"=="/quiet" (
  endlocal
  exit /b 0
)

echo.
echo LED Laser has stopped.
timeout /t 2 /nobreak >nul
exit /b 0
