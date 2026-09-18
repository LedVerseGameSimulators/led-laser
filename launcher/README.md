# LED Laser launcher

Build the operator `LED Laser.exe` on Windows with PyInstaller:

```bat
pip install pyinstaller
pyinstaller launcher/LED_Laser.spec --noconfirm
```

The executable is written to `dist/LED Laser.exe`. Place it next to `START_GAME.bat` in the release folder (or use the GitHub Actions `Package Windows` workflow on a `v*` tag).
