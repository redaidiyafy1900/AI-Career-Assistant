@echo off
title AI Career Assistant

echo ========================================
echo   AI Career Assistant
echo ========================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    py --version >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Python not found
        echo Please install Python 3.8 or higher
        pause
        exit
    )
    set PY=py
) else (
    set PY=python
)

echo [OK] Python:
%PY% --version
echo.

REM Check dependencies
echo [1/3] Checking dependencies...
%PY% -c "import flask" >nul 2>&1
if errorlevel 1 (
    echo   Installing dependencies...
    %PY% -m pip install flask flask-cors requests python-dotenv -i https://pypi.tuna.tsinghua.edu.cn/simple
)
echo   Dependencies OK

REM Check config
echo.
echo [2/3] Checking config...
if not exist ".env" (
    echo # Config > .env
    echo PORT=3002 >> .env
)
echo   Config OK

REM Check directories
echo.
echo [3/3] Checking directories...
if not exist "backend\uploads" mkdir "backend\uploads"
if not exist "backend\storage" mkdir "backend\storage"
echo   Directories OK

REM Start server
echo.
echo ========================================
echo   Starting server...
echo ========================================
echo.
echo URL: http://localhost:3002
echo.

start "" http://localhost:3002/index.html

%PY% server.py

echo.
echo Server stopped
pause
