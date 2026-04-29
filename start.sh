#!/bin/bash
# ========================================
#   AI Career Assistant - 启动脚本 (Linux/Mac)
# ========================================

set -e

echo "========================================"
echo "  AI Career Assistant"
echo "========================================"
echo ""

# 检查 Python
if ! command -v python3 &> /dev/null; then
    if ! command -v python &> /dev/null; then
        echo "[ERROR] Python not found. Please install Python 3.11+"
        exit 1
    fi
    PYTHON_CMD=python
else
    PYTHON_CMD=python3
fi

echo "[OK] Python:"
$PYTHON_CMD --version
echo ""

# 检查依赖
echo "[1/3] Checking dependencies..."
$PYTHON_CMD -c "import flask" > /dev/null 2>&1 || {
    echo "  Installing dependencies..."
    $PYTHON_CMD -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
}
echo "  Dependencies OK"

# 检查配置
echo ""
echo "[2/3] Checking config..."
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "  Config file created (.env)"
        echo "  Please edit .env and configure your API keys!"
    else
        echo "  Creating minimal .env..."
        echo "PORT=3002" > .env
    fi
fi
echo "  Config OK"

# 检查目录
echo ""
echo "[3/3] Checking directories..."
mkdir -p backend/uploads backend/storage data/tailored
echo "  Directories OK"

# 启动服务
echo ""
echo "========================================"
echo "  Starting server..."
echo "========================================"
echo ""
echo "URL: http://localhost:3002"
echo ""

# 尝试打开浏览器
if command -v open &> /dev/null; then
    open http://localhost:3002/index.html 2>/dev/null || true
elif command -v xdg-open &> /dev/null; then
    xdg-open http://localhost:3002/index.html 2>/dev/null || true
fi

$PYTHON_CMD server.py
