# Local PDF Album Generator

Aplicación CLI local para macOS que automatiza la creación de álbumes fotográficos profesionales en PDF a partir de carpetas de imágenes. Motor de renderizado basado en estados (archivos YAML) con un flujo de trabajo en dos fases: **Creación** e **Impresión/Render**.

## Características

- **Escaneo recursivo** de directorios con subcarpetas (cada subcarpeta = un grupo/evento)
- **Ordenación cronológica** por metadatos EXIF `DateTimeOriginal`, con fallback aleatorio
- **Downsampling automático** a 300 DPI manteniendo aspect ratio
- **Layout "Mesa de Luz"**: posicionamiento con jitter aleatorio, rotación sutil y superposición controlada
- **Fondos dinámicos**: color dominante calculado automáticamente por página vía ColorThief
- **Portada y contraportada**: center-crop a sangre completa con título superpuesto
- **Rebalanceo en cascada**: si mueves fotos entre carpetas manualmente, el sistema redistribuye automáticamente
- **Volúmenes múltiples**: divide el PDF en varios archivos si se excede el límite de páginas
- **Estado persistente en YAML**: seeds de layout para resultados reproducibles entre renders

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

### Activar el entorno virtual

```bash
cd ~/Coding/Local_PDF_Album_Generator
source .venv/bin/activate
```

### Fase 1: Creación del workspace (`--init`)

Escanea un directorio de fotos, crea la estructura de páginas y genera los archivos YAML de estado.

```bash
python make_album.py --init /ruta/a/mis_fotos
```

**Ejemplo:**

```bash
python make_album.py --init ~/Fotos/viaje_italia
```

Esto genera el workspace `~/Fotos/viaje_italia_album/` con la siguiente estructura:

```
viaje_italia_album/
├── global_config.yaml          # Configuración global del álbum
├── portada/
│   ├── cover.jpg               # Primera imagen (center-crop a sangre)
│   └── page_config.yaml
├── pagina_01/
│   ├── img_001.jpg … img_006.jpg
│   └── page_config.yaml
├── pagina_02/
│   ├── img_001.jpg … img_006.jpg
│   └── page_config.yaml
├── …
└── contraportada/
    ├── backcover.jpg           # Última imagen
    └── page_config.yaml
```

### Intervención manual (opcional)

Después de `--init`, puedes **mover, añadir o borrar fotos** de las subcarpetas de página libremente. El sistema se encargará de rebalancear al ejecutar `--render`.

### Fase 2: Renderizado del PDF (`--render`)

Lee el estado actual del workspace, rebalancea si es necesario, y genera el PDF final.

```bash
python make_album.py --render /ruta/al/workspace
```

**Ejemplo:**

```bash
python make_album.py --render ~/Fotos/viaje_italia_album
```

El PDF se genera en la raíz del workspace:

```
viaje_italia_album/
├── viaje_italia.pdf            # ← PDF generado
├── global_config.yaml
├── portada/
│   └── …
└── …
```

Si el álbum excede `max_pages_per_volume` (por defecto 100), se generan múltiples volúmenes:

```
viaje_italia_Vol1.pdf
viaje_italia_Vol2.pdf
```

## Configuración YAML

### `global_config.yaml`

```yaml
page_size: A4
target_resolution_dpi: 300
photos_per_page_min: 4
photos_per_page_max: 9
max_pages_per_volume: 100
default_background_color: '#0000FF'
typography_system_font: Helvetica
project_title: viaje_italia
```

| Parámetro | Descripción |
|---|---|
| `page_size` | Tamaño de página (A4) |
| `target_resolution_dpi` | Resolución objetivo para downsampling |
| `photos_per_page_min` | Mínimo de fotos por página (4) |
| `photos_per_page_max` | Máximo de fotos por página (9) |
| `max_pages_per_volume` | Páginas máximas antes de dividir en volúmenes |
| `default_background_color` | Color de fondo por defecto (hex) |
| `typography_system_font` | Fuente del sistema para textos |
| `project_title` | Título del álbum (aparece en portada) |

### `page_config.yaml` (por carpeta de página)

```yaml
page_number: 1
photo_count: 6
layout_seed: 1234567890
override_background_color: null
is_cover: false
is_backcover: false
```

| Parámetro | Descripción |
|---|---|
| `page_number` | Número de orden de la página |
| `photo_count` | Cantidad de fotos en la página |
| `layout_seed` | Semilla para reproducir el layout exacto entre renders |
| `override_background_color` | Color de fondo manual (`null` = automático por ColorThief) |
| `is_cover` / `is_backcover` | Flags para portada/contraportada |

## Rebalanceo automático

Si al editar manualmente el workspace una página queda con menos de `photos_per_page_min` o más de `photos_per_page_max` fotos, al ejecutar `--render` se activa el **rebalanceo en cascada**:

- **Exceso**: las fotos sobrantes se mueven a la página siguiente
- **Déficit**: se extraen fotos de la página siguiente

La cascada se propaga secuencialmente hasta que todas las páginas están dentro del rango válido.

## Rutas de ejecución

| Acción | Comando | Directorio de trabajo |
|---|---|---|
| Activar entorno | `source .venv/bin/activate` | `~/Coding/Local_PDF_Album_Generator/` |
| Crear workspace | `python make_album.py --init /ruta/fotos` | `~/Coding/Local_PDF_Album_Generator/` |
| Generar PDF | `python make_album.py --render /ruta/workspace` | `~/Coding/Local_PDF_Album_Generator/` |

## Estructura del código fuente

```
Local_PDF_Album_Generator/
├── make_album.py               # Entry point CLI
├── requirements.txt            # Dependencias Python
├── README.md
├── .venv/                      # Entorno virtual (no commitear)
└── src/
    ├── cli.py                  # Parsing de argumentos (--init, --render)
    ├── ingestion/
    │   ├── scanner.py          # Escaneo recursivo + lectura EXIF
    │   ├── sorter.py           # Ordenación cronológica con fallback
    │   └── downsampler.py      # Resize a 300 DPI target
    ├── workspace/
    │   ├── initializer.py      # Creación de estructura de carpetas
    │   ├── config.py           # Lectura/escritura de YAMLs
    │   └── rebalancer.py       # Cascada push/pull entre páginas
    ├── render/
    │   ├── layout.py           # Algoritmo masonry "mesa de luz"
    │   ├── styling.py          # Fondos dinámicos + bordes blancos
    │   ├── covers.py           # Portada/contraportada a sangre
    │   └── pdf_generator.py    # Orquestador ReportLab
    └── utils/
        └── color.py            # Extracción de color dominante
```

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
```

### Añadir repositorio remoto (opcional)

```bash
git remote add origin <URL_DEL_REPOSITORIO>
git push -u origin main
```

## Licencia

Uso personal / interno.
