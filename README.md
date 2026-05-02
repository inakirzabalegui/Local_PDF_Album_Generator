# Local PDF Album Generator

Aplicación CLI local para macOS que automatiza la creación de álbumes fotográficos profesionales en PDF a partir de carpetas de imágenes. Motor de renderizado basado en estados (archivos YAML) con un flujo de trabajo en dos fases: **Creación** e **Impresión/Render**.

## Características

- **Escaneo recursivo** de directorios con subcarpetas (cada subcarpeta = un grupo/evento)
- **Títulos de sección automáticos con fecha**: extrae títulos desde nombres de subcarpetas (formato `YYYYMMDD_Nombre`) y los renderiza como `DD/MM/YYYY - Nombre` en el PDF
- **Agrupación estricta**: cada subcarpeta genera páginas independientes, nunca se mezclan fotos de dos carpetas en la misma página
- **Tres modos de layout**: `mesa_de_luz` (rotación +/-3°, jitter), `grid_compacto` (sin rotación, máxima densidad), `hibrido` (rotación sutil +/-1.5°, compacto)
- **Fotos maximizadas**: 6-9 fotos por página con márgenes de impresión seguros (29pt / 10mm, compatible con Peecho). Algoritmo de layout mejorado que intenta llenar máxima densidad vertical, detecta automáticamente 2×2 para grupos pequeños, soporta fotos en filas y columnas según orientación, y permite fotos destacadas/protagonistas en mosaico.
- **Sub-banners para subcarpetas hijas**: si una carpeta de sección contiene subcarpetas (1 nivel), se muestra un banner secundario más pequeño en la primera página donde aparecen esas fotos
- **Ordenación cronológica** por metadatos EXIF `DateTimeOriginal`, con fallback inteligente por fecha de carpeta
- **Downsampling optimizado** a 300 DPI con calidad 85% + redimensionado dinámico en PDF para minimizar el peso
- **Fondos dinámicos**: color dominante calculado automáticamente por página vía ColorThief (optimizado con miniaturas)
- **Portada profesional**: dos bandas con título del álbum (gruesa, primer tercio) y rango de fechas (fina, tercer tercio)
- **Contraportada**: center-crop a sangre completa
- **Carpetas especiales**: carpetas `portada/` y `contraportada/` (case-insensitive) permiten seleccionar fotos específicas para las cubiertas del álbum
- **Rebalanceo en cascada**: si mueves fotos entre carpetas manualmente, el sistema redistribuye automáticamente
- **Volúmenes múltiples**: divide el PDF en varios archivos si se excede el límite de páginas (por defecto 200 páginas)
- **Estado persistente en YAML**: seeds de layout para resultados reproducibles entre renders
- **Barra de progreso**: indicador visual durante la generación del PDF
- **Soporte UTF-8 completo**: renderizado correcto de tildes, ñ, y otros caracteres especiales en títulos y textos mediante fuentes TrueType
- **Renderizado parcial**: opción de generar solo un rango específico de páginas del álbum
- **Editor interactivo web**: interfaz visual para reordenar fotos (drag-and-drop), borrar elementos, editar títulos y previsualizar cambios en tiempo real

## Organización por secciones

El generador detecta automáticamente subcarpetas en el directorio de origen y las trata como "secciones" o eventos. Los nombres de subcarpeta se convierten en títulos visuales en el PDF.

### Formato de nombres de carpeta

Los nombres de subcarpetas deben tener un prefijo de fecha en formato `YYYYMMDD_` para mejor organización:

- `20260109_Comida_Despedida_Js` → Título: **"09/01/2026 - Comida despedida Js"**
- `20260112_Vacaciones_Verano` → Título: **"12/01/2026 - Vacaciones verano"**
- `20260315_Playa` → Título: **"15/03/2026 - Playa"**

Si una carpeta no tiene prefijo de fecha, se usa el nombre directamente:
- `Vacaciones_Verano` → Título: **"Vacaciones verano"**

El título se renderiza como overlay flotante semi-transparente en la parte superior de la página. **Importante**: cada subcarpeta genera sus propias páginas, nunca se mezclan fotos de dos carpetas en la misma página.

### Subcarpetas hijas (sub-banners)

Si una carpeta de sección contiene subcarpetas hijas (un nivel de profundidad), las fotos de esas subcarpetas reciben un **banner secundario más pequeño** (10pt, barra fina) debajo del banner principal. Este sub-banner aparece solo en la **primera página** donde las fotos de esa subcarpeta empiezan. Las fotos de diferentes subcarpetas hijas pueden mezclarse en la misma página.

Las fotos directamente en la carpeta padre (sin subcarpeta) no llevan sub-banner.

### Carpetas especiales para portada y contraportada

Puedes controlar qué fotos se usan para la **portada** y **contraportada** del álbum creando carpetas especiales en el directorio de origen:

- **`portada/` o `Portada/` o `PORTADA/`** (case-insensitive): Si existe esta carpeta, se seleccionará una foto aleatoria de ella para la portada del álbum.
- **`contraportada/` o `Contraportada/` o `CONTRAPORTADA/`** (case-insensitive): Si existe esta carpeta, se seleccionará una foto aleatoria de ella para la contraportada del álbum.

**Características:**
- Las carpetas son detectadas de forma **case-insensitive** (puedes usar cualquier combinación de mayúsculas/minúsculas).
- Si una carpeta especial contiene **múltiples fotos**, se selecciona una **aleatoriamente**.
- Las fotos de estas carpetas **NO aparecen** en las páginas de contenido del álbum (están excluidas del procesamiento normal).
- Si las carpetas no existen o están vacías, el sistema usa el **comportamiento por defecto**: primera foto para portada, última foto para contraportada.
- El sistema **informa en consola** qué fotos se están usando durante el proceso `--init`.

**Importante:** Estas carpetas deben estar en el **nivel raíz** del directorio de origen, no dentro de subcarpetas de eventos.

### Ejemplo de estructura de origen

```
mis_fotos/
├── portada/                     ← carpeta especial para portada
│   ├── cover_01.jpg             ← se selecciona una aleatoriamente
│   └── cover_02.jpg
├── contraportada/               ← carpeta especial para contraportada
│   └── back_01.jpg              ← foto para contraportada
├── 20260109_Comida_Despedida_Js/
│   ├── IMG_001.jpg
│   └── IMG_002.jpg
├── 20260212_EEUU_LA_SanDiego_con_js/
│   ├── IMG_010.jpg              ← fotos sueltas (sin sub-banner)
│   ├── IMG_011.jpg
│   ├── Los_Angeles_City/        ← sub-banner: "Los Angeles City"
│   │   ├── IMG_020.jpg
│   │   └── IMG_021.jpg
│   └── San_Diego_Beach/         ← sub-banner: "San Diego Beach"
│       ├── IMG_030.jpg
│       └── IMG_031.jpg
└── 20260315_Playa/
    ├── IMG_005.jpg
    └── IMG_006.jpg
```

El título del álbum completo se deriva del nombre de la carpeta raíz (`mis_fotos` → **"Mis fotos"**) y aparece en la **banda gruesa** de la portada (primer tercio). El **rango de fechas** (ej. `"09/01/2026 - 15/03/2026"`) se calcula automáticamente y aparece en la **banda fina** (tercer tercio) de la portada.

## Requisitos

- **macOS** (desarrollado y probado en macOS)
- **Python 3.13+**

## Instalación

### 1. Clonar o descargar el proyecto

```bash
cd ~/Coding
git clone <URL_DEL_REPOSITORIO> Local_PDF_Album_Generator
cd Local_PDF_Album_Generator
```

**Inicializar el repositorio git (si no tienes remoto configurado):**

```bash
git config user.name "Your Name"
git config user.email "your.email@example.com"
# El repositorio ya tiene .git si fue clonado
```

### 2. Crear el entorno virtual

Todos los comandos deben ejecutarse con el entorno virtual activado. Usamos `.venv` como convención.

```bash
# Crear el entorno virtual (una sola vez)
python3.13 -m venv .venv

# Activar el entorno virtual (cada vez que abras una terminal nueva)
source .venv/bin/activate
# En Windows: .venv\Scripts\activate
```

**Verificar que el entorno está activado:**

```bash
which python  # Debe mostrar: .../Local_PDF_Album_Generator/.venv/bin/python
# Si no ves .venv en la ruta, ejecuta: source .venv/bin/activate
```

### 3. Instalar dependencias

```bash
# Con el entorno activado:
pip install -r requirements.txt
```

### 4. Guardar cambios en git

Después de cambios locales en el código:

```bash
# Ver estado
git status

# Agregar cambios
git add .

# Hacer commit
git commit -m "Descripción breve del cambio"

# (Opcional) Subir a remoto
git push origin main
```

## Uso

**Importante:** La aplicación se ejecuta siempre desde la raíz del proyecto (`Local_PDF_Album_Generator/`) con el entorno virtual activado.

**Activar entorno si no está activo:**

```bash
cd ~/Coding/Local_PDF_Album_Generator
source .venv/bin/activate
```

### Nuevo: Modo Aplicación Unificada (`--app`)

**La forma recomendada de trabajar** es usar el nuevo modo aplicación que integra las funcionalidades de Fuente y Edición en una interfaz unificada:

```bash
./app_album.sh
```

O si prefieres el comando directo:

```bash
python make_album.py --app
```

Esto abre una aplicación web con dos pestañas:

1. **Pestaña "Fuente"**: Administra las carpetas de fotos originales
   - Navega por los eventos (subcarpetas de fotos)
   - Visualiza fotos directamente desde el disco
   - Renombra eventos (y renumera automáticamente todas las fotos)
   - Borra fotos o eventos completos
   - Regenera el workspace del álbum desde cero

2. **Pestaña "Edición"**: Edita el álbum generado
   - Reordena fotos dentro de páginas (drag-and-drop)
   - Mueve fotos entre páginas
   - Borra fotos o páginas completas
   - Edita títulos de página
   - Elige el modo de layout para cada página (`mesa_de_luz`, `grid_compacto`, `hibrido`)
   - Añade subtítulos a fotos
   - Visualiza preview en PDF de cada página

**Flujo recomendado:**
1. Ejecuta `python make_album.py --app` o `./app_album.sh`
2. Pulsa "Abrir Carpeta" y selecciona tu directorio de fotos
3. El app detecta si existe workspace `_album` hermano; si no, lo crea
4. Usa la pestaña "Fuente" para organizar eventos y fotos si es necesario
5. Usa la pestaña "Edición" para ajustar el álbum visual
6. Finaliza con `python make_album.py --render /ruta/a/workspace` para generar el PDF final

**Características de persistencia y navegación:**

- **Último álbum recordado**: La aplicación guarda la última carpeta abierta en `localStorage`. Al volver a cargar la launcher, aparecerá un botón "⏱️ Abrir último: [nombre_carpeta]" para reabrirlo rápidamente sin navegar de nuevo por el sistema de ficheros.

- **Cambiar de álbum sin reiniciar**: Desde la interfaz unificada (con las pestañas Fuente/Edición), puedes pulsar el botón "📁 Abrir carpeta" en la esquina superior derecha de la barra de herramientas. Esto te permitirá seleccionar una carpeta diferente sin cerrar la aplicación. Si hay cambios pendientes, te pedirá confirmación antes de descartar.

- **Limpieza de servidor al reiniciar**: El script `./app_album.sh` mata automáticamente cualquier proceso anterior escuchando en puerto 5050 antes de iniciar el servidor Flask, evitando conflictos de puerto y asegurando que siempre cargas la versión más actual del código.

### Modo Configuración por defecto

Antes de usar la aplicación, puedes editar los parámetros por defecto en el archivo [`global_config_default.yaml`](global_config_default.yaml) en la raíz del proyecto. Estos parámetros se aplicarán a **todos los nuevos** álbumes creados con `--init`:

```yaml
page_size: "A4"                        # Tamaño de página
target_resolution_dpi: 300             # Resolución objetivo (DPI)
photos_per_page_min: 6                 # Mínimo de fotos por página
photos_per_page_max: 9                 # Máximo de fotos por página
max_pages_per_volume: 200              # Máximo de páginas por PDF
default_background_color: "#0000FF"    # Color de fondo por defecto (RGB hex)
typography_system_font: "Helvetica"    # Tipografía para títulos
```

Cada álbum individual puede sobrescribir estos valores editando su propio `global_config.yaml` dentro del workspace después de crearlo.

### Activar el entorno virtual

```bash
cd ~/Coding/Local_PDF_Album_Generator
source .venv/bin/activate
```

### Inspeccionar el algoritmo de layout (pruebas)

Para verificar visualmente cómo el nuevo algoritmo de layout maneja diferentes cantidades de fotos, ejecuta el script de vista previa:

```bash
python scripts/preview_layouts.py
```

Esto genera un PDF con varias páginas de prueba (`scripts/preview_layouts/layout_previews.pdf`) mostrando cómo se distribuyen 3, 4, 5, 6, 7, 8 y 9 fotos con diferentes orientaciones. Abre el PDF para inspeccionar visualmente si el espaciado y llenado son los deseados.

**Qué esperar:**
- 3 fotos: Layout compacto (posiblemente 2×2 centrado)
- 5–6 fotos: 2–3 filas naturales que llenan verticalmente
- 7–9 fotos: Múltiples filas densas (sin fila única ni espacios grandes)
- Fotos verticales: Columnas densas o multi-filas según orientaciones

### Fase 1: Creación del workspace (`--init`)

Escanea un directorio de fotos, crea la estructura de páginas y genera los archivos YAML de estado.

Puedes usar el comando directo o el script simplificado:

**Comando directo:**
```bash
python make_album.py --init /ruta/a/mis_fotos
```

**Script simplificado:**
```bash
./init_album.sh /ruta/a/mis_fotos
```

**Ejemplo:**
```bash
./init_album.sh ~/Fotos/viaje_italia
```

Esto genera el workspace `~/Fotos/viaje_italia_album/` con la siguiente estructura:

```
viaje_italia_album/
├── global_config.yaml          # Configuración global del álbum
├── portada/
│   ├── cover.jpg               # Primera imagen (center-crop a sangre)
│   └── page_config.yaml
├── pagina_01_roma/
│   ├── img_001.jpg … img_008.jpg  (6-10 fotos)
│   └── page_config.yaml        # Incluye section_titles: ["12/01/2026 - Roma"]
├── pagina_02_roma/
│   ├── img_001.jpg … img_006.jpg
│   └── page_config.yaml        # layout_mode: "hibrido"
├── pagina_03_florencia/
│   ├── img_001.jpg … img_010.jpg
│   └── page_config.yaml        # layout_mode: "grid_compacto"
├── …
└── contraportada/
    ├── backcover.jpg           # Última imagen
    └── page_config.yaml
```

**Nota**: Los nombres de carpeta incluyen el slug de la sección para facilitar la identificación. Cada subcarpeta de origen genera páginas exclusivas.

### Intervención manual (opcional)

Después de `--init`, puedes **mover, añadir o borrar fotos** de las subcarpetas de página e incluso **eliminar carpetas/páginas completas**. Al ejecutar `--render`, el sistema:

1. **Reconcilia** el workspace: detecta carpetas o fotos borradas, redistribuye las fotos restantes de cada sección equitativamente en el número mínimo de páginas necesario, elimina carpetas vacías, renumera y renombra las carpetas físicamente en disco.
2. **Rebalancea** si alguna página queda fuera de los límites min/max de fotos.
3. **Genera** el PDF final.

El `layout_mode` y `layout_seed` de las páginas existentes se conservan durante la reconciliación.

### Fase 2: Renderizado del PDF (`--render`)

Lee el estado actual del workspace, reconcilia cambios, rebalancea si es necesario, y genera el PDF final.

Puedes usar el comando directo o el script simplificado:

**Comando directo:**
```bash
python make_album.py --render /ruta/al/workspace
```

**Script simplificado:**
```bash
./render_album.sh /ruta/al/workspace
```

**Ejemplo:**
```bash
./render_album.sh ~/Fotos/viaje_italia_album
```

#### Renderizado parcial (rango de páginas)

Puedes renderizar solo un rango específico de páginas usando los parámetros `--from` y `--to`. La numeración visual es: `0` = portada, `1, 2, 3...` = páginas de contenido, última = contraportada.

**Comando directo:**
```bash
python make_album.py --render /ruta/al/workspace --from 5 --to 10
```

**Ejemplos:**
```bash
# Renderizar solo la portada
python make_album.py --render ~/Fotos/viaje_italia_album --from 0 --to 0

# Renderizar páginas de contenido 10 a 20
python make_album.py --render ~/Fotos/viaje_italia_album --from 10 --to 20

# Renderizar desde la página 15 hasta el final
python make_album.py --render ~/Fotos/viaje_italia_album --from 15
```

**Nota:** Los parámetros `--from` y `--to` son opcionales y solo válidos con `--render`.

#### Renderizado de página única (debug)

Puedes renderizar solo una página específica para pruebas rápidas usando `--page`. El PDF se genera dentro de la carpeta de la página con el nombre `page_XX.pdf`.

**Comando directo:**
```bash
python make_album.py --render /ruta/workspace --page /ruta/workspace/pagina_04_evento
```

**Ejemplos:**
```bash
# Renderizar solo la página 4
python make_album.py --render ~/Fotos/viaje_italia_album \
  --page ~/Fotos/viaje_italia_album/pagina_04_comida_cumple_amona_y_helen

# Usando el script shell
./render_album.sh ~/Fotos/viaje_italia_album \
  --page ~/Fotos/viaje_italia_album/pagina_04_comida_cumple_amona_y_helen
```

**Características:**
- El PDF se genera dentro de la carpeta de página: `pagina_04_.../page_04.pdf`
- NO incluye portada ni contraportada
- Mutuamente excluyente con `--from` y `--to`
- Útil para iterar rápidamente al ajustar `featured_photos` o `hero_photos`
- El número de página en el PDF se toma del `page_number` en `page_config.yaml`

**Nota:** Este modo es ideal para testing. Para el álbum final, usa render normal sin `--page`.

### Fase 3: Editor interactivo (`--edit`)

Abre una interfaz web para editar páginas del álbum de forma interactiva con vista previa en tiempo real.

**Comando:**
```bash
python make_album.py --edit /ruta/al/workspace
```

**Usando el script shell:**
```bash
./edit_album.sh ~/Fotos/viaje_italia_album
```

**Funcionalidades del editor:**

| Acción | Descripción |
|--------|-------------|
| **Reordenar fotos** | Drag-and-drop para cambiar el orden, regenera layout automáticamente |
| **Borrar foto** | Selecciona una foto de la lista y bórrala, el layout se ajusta |
| **Borrar página** | Elimina página completa del álbum |
| **Editar título** | Modifica el título de sección que aparece en la página |
| **Regenerar preview** | Fuerza regeneración del PDF de vista previa |
| **Navegación** | Botones o flechas de teclado para moverse entre páginas |

**Características:**
- **Auto-guardado**: Todos los cambios se guardan automáticamente en el workspace
- **Vista previa PDF**: Preview en tiempo real del resultado final después de cada cambio
- **Interfaz web**: Se abre automáticamente en tu navegador en `http://localhost:5050`
- **Multi-página**: Edita cualquier página del álbum sin cerrar el editor
- **Atajos de teclado**: `←`/`→` para navegar, `Cmd+S` como recordatorio de guardado, `D` para borrar foto seleccionada, `C` para marcar/desmarcar la página o evento actual como "Completado"
- **Estado de revisión**: el botón "Completado" (o la tecla `C`) marca un evento/página como revisado. Aparece una bolita verde en la esquina del ítem en el panel lateral. Los ítems completados se atenúan para destacar lo pendiente. El estado se persiste en `page_config.yaml` (páginas) y `.album_meta.yaml` (eventos fuente)

**Detener el editor:**
Presiona `Ctrl+C` en la ventana de Terminal para detener el servidor Flask.

El PDF se genera en la raíz del workspace:

```
viaje_italia_album/
├── viaje_italia.pdf            # ← PDF generado
├── global_config.yaml
├── portada/
│   └── …
└── …
```

Si el álbum excede `max_pages_per_volume` (por defecto 200), se generan múltiples volúmenes:

```
viaje_italia_Vol1.pdf
viaje_italia_Vol2.pdf
```

## Configuración YAML

### `global_config.yaml`

```yaml
page_size: A4
target_resolution_dpi: 300
photos_per_page_min: 6
photos_per_page_max: 9
max_pages_per_volume: 200
default_background_color: '#0000FF'
typography_system_font: Helvetica
weight_destacada: 1.5
weight_protagonista: 2.5
project_title: Viaje italia
date_range: 09/01/2026 - 15/03/2026
```

| Parámetro | Descripción |
|---|---|
| `page_size` | Tamaño de página (A4) |
| `target_resolution_dpi` | Resolución objetivo para downsampling |
| `photos_per_page_min` | Mínimo de fotos por página (6) |
| `photos_per_page_max` | Máximo de fotos por página (9) |
| `max_pages_per_volume` | Páginas máximas antes de dividir en volúmenes |
| `default_background_color` | Color de fondo por defecto (hex) |
| `typography_system_font` | Fuente del sistema para textos |
| `weight_destacada` | Multiplicador para fotos destacadas (1.5x) |
| `weight_protagonista` | Multiplicador para fotos protagonistas (2.5x) |
| `project_title` | Título del álbum (se deriva automáticamente del nombre del directorio de origen) |
| `date_range` | Rango de fechas del álbum (calculado automáticamente, aparece en portada) |

### `page_config.yaml` (por carpeta de página)

```yaml
page_number: 1
photo_count: 8
layout_seed: 1234567890
override_background_color: null
is_cover: false
is_backcover: false
layout_mode: hibrido
section_titles:
  - "09/01/2026 - Roma"
featured_photos: [img_003.jpg, img_007.jpg]
hero_photos: [img_001.jpg]
```

| Parámetro | Descripción |
|---|---|
| `page_number` | Número de orden de la página |
| `photo_count` | Cantidad de fotos en la página (6-10) |
| `layout_seed` | Semilla para reproducir el layout exacto entre renders |
| `override_background_color` | Color de fondo manual (`null` = automático por ColorThief) |
| `is_cover` / `is_backcover` | Flags para portada/contraportada |
| `layout_mode` | Modo de layout: `mesa_de_luz`, `grid_compacto`, o `hibrido` (se asigna aleatoriamente, editable) |
| `section_titles` | Lista de títulos de sección con fecha (formato: `DD/MM/YYYY - Nombre`) |
| `featured_photos` | Fotos "destacadas" (1.5x): ocupan más espacio en la página (opcional) |
| `hero_photos` | Fotos "protagonistas" (2.5x): ocupan el máximo espacio posible (opcional) |

## Modos de layout

Cada página puede tener uno de tres modos de layout configurables en su `page_config.yaml`:

| Modo | Rotación | Jitter | Borde blanco | Fill factor | Descripción |
|---|---|---|---|---|---|
| `mesa_de_luz` | ±3° | 3% | Sí | 93% | Efecto "fotos esparcidas" con rotación notable |
| `grid_compacto` | No | No | No | 97% | Grid limpio y apretado, máxima densidad |
| `hibrido` | ±1.5° | 1% | Sí | 95% | Balance entre compacto y estético |

Durante `--init`, se asigna un modo aleatorio a cada página. Puedes editarlo manualmente en el YAML antes de ejecutar `--render`.

## Sistema de pesos para fotos destacadas

Puedes marcar fotos específicas dentro de una página para que se rendericen más grandes que el resto. Esto se configura manualmente en el `page_config.yaml` de la página después de ejecutar `--init`.

### Niveles de peso

| Nivel | Lista YAML | Multiplicador | Efecto |
|---|---|---|---|
| Normal | (por defecto) | 1.0x | Tamaño estándar |
| Destacada | `featured_photos` | 1.5x | ~50% más grande |
| Protagonista | `hero_photos` | 2.5x | ~150% más grande |

### Cómo funciona

El algoritmo de layout trata las fotos con peso como si ocuparan "varios slots" durante la distribución en filas. Esto hace que las fotos con peso terminen en filas con menos vecinas, lo que aumenta la altura de esa fila y por tanto el tamaño de todas las fotos en ella (pero especialmente la foto con peso, que también reclama más ancho proporcional).

### Ejemplo

```yaml
# page_config.yaml de una página con 8 fotos
featured_photos: [img_003.jpg, img_007.jpg]  # Destacadas
hero_photos: [img_001.jpg]                    # Protagonista
```

**Resultado**: `img_001.jpg` dominará su fila (puede quedar sola o con 1-2 fotos pequeñas). Las fotos `img_003.jpg` y `img_007.jpg` terminarán en filas con menos fotos que el resto. Las demás fotos (`img_002.jpg`, `img_004-006.jpg`, `img_008.jpg`) se distribuyen normalmente.

### Recomendaciones

- **No abuses**: marcar demasiadas fotos con peso anula el efecto visual de destacar.
- **1-2 protagonistas máximo** por página.
- **2-3 destacadas** como complemento.
- Las fotos con peso funcionan mejor en layouts `mesa_de_luz` o `hibrido` donde la variación de tamaños es más natural.

## Agrupación por carpetas

**Importante**: Las fotos de cada subcarpeta de origen se agrupan en páginas exclusivas. Nunca se mezclan fotos de dos carpetas en la misma página. Si una carpeta tiene pocas fotos en su última página, estas se renderizan más grandes para aprovechar el espacio.

## Reconciliación y rebalanceo automático

Al ejecutar `--render`, el sistema ejecuta dos pasos previos a la generación del PDF:

### Reconciliación (detecta borrados)

Si entre `--init` y `--render` se han eliminado carpetas de página o fotos dentro de ellas:

1. Se detectan las páginas vacías o con menos fotos de las esperadas
2. Se reagrupan TODAS las fotos de cada sección y se redistribuyen equitativamente en el mínimo de páginas necesario
3. Se eliminan carpetas vacías o sobrantes del disco
4. Se renumeran las páginas secuencialmente y se renombran las carpetas
5. Se actualizan los archivos `page_config.yaml`

El `layout_mode` y `layout_seed` de las páginas originales se conservan.

### Rebalanceo en cascada

Si tras la reconciliación alguna página queda fuera del rango 6-10 fotos:

- **Exceso**: las fotos sobrantes se mueven a la página siguiente
- **Déficit**: se extraen fotos de la página siguiente

La cascada se propaga solo dentro de las páginas del mismo grupo (nunca mezcla carpetas).

## Rutas de ejecución

| Acción | Comando | Directorio de trabajo |
|---|---|---|
| Activar entorno | `source .venv/bin/activate` | `~/Coding/Local_PDF_Album_Generator/` |
| **App unificada** | **`./app_album.sh`** | **`~/Coding/Local_PDF_Album_Generator/`** |
| **App unificada (directo)** | **`python make_album.py --app`** | **`~/Coding/Local_PDF_Album_Generator/`** |
| Crear workspace | `./init_album.sh /ruta/fotos` | `~/Coding/Local_PDF_Album_Generator/` |
| Generar PDF | `./render_album.sh /ruta/workspace` | `~/Coding/Local_PDF_Album_Generator/` |
| Editor interactivo | `./edit_album.sh /ruta/workspace` | `~/Coding/Local_PDF_Album_Generator/` |
| Guardar en Git | `git add . && git commit -m "msg" && git push` | `~/Coding/Local_PDF_Album_Generator/` |

## Estructura del código fuente

```
Local_PDF_Album_Generator/
├── make_album.py               # Entry point CLI
├── init_album.sh               # Script simplificado para Fase 1
├── render_album.sh             # Script simplificado para Fase 2
├── edit_album.sh               # Script simplificado para Fase 3 (editor)
├── requirements.txt            # Dependencias Python
├── README.md
├── .venv/                      # Entorno virtual (no commitear)
└── src/
    ├── cli.py                  # Parsing de argumentos (--init, --render)
    ├── ingestion/
    │   ├── scanner.py          # Escaneo recursivo + lectura EXIF
    │   ├── sorter.py           # Ordenación cronológica con fallback por fecha de carpeta
    │   └── downsampler.py      # Resize a 300 DPI target
    ├── workspace/
    │   ├── initializer.py      # Creación de estructura de carpetas
    │   ├── config.py           # Lectura/escritura de YAMLs
    │   ├── reconciler.py       # Reconciliación pre-render: detecta borrados y redistribuye
    │   └── rebalancer.py       # Cascada push/pull entre páginas
    ├── render/
    │   ├── layout.py           # 3 modos de layout (mesa_de_luz, grid_compacto, hibrido)
    │   ├── styling.py          # Fondos dinámicos + bordes blancos
    │   ├── covers.py           # Portada/contraportada con bandas de título y fecha
    │   └── pdf_generator.py    # Orquestador ReportLab + optimización de imágenes
    ├── editor/
    │   ├── app.py              # Flask server (launcher, bootstrap, app mode)
    │   ├── routes.py           # API REST endpoints (album edition)
    │   ├── source_routes.py    # API REST endpoints (source mode)
    │   ├── workspace_manager.py # Operaciones de edición album (reorder, delete, etc.)
    │   ├── source_manager.py   # Operaciones de fuente (rename, delete, regenerate)
    │   ├── templates/
    │   │   ├── launcher.html   # Interfaz selector de carpeta
    │   │   ├── app.html        # Interfaz unificada con tabs Fuente/Edición
    │   │   └── editor.html     # Editor legado (deprecado)
    │   └── static/
    │       ├── css/
    │       │   └── editor.css  # Estilos compartidos (app + editor)
    │       └── js/
    │           ├── common.js   # Utilidades comunes (theme, tabs, logging)
    │           ├── album.js    # Lógica modo Edición (album edition)
    │           ├── source.js   # Lógica modo Fuente (source management)
    │           ├── app.js      # Controlador de tabs y bootstrap
    │           └── editor.js   # Legado (deprecado)
    └── utils/
        ├── color.py            # Extracción de color dominante (optimizado)
        ├── naming.py           # Parsing de nombres y fechas de carpetas
        └── logger.py           # Logging dual: consola (INFO) + archivo (DEBUG)
```

## Ordenación y fotos sin EXIF

Las fotos se ordenan cronológicamente por su fecha EXIF `DateTimeOriginal`. Para fotos que no tienen metadatos EXIF, el sistema asigna una fecha sintética para mantenerlas agrupadas con las demás fotos de su carpeta:

1. **Prefijo de fecha de la carpeta**: si el nombre de la carpeta tiene formato `YYYYMMDD_...`, se usa esa fecha.
2. **Fecha mediana de hermanas**: si otras fotos de la misma carpeta sí tienen EXIF, se usa la fecha mediana.
3. **Fecha determinista**: como último recurso, se genera una fecha basada en el nombre de la carpeta para que las fotos siempre queden agrupadas.

Esto garantiza que las fotos sin EXIF (capturas de pantalla, fotos descargadas, etc.) se mantengan junto a las demás fotos de su carpeta en lugar de mezclarse al final del álbum.

## Optimización del peso del PDF

El generador aplica múltiples técnicas de optimización para mantener el peso del PDF razonable sin sacrificar calidad de impresión:

1. **Downsampling inicial** a 300 DPI (calidad 85%) durante `--init`
2. **Redimensionado dinámico** durante el render: cada imagen se ajusta al tamaño real que ocupará en el PDF (no al tamaño de página completo)
3. **ColorThief optimizado** con miniaturas de 150x150px para análisis de color rápido

Con estas optimizaciones, un álbum de 100 páginas (~600 fotos) generalmente pesa entre 300 MB y 1 GB dependiendo del contenido, manteniendo calidad excelente para impresión profesional.

## Compatibilidad con impresión (Peecho)

Los PDFs generados por esta aplicación cumplen con las especificaciones técnicas de **Peecho** para impresión de libros hardcover:

### Especificaciones cumplidas

| Requisito | Implementación |
|-----------|----------------|
| **Tamaño de página** | A4 (210 x 297 mm) |
| **Resolución** | 300 DPI |
| **Perfil de color** | RGB |
| **Fuentes** | Embebidas automáticamente (TrueType) |
| **Márgenes** | 10mm mínimo en todos los lados (contenido y cubiertas) |
| **Número de páginas** | Par (auto-padding si es necesario) |
| **Rango de páginas** | 24-500 páginas por volumen |
| **Orden del PDF** | Portada → Contenido → Contraportada |
| **Bleed y marcas de corte** | No incluidos (Peecho los genera automáticamente) |

### Validaciones automáticas

Durante el proceso de renderizado (`--render`), la aplicación aplica automáticamente las siguientes correcciones para garantizar compatibilidad con Peecho:

1. **Número par de páginas**: Si el PDF tiene un número impar de páginas, se inserta automáticamente una página en blanco antes de la contraportada.

2. **Mínimo 24 páginas**: Si el álbum tiene menos de 24 páginas totales (portada + contenido + contraportada), se añaden automáticamente páginas en blanco hasta alcanzar el mínimo requerido. Se registra un aviso en el log.

3. **Máximo 500 páginas**: Si `max_pages_per_volume` en `global_config.yaml` excede 498 (500 menos portada y contraportada), se muestra un aviso en el log. El valor por defecto es 200 páginas.

4. **Márgenes de seguridad**: Todos los elementos (fotos, títulos, números de página) respetan un margen mínimo de 10mm desde el borde de la página.

### Limitaciones conocidas

**PDF/X-4**: Peecho recomienda (pero no requiere) el perfil PDF/X-4 (coated FOGRA 39). ReportLab genera PDFs estándar (PDF 1.4) que Peecho acepta sin problemas.

Si necesitas convertir a PDF/X-4, puedes usar Ghostscript como post-procesamiento:

```bash
gs -dPDFX -dBATCH -dNOPAUSE -sDEVICE=pdfwrite \
   -sOutputFile=output_x4.pdf input.pdf
```

### Configuración recomendada para impresión

Para álbumes destinados a impresión profesional con Peecho:

- `max_pages_per_volume`: 200-400 (nunca más de 498)
- `target_resolution_dpi`: 300 (ya es el valor por defecto)
- Verifica que tus fotos originales tengan buena resolución (mínimo 2000x1500 px para fotos de página completa)

## Dependencias

| Paquete | Uso |
|---|---|
| `reportlab` | Generación de PDF con control total de posicionamiento |
| `Pillow` | Procesamiento de imágenes, EXIF, resize |
| `colorthief` | Extracción de color dominante de imágenes |
| `PyYAML` | Parsing de archivos de configuración |
| `exifread` | Lectura robusta de metadatos EXIF |
| `Flask` | Servidor web para el editor interactivo de páginas |

## Git

### Configuración inicial

```bash
cd ~/Coding/Local_PDF_Album_Generator
git init
```

Crear `.gitignore`:

```
.venv/
__pycache__/
*.pyc
.DS_Store
```

Primer commit:

```bash
git add .
git commit -m "Initial commit: Local PDF Album Generator"
```

### Guardar nuevos cambios

```bash
git add .
git commit -m "Descripción de los cambios"
git push origin HEAD
```

### Añadir repositorio remoto (opcional)

```bash
git remote add origin <URL_DEL_REPOSITORIO>
git push -u origin main
```

## Rutas de ejecución simplificadas

Los scripts `.sh` permiten ejecutar el programa sin activar manualmente el entorno virtual cada vez (aunque debe estar creado):

- **App Unificada (RECOMENDADO):** `./app_album.sh`
- **Fase 1 (Init):** `./init_album.sh /ruta/a/fotos`
- **Fase 2 (Render):** `./render_album.sh /ruta/a/workspace_album`
- **Fase 3 (Edit):** `./edit_album.sh /ruta/a/workspace_album`

Todos los scripts deben ejecutarse desde la raíz del proyecto: `~/Coding/Local_PDF_Album_Generator/`.

## Licencia

Uso personal / interno.
