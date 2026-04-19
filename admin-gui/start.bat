@echo off
chcp 65001 >nul 2>&1
title Blog Admin

cd /d "%~dp0"

echo ============================================
echo   Blog Management Console
echo ============================================
echo.
echo   Starting Python server...
echo.

"C:\Users\Lenovo\AppData\Local\Programs\Python\Python313\python.exe" server.py

echo.
echo ============================================
echo   Server stopped or crashed!
echo   Error code: %ERRORLEVEL%
echo ============================================
pause
