# Configuración de Quick Actions en macOS

Este documento explica cómo crear acciones rápidas en el Finder para ejecutar los comandos del generador de álbumes fotográficos desde el menú contextual con un clic derecho del ratón.

## Requisitos previos

- macOS (cualquier versión moderna)
- Automator (incluido en macOS, localizable en `/Applications`)
- Local PDF Album Generator instalado y configurado
- Entorno virtual Python creado (`.venv`)

## Crear Quick Actions

### Paso 1: Determinar la ruta absoluta del proyecto

Antes de empezar, identifica la ruta completa de tu carpeta del proyecto:

```bash
cd /Users/jzabalegui/Coding/Local_PDF_Album_Generator
pwd
```

Esta ruta (`/Users/jzabalegui/Coding/Local_PDF_Album_Generator`) se usará en los scripts que crearemos.

> **IMPORTANTE**: Si cambias de portátil o la ruta del proyecto cambia, **debes actualizar esta ruta en todos los scripts** de Automator.

---

## Quick Action 1: Inicializar Álbum (--init)

Crea una acción para inicializar álbumes a partir de carpetas de fotos.

### Crear la acción

1. **Abre Automator**
   - Spotlight: `Cmd + Space` → escribe "Automator" → Enter
   - O navega a `/Applications/Automator.app`

2. **Crear nuevo documento**
   - `File > New` o `Cmd + N`
   - Selecciona: **"Quick Action"** (Acción Rápida)

3. **Configurar entrada**
   - En la parte superior derecha, busca:
     - **"Workflow receives"**: selecciona `folders` (carpetas)
     - **"in"**: selecciona `Finder`
     - **"Image"**: selecciona un ícono (recomendado: carpeta o imagen)

4. **Añadir acción de shell**
   - En el panel izquierdo, busca: **"Run Shell Script"** (Ejecutar script de shell)
   - Arrastra al área de trabajo principal
   - Configura los siguientes valores:
     - **Shell**: `/bin/zsh`
     - **Pass input**: `as arguments`

5. **Copiar el script**

Borra el contenido por defecto y copia este script (reemplaza la ruta si es necesario):

> **RECOMENDACIÓN**: Este script abre Terminal automáticamente para mostrar el progreso en tiempo real. Si prefieres una versión silenciosa, usa los scripts antiguos al final de este documento.

```bash
#!/bin/zsh

# ============================================================================
# Quick Action: Inicializar Álbum (con Terminal visible)
# Función: Ejecuta --init en una carpeta de fotos desde el menú del Finder
# ============================================================================

REPO_PATH="/Users/jzabalegui/Coding/Local_PDF_Album_Generator"

# Crear script temporal
TEMP_SCRIPT=$(mktemp)

cat > "$TEMP_SCRIPT" << 'EOF'
#!/bin/zsh

REPO_PATH="$1"
FOLDER="$2"

# Validaciones
if [ ! -d "$REPO_PATH" ]; then
    echo "❌ Error: Ruta del proyecto no encontrada: $REPO_PATH"
    exit 1
fi

if [ ! -f "$REPO_PATH/.venv/bin/activate" ]; then
    echo "❌ Error: Entorno virtual no encontrado"
    echo "Ejecuta: cd '$REPO_PATH' && python3.13 -m venv .venv"
    exit 1
fi

# Activar entorno virtual
source "$REPO_PATH/.venv/bin/activate"
cd "$REPO_PATH"

folder_name=$(basename "$FOLDER")
echo ""
echo "📁 Procesando: $folder_name"
echo "🚀 Inicializando álbum..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

python3 make_album.py --init "$FOLDER"

if [ $? -eq 0 ]; then
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "✅ ¡Álbum inicializado correctamente!"
    echo ""
else
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "❌ Error al inicializar el álbum"
    echo ""
    exit 1
fi

echo "Presiona cualquier tecla para cerrar esta ventana..."
read -k 1
EOF

chmod +x "$TEMP_SCRIPT"

# Ejecutar en Terminal para cada carpeta
for folder in "$@"; do
    osascript << APPLESCRIPT
        tell application "Terminal"
            activate
            do script "bash '$TEMP_SCRIPT' '$REPO_PATH' '$folder'; rm '$TEMP_SCRIPT'"
        end tell
APPLESCRIPT
done
```

6. **Guardar la acción**
   - `Cmd + S` o `File > Save`
   - **Nombre**: `Inicializar Álbum PDF`
   - Se guardará automáticamente en `~/Library/Services/`
   - Haz clic en **"Save"**

---

## Quick Action 2: Renderizar Álbum (--render)

Crea una acción para renderizar/generar el PDF a partir de un workspace.

### Crear la acción

Repite los pasos 1-4 del Quick Action 1, pero en el paso 5, usa este script:

```bash
#!/bin/zsh

# ============================================================================
# Quick Action: Renderizar Álbum (con Terminal visible)
# Función: Ejecuta --render en un workspace desde el menú del Finder
# ============================================================================

REPO_PATH="/Users/jzabalegui/Coding/Local_PDF_Album_Generator"

# Crear script temporal
TEMP_SCRIPT=$(mktemp)

cat > "$TEMP_SCRIPT" << 'EOF'
#!/bin/zsh

REPO_PATH="$1"
FOLDER="$2"

# Validaciones
if [ ! -d "$REPO_PATH" ]; then
    echo "❌ Error: Ruta del proyecto no encontrada: $REPO_PATH"
    exit 1
fi

if [ ! -f "$REPO_PATH/.venv/bin/activate" ]; then
    echo "❌ Error: Entorno virtual no encontrado"
    echo "Ejecuta: cd '$REPO_PATH' && python3.13 -m venv .venv"
    exit 1
fi

# Activar entorno virtual
source "$REPO_PATH/.venv/bin/activate"
cd "$REPO_PATH"

folder_name=$(basename "$FOLDER")
echo ""
echo "📁 Workspace: $folder_name"
echo "🎨 Generando PDF..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

python3 make_album.py --render "$FOLDER"

if [ $? -eq 0 ]; then
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "✅ ¡PDF generado correctamente!"
    echo ""
else
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "❌ Error al renderizar el álbum"
    echo ""
    exit 1
fi

echo "Presiona cualquier tecla para cerrar esta ventana..."
read -k 1
EOF

chmod +x "$TEMP_SCRIPT"

# Ejecutar en Terminal para cada carpeta
for folder in "$@"; do
    osascript << APPLESCRIPT
        tell application "Terminal"
            activate
            do script "bash '$TEMP_SCRIPT' '$REPO_PATH' '$folder'; rm '$TEMP_SCRIPT'"
        end tell
APPLESCRIPT
done
```

Guarda como: **`Renderizar Álbum PDF`**

---

## Quick Action 3: Renderizar Página Única (--page)

Crea una acción para renderizar solo una página específica para testing rápido.

### Crear la acción

Repite los pasos 1-4 del Quick Action 1, pero en el paso 5, usa este script:

```bash
#!/bin/zsh

# ============================================================================
# Quick Action: Renderizar Página Única (con Terminal visible)
# Función: Ejecuta --render --page en una carpeta de página desde el Finder
# ============================================================================

REPO_PATH="/Users/jzabalegui/Coding/Local_PDF_Album_Generator"

# Crear script temporal
TEMP_SCRIPT=$(mktemp)

cat > "$TEMP_SCRIPT" << 'EOF'
#!/bin/zsh

REPO_PATH="$1"
PAGE_FOLDER="$2"

# Validaciones
if [ ! -d "$REPO_PATH" ]; then
    echo "❌ Error: Ruta del proyecto no encontrada: $REPO_PATH"
    exit 1
fi

if [ ! -f "$REPO_PATH/.venv/bin/activate" ]; then
    echo "❌ Error: Entorno virtual no encontrado"
    echo "Ejecuta: cd '$REPO_PATH' && python3.13 -m venv .venv"
    exit 1
fi

# Detectar el workspace (carpeta padre)
WORKSPACE=$(dirname "$PAGE_FOLDER")

# Activar entorno virtual
source "$REPO_PATH/.venv/bin/activate"
cd "$REPO_PATH"

page_name=$(basename "$PAGE_FOLDER")
echo ""
echo "📄 Página: $page_name"
echo "🎨 Renderizando página única..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

python3 make_album.py --render "$WORKSPACE" --page "$PAGE_FOLDER"

if [ $? -eq 0 ]; then
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "✅ ¡Página renderizada correctamente!"
    echo "📁 PDF: $PAGE_FOLDER/page_*.pdf"
    echo ""
else
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "❌ Error al renderizar la página"
    echo ""
    exit 1
fi

echo "Presiona cualquier tecla para cerrar esta ventana..."
read -k 1
EOF

chmod +x "$TEMP_SCRIPT"

# Ejecutar en Terminal para cada carpeta
for page_folder in "$@"; do
    osascript << APPLESCRIPT
        tell application "Terminal"
            activate
            do script "bash '$TEMP_SCRIPT' '$REPO_PATH' '$page_folder'; rm '$TEMP_SCRIPT'"
        end tell
APPLESCRIPT
done
```

Guarda como: **`Renderizar Página PDF`**

---

## Cómo usar las Quick Actions

Una vez creadas las acciones, puedes usarlas desde el Finder:

### Inicializar un álbum
1. En Finder, selecciona una carpeta con fotos originales
2. Haz clic derecho
3. Ve a **"Quick Actions"** (o "Servicios" en versiones antiguas)
4. Selecciona **"Inicializar Álbum PDF"**

### Renderizar un álbum completo
1. En Finder, selecciona el workspace (ej: `Año_2026_album`)
2. Haz clic derecho
3. Ve a **"Quick Actions"**
4. Selecciona **"Renderizar Álbum PDF"**

### Renderizar una sola página
1. En Finder, selecciona una carpeta de página (ej: `pagina_04_evento`)
2. Haz clic derecho
3. Ve a **"Quick Actions"**
4. Selecciona **"Renderizar Página PDF"**

---

## Solución de problemas

### No aparecen las Quick Actions en el menú

1. Abre **System Settings** (Preferencias del Sistema)
2. Ve a **Privacy & Security > Extensions** (Privacidad y Seguridad > Extensiones)
3. En la barra lateral, selecciona **"Finder"**
4. Marca las acciones que creaste

### Error: "Entorno virtual no encontrado"

Crea el entorno virtual:
```bash
cd /Users/jzabalegui/Coding/Local_PDF_Album_Generator
python3.13 -m venv .venv
```

### Error: "Ruta del proyecto no encontrada"

La ruta especificada en el script no existe. Actualiza `REPO_PATH` en todos los scripts:

```bash
# Encuentra la ruta correcta
cd /Users/jzabalegui/Coding/Local_PDF_Album_Generator
pwd
```

Luego edita cada Quick Action:
- Abre Automator
- File > Open Recent > selecciona la acción
- Actualiza la línea `REPO_PATH="/Users/..."`
- Guarda

---

## Cambio de portátil: Pasos para migrar

Si cambias de portátil, sigue estos pasos:

1. **Instala el proyecto** en la nueva máquina
2. **Crea el entorno virtual** en la nueva ubicación
3. **Abre Automator** en la nueva máquina
4. **Abre cada Quick Action**:
   - `File > Open Recent` o busca en `~/Library/Services/`
5. **Actualiza la ruta** `REPO_PATH` en cada script
6. **Guarda** cada acción

Alternativamente, **copia las acciones directamente**:
```bash
# En la nueva máquina, después de clonar el proyecto
cp ~/Library/Services/"Inicializar Álbum PDF.workflow" ~/Library/Services/ 2>/dev/null || true

# Luego edita cada una con Automator para actualizar la ruta
```

---

## Personalización adicional

### Cambiar el ícono de una Quick Action

1. Abre Automator
2. Abre la acción que quieres editar
3. En el panel de configuración superior, haz clic en el ícono actual
4. Selecciona uno nuevo o sube una imagen personalizada
5. Guarda

### Usar versión silenciosa (sin Terminal visible)

Si prefieres que los Quick Actions se ejecuten **sin mostrar Terminal** (solo con notificaciones), reemplaza los scripts anteriores con los siguientes.

#### Script silencioso para "Inicializar Álbum":

```bash
#!/bin/zsh

REPO_PATH="/Users/jzabalegui/Coding/Local_PDF_Album_Generator"

if [ ! -d "$REPO_PATH" ] || [ ! -f "$REPO_PATH/.venv/bin/activate" ]; then
    osascript -e 'display notification "Error de configuración" with title "PDF Album Generator"'
    exit 1
fi

source "$REPO_PATH/.venv/bin/activate"

for folder in "$@"; do
    cd "$REPO_PATH" || exit 1
    python3 make_album.py --init "$folder"
    
    if [ $? -eq 0 ]; then
        folder_name=$(basename "$folder")
        osascript -e 'display notification "✅ Álbum inicializado" with title "PDF Album Generator" subtitle "'"$folder_name"'"'
    else
        osascript -e 'display notification "❌ Error en la inicialización" with title "PDF Album Generator"'
    fi
done
```

#### Script silencioso para "Renderizar Álbum":

```bash
#!/bin/zsh

REPO_PATH="/Users/jzabalegui/Coding/Local_PDF_Album_Generator"

if [ ! -d "$REPO_PATH" ] || [ ! -f "$REPO_PATH/.venv/bin/activate" ]; then
    osascript -e 'display notification "Error de configuración" with title "PDF Album Generator"'
    exit 1
fi

source "$REPO_PATH/.venv/bin/activate"

for folder in "$@"; do
    cd "$REPO_PATH" || exit 1
    python3 make_album.py --render "$folder"
    
    if [ $? -eq 0 ]; then
        folder_name=$(basename "$folder")
        osascript -e 'display notification "✅ PDF generado" with title "PDF Album Generator" subtitle "'"$folder_name"'"'
    else
        osascript -e 'display notification "❌ Error en renderización" with title "PDF Album Generator"'
    fi
done
```

#### Script silencioso para "Renderizar Página":

```bash
#!/bin/zsh

REPO_PATH="/Users/jzabalegui/Coding/Local_PDF_Album_Generator"

if [ ! -d "$REPO_PATH" ] || [ ! -f "$REPO_PATH/.venv/bin/activate" ]; then
    osascript -e 'display notification "Error de configuración" with title "PDF Album Generator"'
    exit 1
fi

source "$REPO_PATH/.venv/bin/activate"

for page_folder in "$@"; do
    workspace=$(dirname "$page_folder")
    cd "$REPO_PATH" || exit 1
    python3 make_album.py --render "$workspace" --page "$page_folder"
    
    if [ $? -eq 0 ]; then
        folder_name=$(basename "$page_folder")
        osascript -e 'display notification "✅ Página renderizada" with title "PDF Album Generator" subtitle "'"$folder_name"'"'
    else
        osascript -e 'display notification "❌ Error en página" with title "PDF Album Generator"'
    fi
done
```

---

## Referencias

- [Documentación oficial: Automatizar tareas en macOS](https://support.apple.com/es-es/guide/automator/welcome/mac)
- [Documentación de Automator](https://support.apple.com/es-es/guide/automator/aut3f53e9a8/mac)
- [Local PDF Album Generator - Uso](./README.md#uso)
