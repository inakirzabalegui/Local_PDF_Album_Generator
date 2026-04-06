"""Command-line interface for Local PDF Album Generator."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="make_album",
        description=(
            "Genera álbumes fotográficos profesionales en PDF "
            "a partir de carpetas de imágenes."
        ),
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--init",
        metavar="DIRECTORIO_FOTOS",
        type=Path,
        help=(
            "Modo Creación: escanea el directorio de fotos, crea un workspace "
            "con la estructura de páginas y genera los archivos YAML de estado."
        ),
    )
    group.add_argument(
        "--render",
        metavar="DIRECTORIO_PROYECTO",
        type=Path,
        help=(
            "Modo Reprocesamiento: lee el workspace existente, rebalancea "
            "páginas si es necesario y genera el PDF final."
        ),
    )

    parser.add_argument(
        "--from",
        dest="page_from",
        metavar="N",
        type=int,
        default=None,
        help=(
            "Renderizar desde la página N (0 = portada). "
            "Solo válido con --render."
        ),
    )
    parser.add_argument(
        "--to",
        dest="page_to",
        metavar="N",
        type=int,
        default=None,
        help=(
            "Renderizar hasta la página N (inclusive). "
            "Solo válido con --render."
        ),
    )

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.init:
        if args.page_from is not None or args.page_to is not None:
            print("Error: --from y --to solo son válidos con --render.", file=sys.stderr)
            sys.exit(1)
        _run_init(args.init.resolve())
    elif args.render:
        _run_render(args.render.resolve(), page_from=args.page_from, page_to=args.page_to)


def _run_init(source_dir: Path) -> None:
    if not source_dir.is_dir():
        print(f"Error: '{source_dir}' no es un directorio válido.", file=sys.stderr)
        sys.exit(1)

    from src.ingestion.scanner import scan_directory
    from src.ingestion.sorter import sort_photos
    from src.workspace.config import write_global_config, write_page_configs
    from src.workspace.initializer import create_workspace
    from src.utils.logger import setup_logger

    workspace = source_dir.parent / f"{source_dir.name}_album"
    workspace.mkdir(parents=True, exist_ok=True)
    logger = setup_logger(workspace, "init")

    logger.info(f"Escaneando '{source_dir}' …")
    photos = scan_directory(source_dir)

    if not photos:
        logger.error("No se encontraron imágenes válidas.")
        sys.exit(1)

    logger.info(f"{len(photos)} imágenes encontradas. Ordenando …")
    sorted_photos = sort_photos(photos)

    logger.info(f"Creando workspace en '{workspace}' …")
    global_cfg, page_map = create_workspace(sorted_photos, workspace, source_dir_name=source_dir.name)

    write_global_config(workspace, global_cfg)
    write_page_configs(page_map)

    logger.info(f"Workspace creado con {len(page_map)} página(s).")
    logger.info("Listo. Puedes editar las carpetas y luego ejecutar --render.")


def _run_render(project_dir: Path, page_from: int | None = None, page_to: int | None = None) -> None:
    if not project_dir.is_dir():
        print(f"Error: '{project_dir}' no es un directorio válido.", file=sys.stderr)
        sys.exit(1)

    global_yaml = project_dir / "global_config.yaml"
    if not global_yaml.exists():
        print(
            f"Error: no se encontró 'global_config.yaml' en '{project_dir}'.",
            file=sys.stderr,
        )
        sys.exit(1)

    from src.render.pdf_generator import generate_album
    from src.workspace.config import read_global_config, read_page_configs
    from src.workspace.reconciler import reconcile
    from src.workspace.rebalancer import rebalance
    from src.utils.logger import setup_logger

    logger = setup_logger(project_dir, "render")
    
    logger.info(f"Leyendo proyecto en '{project_dir}' …")
    global_cfg = read_global_config(project_dir)
    pages = read_page_configs(project_dir, global_cfg)

    logger.info("Reconciliando workspace (detectando cambios) …")
    pages = reconcile(pages, global_cfg, project_dir)

    logger.info("Rebalanceando páginas …")
    pages = rebalance(pages, global_cfg, project_dir)

    # Apply page range filter if specified
    if page_from is not None or page_to is not None:
        pages = _filter_pages_by_range(pages, page_from, page_to, logger)

    logger.info(f"Generando PDF ({len(pages)} página(s)) …")
    output_paths = generate_album(pages, global_cfg, project_dir)

    for p in output_paths:
        logger.info(f"PDF generado: {p}")
    logger.info("Listo.")


def _filter_pages_by_range(pages: list, page_from: int | None, page_to: int | None, logger) -> list:
    """Filter pages by visual page range (0=cover, 1..N=content, last=backcover)."""
    if not pages:
        return pages
    
    # Separate pages by type
    cover = next((p for p in pages if p.is_cover), None)
    backcover = next((p for p in pages if p.is_backcover), None)
    content = [p for p in pages if not p.is_cover and not p.is_backcover]
    
    # Build visual index mapping: 0=cover, 1..N=content pages, last=backcover
    visual_pages = []
    if cover:
        visual_pages.append((0, cover))
    
    for page in sorted(content, key=lambda p: p.page_number):
        visual_pages.append((page.page_number, page))
    
    if backcover:
        # Backcover gets the visual index after all content pages
        last_visual_idx = visual_pages[-1][0] + 1 if visual_pages else 1
        visual_pages.append((last_visual_idx, backcover))
    
    # Apply range filter
    from_idx = page_from if page_from is not None else 0
    to_idx = page_to if page_to is not None else visual_pages[-1][0] if visual_pages else 0
    
    filtered = [page for visual_idx, page in visual_pages if from_idx <= visual_idx <= to_idx]
    
    logger.info(f"Filtrando páginas {from_idx} a {to_idx}: {len(filtered)} página(s) seleccionadas.")
    
    return filtered
