# Local PDF Album Generator

Aplicación CLI local para macOS que automatiza la creación de álbumes fotográficos profesionales en PDF a partir de carpetas de imágenes. Motor de renderizado basado en estados (archivos YAML) con un flujo de trabajo en dos fases: **Creación** e **Impresión/Render**.

## Características

- **Escaneo recursivo** de directorios con subcarpetas (cada subcarpeta = un grupo/evento)
- **Títulos de sección automáticos con fecha**: extrae títulos desde nombres de subcarpetas (formato `YYYYMMDD_Nombre`) y los renderiza como `DD/MM/YYYY - Nombre` en el PDF
- **Agrupación estricta**: cada subcarpeta genera páginas independientes, nunca se mezclan fotos de dos carpetas en la misma página
- **Tres modos de layout**: `mesa_de_luz` (rotación +/-3°, jitter), `grid_compacto` (sin rotación, máxima densidad), `hibrido` (rotación sutil +/-1.5°, compacto)
- **Fotos maximizadas**: 6-10 fotos por página con márgenes mínimos (18pt) y fill factors altos (93-97%)
- **Sub-banners para subcarpetas hijas**: si una carpeta de sección contiene subcarpetas (1 nivel), se muestra un banner secundario más pequeño en la primera página donde aparecen esas fotos
- **Ordenación cronológica** por metadatos EXIF `DateTimeOriginal`, con fallback inteligente por fecha de carpeta
- **Downsampling optimizado** a 300 DPI con calidad 85% + redimensionado dinámico en PDF para minimizar el peso
- **Fondos dinámicos**: color dominante calculado automáticamente por página vía ColorThief (optimizado con miniaturas)
- **Portada profesional**: dos bandas con título del álbum (gruesa, primer tercio) y rango de fechas (fina, tercer tercio)
- **Contraportada**: center-crop a sangre completa
- **Rebalanceo en cascada**: si mueves fotos entre carpetas manualmente, el sistema redistribuye automáticamente
- **Volúmenes múltiples**: divide el PDF en varios archivos si se excede el límite de páginas (por defecto 200 páginas)
- **Estado persistente en YAML**: seeds de layout para resultados reproducibles entre renders
- **Barra de progreso**: indicador visual durante la generación del PDF
- **Soporte UTF-8 completo**: renderizado correcto de tildes, ñ, y otros caracteres especiales en títulos y textos mediante fuentes TrueType
- **Renderizado parcial**: opción de generar solo un rango específico de páginas del álbum

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

### Ejemplo de estructura de origen

```
mis_fotos/
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

### 2. Crear el entorno virtual

```bash
python3.13 -m venv .venv
source .venv/bin/activate
```

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

## Uso

La aplicación se ejecuta siempre desde la raíz del proyecto (`Local_PDF_Album_Generator/`) con el entorno virtual activado.

### Configuración por defecto

Antes de usar la aplicación, puedes editar los parámetros por defecto en el archivo [`global_config_default.yaml`](global_config_default.yaml) en la raíz del proyecto. Estos parámetros se aplicarán a **todos los nuevos** álbumes creados con `--init`:

```yaml
page_size: "A4"                        # Tamaño de página
target_resolution_dpi: 300             # Resolución objetivo (DPI)
photos_per_page_min: 6                 # Mínimo de fotos por página
photos_per_page_max: 10                # Máximo de fotos por página
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
photos_per_page_max: 10
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
| `photos_per_page_max` | Máximo de fotos por página (10) |
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
| Crear workspace | `./init_album.sh /ruta/fotos` | `~/Coding/Local_PDF_Album_Generator/` |
| Generar PDF | `./render_album.sh /ruta/workspace` | `~/Coding/Local_PDF_Album_Generator/` |
| Guardar en Git | `git add . && git commit -m "msg" && git push` | `~/Coding/Local_PDF_Album_Generator/` |

## Estructura del código fuente

```
Local_PDF_Album_Generator/
├── make_album.py               # Entry point CLI
├── init_album.sh               # Script simplificado para Fase 1
├── render_album.sh             # Script simplificado para Fase 2
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

## Dependencias

| Paquete | Uso |
|---|---|
| `reportlab` | Generación de PDF con control total de posicionamiento |
| `Pillow` | Procesamiento de imágenes, EXIF, resize |
| `colorthief` | Extracción de color dominante de imágenes |
| `PyYAML` | Parsing de archivos de configuración |
| `exifread` | Lectura robusta de metadatos EXIF |

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

- **Fase 1 (Init):** `./init_album.sh /ruta/a/fotos`
- **Fase 2 (Render):** `./render_album.sh /ruta/a/workspace_album`

Ambos scripts deben ejecutarse desde la raíz del proyecto: `~/Coding/Local_PDF_Album_Generator/`.

## Licencia

Uso personal / interno.
