#!/bin/zsh
# Script para inicializar un álbum (Fase 1)

# Obtener la ruta absoluta del directorio donde reside este script
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Activar el entorno virtual
if [ -d ".venv" ]; then
    source .venv/bin/activate
else
    echo "Error: No se encontró la carpeta .venv en $SCRIPT_DIR."
    echo "Por favor, crea el entorno virtual ejecutando: python3.13 -m venv .venv"
    exit 1
fi

# Verificar si se pasó un argumento
if [ $# -eq 0 ]; then
    echo "Uso: $0 /ruta/a/directorio_de_fotos"
    exit 1
fi

# Ejecutar el proceso init
python3 make_album.py --init "$1"
