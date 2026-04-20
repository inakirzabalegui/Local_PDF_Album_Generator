#!/bin/bash

# Local PDF Album Generator - Unified App Launcher
# Launches the interactive web app with Fuente and Edición modes

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Check if virtual environment exists
if [ ! -d "$SCRIPT_DIR/.venv" ]; then
    echo "❌ Error: Virtual environment not found at $SCRIPT_DIR/.venv"
    echo "Please run: python3.13 -m venv .venv"
    exit 1
fi

# Kill any existing server on port 5050 so we always start fresh
EXISTING_PID=$(lsof -ti :5050 2>/dev/null)
if [ -n "$EXISTING_PID" ]; then
    echo "🔄 Deteniendo servidor anterior (PID $EXISTING_PID)..."
    kill -9 $EXISTING_PID 2>/dev/null || true
    sleep 1
fi

# Activate virtual environment
source "$SCRIPT_DIR/.venv/bin/activate"

echo "🚀 Iniciando aplicación unificada..."
echo "🌐 URL: http://localhost:5050"
echo ""
echo "Presiona Ctrl+C para detener el servidor"
echo ""

cd "$SCRIPT_DIR"
python make_album.py --app
