@echo off
setlocal

REM Build wagom-player using the PyInstaller spec (no line continuations)

where pyinstaller >nul 2>nul
if errorlevel 1 (
  echo [!] PyInstaller not found. Run: pip install pyinstaller
  exit /b 1
)

set SPEC=wagom-player.spec
if not exist "%SPEC%" (
  echo [!] Spec file not found: %SPEC%
  exit /b 1
)

REM Generate ICO from SVG (requires PyQt5.QtSvg)
python scripts\make_ico.py
if errorlevel 1 (
  echo [!] ICO generation failed. Ensure PyQt5 is installed.
  exit /b 1
)

pyinstaller -y "%SPEC%"
if errorlevel 1 (
  echo [!] Build failed
  exit /b 1
)

echo.
echo [i] Output: dist\wagom-player\wagom-player.exe
echo [i] VLC (libvlc) must be installed on the system.
echo.
endlocal
