#!/bin/bash

# Test launcher for the unified app on a different port

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ ! -d "$SCRIPT_DIR/.venv" ]; then
    echo "❌ Error: Virtual environment not found"
    exit 1
fi

source "$SCRIPT_DIR/.venv/bin/activate"

cd "$SCRIPT_DIR"

echo "🚀 Iniciando app en puerto 5051 (test)..."
echo "🌐 URL: http://localhost:5051"
echo ""

# Run with different port by modifying launch_app to accept port parameter
python -c "
from src.editor.app import app
import webbrowser

print('🎯 App iniciada sin WORKSPACE/SOURCE configurado')
print('📋 Debería mostrar launcher.html')
print('')

webbrowser.open('http://localhost:5051')
app.run(host='localhost', port=5051, debug=False)
"
