@echo off
chcp 65001 >nul
title IP Quick Switcher - Build

echo ============================================
echo   IP Quick Switcher - Build to exe
echo ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] python not found. Install Python and tick "Add to PATH".
    pause
    exit /b 1
)

echo [1/3] Installing dependencies...
python -m pip install --upgrade pip -q
python -m pip install pyinstaller -q
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies. Check your network.
    pause
    exit /b 1
)

echo [2/3] Cleaning old build...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [3/3] Building...
if exist version_info.txt (
    python -m PyInstaller --noconfirm --clean --onefile --windowed --name "IPSwitcher" --uac-admin --version-file version_info.txt app.py
) else (
    python -m PyInstaller --noconfirm --clean --onefile --windowed --name "IPSwitcher" --uac-admin app.py
)

if errorlevel 1 (
    echo.
    echo [WARN] Build with version-info failed, retrying without it...
    python -m PyInstaller --noconfirm --clean --onefile --windowed --name "IPSwitcher" --uac-admin app.py
)

if errorlevel 1 (
    echo.
    echo [ERROR] Build failed.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   Done! Output: dist\IPSwitcher.exe
echo ============================================
echo.
pause
