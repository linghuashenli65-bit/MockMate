@echo off
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8

echo ============================================
echo         MockMate v1.0
echo         AI Interview Coach
echo ============================================
echo.
REM 杀掉上次残留的 MockMate 进程
for /f "tokens=5" %%a in ('netstat -ano ^| find ":18633" ^| find "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
    timeout /t 1 /nobreak >nul
)

echo Starting server...

if exist "C:\ProgramData\anaconda3\python.exe" (
    "C:\ProgramData\anaconda3\python.exe" run.py
) else (
    python run.py
)

if errorlevel 1 (
    echo.
    echo [ERROR] Server exited with code: %errorlevel%
    echo Check log: backend\data\mockmate.log
    echo.
) else (
    echo.
    echo Server stopped.
    echo.
)

pause
