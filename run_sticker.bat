@echo off
chcp 65001 >nul
title IP Quick Switcher - Sticker
python "%~dp0sticker.py"
if errorlevel 1 (
    echo.
    echo Failed to start. Make sure Python is installed and added to PATH.
    pause
)
