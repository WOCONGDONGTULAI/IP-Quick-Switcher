@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo   IP 快速切换器 - 发布新版本
echo   规则：纯数字递增，数字最大即最新版
echo ============================================
echo.

python release.py --dry-run
if errorlevel 1 goto fail

echo.
set /p CONFIRM=确认发布以上版本？[Y/N]
if /i not "%CONFIRM%"=="Y" (
    echo 已取消。
    pause
    exit /b 0
)

python release.py
if errorlevel 1 goto fail

pause
exit /b 0

:fail
echo.
echo [ERROR] 发布失败。请确认已安装 gh 并执行过 gh auth login。
pause
exit /b 1
