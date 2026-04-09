#!/bin/zsh

# ==============================================================================
# edit_album.sh
# Interactive page editor launcher
# ==============================================================================
# Usage: ./edit_album.sh /ruta/al/workspace_album
#
# Launches the Flask-based interactive editor for editing album pages.
# Opens a web browser interface for:
#   - Reordering photos via drag-and-drop
#   - Deleting photos or entire pages
#   - Editing page titles
#   - Regenerating page previews
#   - Navigating between pages
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PATH="$SCRIPT_DIR/.venv"

# Validate workspace argument
if [ $# -eq 0 ]; then
    echo "❌ Error: No se especificó workspace"
    echo ""
    echo "Uso: $0 /ruta/al/workspace_album"
    echo ""
    echo "Ejemplo:"
    echo "  $0 /Users/jzabalegui/Pictures/Ano_2026_album"
    exit 1
fi

WORKSPACE="$1"

# Validate workspace exists
if [ ! -d "$WORKSPACE" ]; then
    echo "❌ Error: El workspace no existe: $WORKSPACE"
    exit 1
fi

# Validate it's a valid workspace (has global_config.yaml)
if [ ! -f "$WORKSPACE/global_config.yaml" ]; then
    echo "❌ Error: No es un workspace válido (falta global_config.yaml)"
    echo "   Path: $WORKSPACE"
    echo ""
    echo "Ejecuta --init primero para crear el workspace"
    exit 1
fi

# Validate virtual environment
if [ ! -f "$VENV_PATH/bin/activate" ]; then
    echo "❌ Error: Entorno virtual no encontrado"
    echo "   Path: $VENV_PATH"
    echo ""
    echo "Crea el entorno virtual:"
    echo "  cd '$SCRIPT_DIR'"
    echo "  python3.13 -m venv .venv"
    echo "  source .venv/bin/activate"
    echo "  pip install -r requirements.txt"
    exit 1
fi

# Activate virtual environment
source "$VENV_PATH/bin/activate"

# Change to project directory
cd "$SCRIPT_DIR"

# Launch editor
echo "🚀 Iniciando editor interactivo..."
echo ""
python3 make_album.py --edit "$WORKSPACE"
