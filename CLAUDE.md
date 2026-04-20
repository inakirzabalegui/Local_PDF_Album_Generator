# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

All commands must be run from the project root with the virtualenv activated.

## Key Commands

| Action | Command |
|---|---|
| Create workspace from photos | `python make_album.py --init /path/to/photos` |
| Generate PDF | `python make_album.py --render /path/to/workspace` |
| Open interactive editor | `python make_album.py --edit /path/to/workspace` |
| **Launch unified app** | **`python make_album.py --app`** |
| Render single page (debug) | `python make_album.py --render /path/to/workspace --page /path/to/workspace/pagina_04_...` |
| Render page range | `python make_album.py --render /path/to/workspace --from 5 --to 10` |

The shell scripts `init_album.sh`, `render_album.sh`, and `edit_album.sh` wrap the above commands and activate the virtualenv automatically.

There is no test suite or linter configuration in this project.

## Architecture Overview

The application has three operational modes, plus a unified app launcher:

**Phase 1 (`--init`):** Scans a photo directory, downsamples images to 300 DPI, sorts them chronologically by EXIF, groups them by source subfolder, and creates a *workspace* directory. The workspace contains one folder per page with the physical image files and a `page_config.yaml` per page, plus a top-level `global_config.yaml`.

**Phase 2 (`--render`):** Reads the workspace state, runs *reconciliation* (detects deleted pages/photos and redistributes remaining photos across pages) and *rebalancing* (cascade push/pull to keep each page within the 6–10 photo range), then generates the PDF using ReportLab.

**Phase 3 (`--edit`):** Starts a Flask server on port 5050, serving a drag-and-drop web UI that modifies workspace files directly (photo order, deletions, title edits). Changes are auto-saved to the YAML/filesystem. This mode requires a workspace path: `python make_album.py --edit /path/to/workspace`

**Phase 4 (`--app`):** Launches a unified web application with two modes:
- **Fuente (Source Mode):** Browse and manage the original photo folders. Rename events, delete photos, regenerate the album workspace from scratch.
- **Edición (Album Edition):** Edit the generated album workspace (photo order, deletions, titles, layout modes, move photos between pages). Identical to Phase 3 but integrated into a tabbed interface.

The app starts with a launcher that requests the user to select a source folder via a native file picker. It auto-detects or creates the `_album` workspace sibling and presents both modes in a single UI.

### Data Flow

```
photos/ → scanner → sorter → downsampler → initializer → workspace/
                                                              ↓
                                          reconciler → rebalancer → pdf_generator → album.pdf
```

Additionally, for the unified app:
```
Launch --app → Launcher (pick folder) → Bootstrap (check/create _album) → Unified App (tabs: Fuente | Edición)
```

### Key State Files

- **`global_config.yaml`** (workspace root): album-wide settings (page size, DPI, min/max photos per page, background color, font, photo weight multipliers, project title, date range). Editable before `--render`.
- **`page_config.yaml`** (per page folder): `layout_seed`, `layout_mode`, `section_titles`, optional `featured_photos` (1.5× weight) and `hero_photos` (2.5× weight). `layout_seed` is preserved across reconciliations to keep layouts reproducible.
- **`global_config_default.yaml`** (repo root): application-wide defaults applied to every new album on `--init`.

### Source Module Responsibilities

- **`src/workspace/config.py`** — `GlobalConfig` and `PageConfig` dataclasses; all YAML serialization/deserialization.
- **`src/workspace/reconciler.py`** — Detects deletions between `--init` and `--render`, redistributes photos per section into the minimum needed pages, renumbers and renames page folders on disk.
- **`src/workspace/rebalancer.py`** — Cascade push/pull: moves photos between adjacent pages (within same section) to satisfy the min/max constraint.
- **`src/render/layout.py`** — Implements the three layout modes (`mesa_de_luz`, `grid_compacto`, `hibrido`) and the weight-based row allocation algorithm.
- **`src/render/pdf_generator.py`** — ReportLab orchestrator; handles multi-volume splitting, Peecho compatibility (even page count, 24–500 pages), and dynamic image resizing at render time.
- **`src/editor/routes.py`** + **`workspace_manager.py`** — REST API endpoints consumed by the legacy web editor frontend.
- **`src/editor/source_routes.py`** + **`source_manager.py`** — REST API endpoints for Source mode folder/photo management.
- **`src/editor/app.py`** — Flask app setup, launcher, bootstrap, and unified app context.

### Important Constraints

- **Peecho print compatibility:** PDFs must have an even number of pages, between 24 and 500. These validations run automatically during `--render`.
- **Section isolation:** Photos from different source subfolders are never placed on the same page. Reconciliation and rebalancing respect section boundaries.
- **Folder naming:** Source subfolder names in format `YYYYMMDD_Name` are parsed into section titles `DD/MM/YYYY - Name`. Special folders `portada/` and `contraportada/` (case-insensitive) supply cover photos and are excluded from content pages.
- **Font registration:** Registers `/System/Library/Fonts/Helvetica.ttc` as a TrueType font for UTF-8 support (tildes, ñ). Falls back to standard ReportLab fonts if unavailable.
- **Photo Renaming in Source Mode:** When an event folder is renamed, all photos inside are automatically renamed with a CamelCase prefix derived from the folder name, maintaining chronological order. For example, renaming `20260109_Comida_Despedida_Js` to just `Comida despedida Js` will rename photos to `ComidaDespedidaJs_001.jpg`, `ComidaDespedidaJs_002.jpg`, etc.

