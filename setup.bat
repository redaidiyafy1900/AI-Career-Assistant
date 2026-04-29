@echo off
echo.
echo ========================================
echo   AI Career Assistant Setup
echo ========================================
echo.

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    py --version >nul 2>&1
    if %errorlevel% neq 0 (
        echo Error: Python not found
        echo Please install Python 3.11+
        pause
        exit /b 1
    )
    set PYTHON_CMD=py
) else (
    set PYTHON_CMD=python
)

echo [1/3] Checking Python...
%PYTHON_CMD% --version
echo   Python OK
echo.

:: Upgrade pip
echo [2/3] Upgrading pip...
%PYTHON_CMD% -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple
echo   pip upgraded
echo.

:: Install dependencies
echo [3/3] Installing dependencies...
%PYTHON_CMD% -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
if %errorlevel% neq 0 (
    echo Error: Installation failed
    pause
    exit /b 1
)
echo   Dependencies installed
echo.

:: Create directories
if not exist backend\uploads mkdir backend\uploads
if not exist backend\storage mkdir backend\storage
echo   Directories created
echo.

:: Check .env file
if not exist .env (
    if exist .env.example (
        echo Creating config file...
        copy .env.example .env >nul
        echo   Config file created (.env)
        echo.
        echo NOTE:
        echo   Please edit .env file and configure:
        echo   - FastGPT API Key (for interview)
        echo   - Doubao API Key (for matching/optimization)
        echo.
    )
)

echo ========================================
echo   Setup Complete!
echo ========================================
echo.
echo Next steps:
echo   1. Edit .env file and add API keys
echo   2. Run start.bat to launch the project
echo   3. Visit http://localhost:3002
echo.
pause
