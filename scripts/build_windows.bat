@echo off
setlocal

REM Build wagom-player using PyInstaller spec; robust path handling

set SCRIPT_DIR=%~dp0
pushd "%SCRIPT_DIR%.." >nul

python -c "import PyInstaller" 1>nul 2>nul
if errorlevel 1 (
  echo [!] PyInstaller not found. Run: pip install pyinstaller
  popd >nul & endlocal & exit /b 1
)

set SPEC=wagom-player.spec
if not exist "%SPEC%" (
  echo [!] Spec file not found: %CD%\%SPEC%
  popd >nul & endlocal & exit /b 1
)

REM Generate ICO from SVG (requires PyQt5.QtSvg)
python scripts\make_ico.py
if errorlevel 1 (
  echo [!] ICO generation failed. Ensure PyQt5 is installed.
  popd >nul & endlocal & exit /b 1
)

REM Do not force-kill the player during builds. A running app can hold dist locks.
tasklist /FI "IMAGENAME eq wagom-player.exe" 2>nul | findstr /I /C:"wagom-player.exe" >nul
if not errorlevel 1 (
  echo [!] wagom-player.exe is running. Close it before building.
  popd >nul & endlocal & exit /b 1
)

REM Clean previous dist/build to prevent access denied on overwrite
if exist dist\wagom-player (
  rmdir /S /Q dist\wagom-player 2>nul
)
if exist build (
  rmdir /S /Q build 2>nul
)

python -m PyInstaller -y "%CD%\%SPEC%"
if errorlevel 1 (
  echo [!] Build failed
  popd >nul & endlocal & exit /b 1
)

echo.
echo [i] Output: dist\wagom-player\wagom-player.exe
echo [i] VLC (libvlc) must be installed on the system.
echo.

popd >nul
endlocal
