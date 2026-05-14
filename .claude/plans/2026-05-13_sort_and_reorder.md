# Plan: Sort root‑cause fix + manual page reorder

Fecha: 2026-05-13
Estado: en ejecución

## Contexto

El álbum `/Users/jzabalegui/Pictures/2025_album` se generó con secciones fuera de orden cronológico: páginas de agosto aparecen antes que páginas de mayo, páginas de octubre en medio de junio, etc. La carpeta fuente `/Users/jzabalegui/Pictures/2025` tiene el patrón `YYYYMMDD_Name` por evento.

### Causa raíz

`src/workspace/initializer.py:139-145` itera `content_photos` (ya ordenado por `(date_taken, source_group, name)` en `sorter.py:30`) y registra cada `source_group` en `groups_dict` la **primera vez** que ve una foto de él. El orden de iteración de `groups_dict.items()` luego determina el orden de las páginas.

Resultado: el orden de las carpetas en el álbum lo decide la **foto con EXIF más antigua dentro de cada carpeta**, NO el prefijo `YYYYMMDD_` del nombre. Basta con una foto outlier (captura, importada, fecha falsa) para descolocar la sección entera.

### Drag‑and‑drop roto

`/api/pages/reorder` en `workspace_manager.py:382` ya existe pero valida contigüidad de `section_id`. El Sortable de páginas en `album.js:1329` lo llama pero el flujo está roto. Usuario quiere un botón "Mover a página…" en su lugar.

## Decisiones (P1–P21)

| # | Decisión |
|---|---|
| P1 | Fix sort + tool **resort** que renombra carpetas/page_number conservando ediciones. |
| P2 | Orden de secciones: prefijo `YYYYMMDD_` → mediana EXIF → hash determinista. |
| P3 | Orden de fotos dentro de página: EXIF chronológico (sin cambios). |
| P4 | Botón "Mover a página" en `#album-action-bar`. |
| P5 | **Sin rango** — cualquier página a cualquier posición. |
| P6 | Concepto "independiente" eliminado por P5. |
| P7 | Cualquier página a cualquier posición (cross‑section permitido). |
| P8 | Sin límite. |
| P9 | Drag‑and‑drop de páginas: deshabilitar visualmente, código intacto. |
| P10 | Disparo del resort: (a) botón en header + (c) CLI `--resort-sections`. |
| P11 | Resort conserva: títulos, completed, featured/hero, layout_mode, layout_seed, fotos, orden, manifest. Solo cambia `page_number` y nombre de carpeta. |
| P12 | Carpetas sin prefijo: mediana del EXIF. |
| P13 | Botón mueve solo la página activa (no multi‑select v1). |
| P14 | Semántica del input: número tecleado = posición final. |
| P15 | Sin doble confirmación (Aceptar/Cancelar). |
| P16 | Deshabilitar Sortable de páginas (hide handle + cursor). |
| P17 | Fuente de fecha para resort: `section_titles[0]` → manifest source EXIF → mtime archivo original. |
| P18 | Tie‑break en empate de fecha: orden actual (estable). |
| P19 | Fuera de rango: error inline, no cierra modal. |
| P20 | Undo del move_page: sí, guardando `oldPageId` y posición. |
| P21 | Refoco tras resort: por `section_id` + offset dentro de sección. |

### Consecuencias clave

- Tras un move manual cross‑section, las secciones pueden quedar intercaladas. El `reconciler` y `rebalancer` seguirán operando por `section_id` pero no encontrarán páginas adyacentes del mismo grupo para hacer push/pull. **Asumido**: el usuario hace moves manuales fuera de flujos de balance.
- EXIF NO está preservado en los JPG downsampled (`downsampler.py:18-45` no pasa `exif=` a `Image.save`). Para fechas de secciones sin prefijo en álbumes existentes, hay que leer del manifest el `source_path` y abrir el JPG original.

## Decisión adicional 2026-05-14: persistencia de move cross-section

**Regla A:** cuando se mueve una página mediante `↕️ Mover a página` a una posición perteneciente a otra sección, la página **adopta** el `section_id` y `section_date` de su vecino precedente en el nuevo orden (o del vecino siguiente si la página queda en la posición 0).

**Regla A1:** `section_titles` nunca se toca — la página conserva su etiqueta de origen (ej. "01/08/2025 - Js en EEUU") como traza narrativa.

**Consecuencia:** tras la adopción, un posterior "🔧 Reordenar secciones" agrupa la página con su nueva sección adoptada, no con la original. El manifest (`.photo_manifest.yaml`) también se actualiza para mantener `section_id` en sincronía.

**No-op:** si la página ya pertenece al mismo `section_id` que su vecino (move intra-sección), no se escribe nada.

**Edge case:** si `ordered_page_ids` tiene un solo elemento, no hay vecino → sin adopción, sin crash.

## API contract (fijado para ambos subagentes)

### POST `/api/pages/reorder` (modificado)
- Body: `{"ordered_page_ids": ["pagina_01_x", "pagina_02_y", ...], "moved_page_id": "pagina_03_z"}`
  - `moved_page_id` es opcional (puede omitirse o ser `null`).
- **Cambio**: eliminar validación de contigüidad por `section_id` (workspace_manager.py:427-440).
- Respuesta: `{"success": bool, "error": str|null, "renamed_pages": [{"old_id", "new_id"}], "section_changed": {"page_id", "old_section_id", "new_section_id"}|omitido}`
  - `section_changed` sólo aparece cuando hubo adopción cross-section.

### POST `/api/sections/resort` (nuevo)
- Body: `{}` (sin parámetros)
- Acción: agrupar páginas por `section_id`, calcular `section_date` por sección (orden P17), reordenar secciones, renombrar carpetas y `page_number` preservando orden de páginas dentro de sección. Tie‑break estable (P18).
- Respuesta: `{"success": bool, "error": str|null, "renamed_pages": [{"old_id", "new_id"}], "focus_section_id": str|null}`

## Cambios por archivo

### Backend

**`src/workspace/config.py`**
- Añadir `section_date: str = ""` (DD/MM/YYYY) a `PageConfig` dataclass + `to_dict` + plantilla YAML + parser.

**`src/utils/naming.py`**
- Añadir `def section_date_sort_key(section_title: str) -> tuple` o helper para parsear `"DD/MM/YYYY - Nombre"`.

**`src/workspace/initializer.py`**
- Antes del `for source_group, group_photos in groups_dict.items()`, ordenar `groups_dict` por clave de sección: folder prefix → mediana EXIF → hash determinista.
- Calcular y guardar `section_date` en cada `PageConfig`.

**`src/workspace/resort.py`** (nuevo)
- `def resort_sections(workspace: Path) -> dict`: lee páginas, agrupa por section_id, calcula sort key por orden P17, reordena secciones, renombra carpetas con misma técnica phase‑1/phase‑2 que `reorder_pages`. Conserva todo el contenido de page_config (P11).

**`make_album.py`**
- Nuevo flag `--resort-sections /path/to/workspace`.

**`src/editor/workspace_manager.py`**
- `reorder_pages`: eliminar bloque `# Validate section contiguity` (líneas 427-440).
- `reorder_pages` extendido con parámetro opcional `moved_page_id: str | None = None`. Cuando se detecta cruce de sección, adopta `section_id` y `section_date` del vecino precedente (o siguiente en posición 0) tanto en `page_config.yaml` como en `.photo_manifest.yaml` vía `read_page_manifest`/`write_page_manifest`. Retorna `section_changed` en el dict de respuesta.
- Importar/exponer `resort_sections`.

**`src/editor/routes.py`**
- Nuevo endpoint `POST /api/sections/resort` que llama a `resort_sections(workspace)`.

### Frontend

**`src/editor/templates/app.html`**
- En `#album-action-bar` (línea ~189): añadir `<button id="move-page-btn" class="btn btn-secondary">↕️ Mover a página</button>` entre `💥 Explotar` y `🗑️ Borrar`.
- En header (línea ~97): añadir `<button id="resort-sections-btn" class="btn btn-secondary" title="Reordena secciones por fecha de carpeta">🔧 Reordenar secciones</button>` entre `🔄 Sincronizar` y `⚠️ Reset álbum`.

**`src/editor/static/js/album.js`**
- Wire `#move-page-btn` → abre `#generic-dialog` con título "Mover a página", input numérico (`min=1 max=N`). Validación de rango (P19). Si OK, construye `ordered_page_ids` reposicionando la página activa al índice tecleado, llama `POST /api/pages/reorder`, push undo state con `{action:'move_page', oldIndex, pageId}`.
- `performUndo`: nuevo case `'move_page'` que vuelve a llamar `/api/pages/reorder` con la página re‑colocada al `oldIndex`.
- Deshabilitar `Sortable` en `#page-list` (línea ~1329). Quitar `dragHandle` del item (línea ~364‑372 en album.js para fotos NO; el handle de página está en otro lado, hay que localizar).

**`src/editor/static/js/app.js`** (o nuevo handler en album.js si encaja mejor)
- Wire `#resort-sections-btn` → confirm dialog → `POST /api/sections/resort` → recarga `PAGES_DATA` → refoca por `section_id` + offset (P21).

**`src/editor/static/css/editor.css`**
- Si hay `cursor: move` o `cursor: grab` en `.page-list-item`, comentarlo.

## Plan de ejecución

1. **Plan doc** (este archivo) — ✅
2. **Subagente Backend** (Sonnet, paralelo a frontend) — encapsulado, sin dependencias cruzadas.
3. **Subagente Frontend** (Sonnet, paralelo a backend) — usa el API contract fijado arriba.
4. **Verify + smoke test** (Opus): leer cada archivo modificado, comprobar contratos, levantar app y probar los dos botones.

## Resume instructions (si la sesión se corta)

1. `cat .claude/plans/2026-05-13_sort_and_reorder.md` (este archivo).
2. `git status` + `git diff` para ver qué se hizo.
3. `TaskList` para ver progreso.
4. Si faltan tareas, lanzarlas con los specs de "Cambios por archivo" arriba.
5. La sección "API contract" es la verdad: ambos subagentes deben respetarla.

## Riesgos conocidos

- **Reconciler/rebalancer post move cross‑section**: pueden no balancear páginas no adyacentes. No bloqueante, asumido por usuario.
- **Multi-section workspace antiguo sin `section_date`**: resort.py debe derivarlo on‑the‑fly de `section_titles[0]` + manifest. Después de un resort, los page_configs llevarán `section_date` poblado.
- **JPG downsampled sin EXIF**: si la carpeta fuente original ya no existe y no hay prefijo en el título, fallback a mtime del archivo en disco.
