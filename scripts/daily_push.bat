@echo off
chcp 65001 >nul
REM 财经日历每日推送 —— 供 Windows 计划任务调用
setlocal
set "PROJ=%~dp0.."
set "PY=C:\Users\Gk319\.workbuddy\binaries\python\versions\3.13.12\python.exe"
if not exist "%PY%" set "PY=python"
if not exist "%PROJ%\logs" mkdir "%PROJ%\logs"
cd /d "%PROJ%"
"%PY%" run.py push >> "%PROJ%\logs\push.log" 2>&1
exit /b %ERRORLEVEL%
