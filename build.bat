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

echo [3/3] Building main app...
if exist version_info.txt (
    python -m PyInstaller --noconfirm --clean --onefile --name "IPSwitcher" --uac-admin --version-file version_info.txt app.py
) else (
    python -m PyInstaller --noconfirm --clean --onefile --name "IPSwitcher" --uac-admin app.py
)
if errorlevel 1 python -m PyInstaller --noconfirm --clean --onefile --name "IPSwitcher" --uac-admin app.py
if errorlevel 1 (
    echo [ERROR] Main app build failed.
    pause
    exit /b 1
)

echo [+] Building desktop sticker...
if exist version_info.txt (
    python -m PyInstaller --noconfirm --clean --onefile --name "IPSwitcherSticker" --uac-admin --version-file version_info.txt sticker.py
) else (
    python -m PyInstaller --noconfirm --clean --onefile --name "IPSwitcherSticker" --uac-admin sticker.py
)
if errorlevel 1 python -m PyInstaller --noconfirm --clean --onefile --name "IPSwitcherSticker" --uac-admin sticker.py
if errorlevel 1 (
    echo [ERROR] Sticker build failed.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   Done!
echo     dist\IPSwitcher.exe         完整管理界面
echo     dist\IPSwitcherSticker.exe  桌面贴纸悬浮窗
echo ============================================
echo.
pause
