@echo off
echo Starting server...
echo.

python server.py

if errorlevel 1 (
    echo.
    echo Error: Python not found
    echo Please install Python 3.11+
    echo.
)

pause
