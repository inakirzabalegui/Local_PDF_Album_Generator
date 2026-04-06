#!/bin/zsh
# Script para renderizar un álbum (Fase 2)
# 
# Uso:
#   ./render_album.sh /ruta/al/workspace                    # Renderizar todo
#   ./render_album.sh /ruta/al/workspace --from 5 --to 10   # Renderizar páginas 5-10
#   ./render_album.sh /ruta/al/workspace --from 0 --to 0    # Solo portada

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
    echo "Uso: $0 /ruta/a/directorio_del_proyecto_album [--from N] [--to N]"
    echo ""
    echo "Ejemplos:"
    echo "  $0 ~/Fotos/viaje_album"
    echo "  $0 ~/Fotos/viaje_album --from 5 --to 10"
    echo "  $0 ~/Fotos/viaje_album --from 0 --to 0"
    exit 1
fi

# Pasar el primer argumento como ruta, y el resto como parámetros opcionales
PROJECT_PATH="$1"
shift  # Eliminar el primer argumento

# Ejecutar el proceso render con parámetros opcionales
python3 make_album.py --render "$PROJECT_PATH" $@
