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
    parser.add_argument(
        "--page",
        metavar="PATH_CARPETA_PAGINA",
        type=Path,
        default=None,
        help=(
            "Renderizar solo una página específica. "
            "Path absoluto a la carpeta de página (ej: /ruta/workspace/pagina_04_...). "
            "El PDF se genera dentro de la carpeta como page_N.pdf. "
            "Mutuamente excluyente con --from/--to."
        ),
    )

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.init:
        if args.page_from is not None or args.page_to is not None or args.page is not None:
            print("Error: --from, --to y --page solo son válidos con --render.", file=sys.stderr)
            sys.exit(1)
        _run_init(args.init.resolve())
    elif args.render:
        # Validar que --page y --from/--to sean mutuamente excluyentes
        if args.page is not None and (args.page_from is not None or args.page_to is not None):
            print("Error: --page no puede usarse junto con --from/--to.", file=sys.stderr)
            sys.exit(1)
        _run_render(args.render.resolve(), page_from=args.page_from, page_to=args.page_to, single_page_path=args.page)


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
    scan_result = scan_directory(source_dir)

    # Log special folders status
    if scan_result.cover_photos:
        logger.info(f"✓ Carpeta 'portada' encontrada: {len(scan_result.cover_photos)} foto(s)")
    else:
        logger.info("○ Carpeta 'portada' no encontrada, se usará foto aleatoria")
    
    if scan_result.backcover_photos:
        logger.info(f"✓ Carpeta 'contraportada' encontrada: {len(scan_result.backcover_photos)} foto(s)")
    else:
        logger.info("○ Carpeta 'contraportada' no encontrada, se usará foto aleatoria")

    if not scan_result.photos:
        logger.error("No se encontraron imágenes válidas.")
        sys.exit(1)

    logger.info(f"{len(scan_result.photos)} imágenes encontradas. Ordenando …")
    sorted_photos = sort_photos(scan_result.photos)

    logger.info(f"Creando workspace en '{workspace}' …")
    global_cfg, page_map = create_workspace(
        sorted_photos, 
        workspace, 
        source_dir_name=source_dir.name,
        cover_candidates=scan_result.cover_photos,
        backcover_candidates=scan_result.backcover_photos,
    )

    write_global_config(workspace, global_cfg)
    write_page_configs(page_map)

    logger.info(f"Workspace creado con {len(page_map)} página(s).")
    logger.info("Listo. Puedes editar las carpetas y luego ejecutar --render.")


def _run_render(project_dir: Path, page_from: int | None = None, page_to: int | None = None, single_page_path: Path | None = None) -> None:
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
    
    # Si se especificó --page, renderizar solo esa página
    if single_page_path is not None:
        _render_single_page(single_page_path, global_cfg, logger)
        return
    
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


def _render_single_page(page_path: Path, global_cfg, logger) -> None:
    """Renderizar una sola página y generar PDF en su carpeta."""
    from src.workspace.config import PageConfig, VALID_IMAGE_EXTENSIONS
    from src.render.pdf_generator import generate_single_page_pdf
    import yaml
    import random
    
    # Validar que el path existe y es un directorio
    if not page_path.is_dir():
        print(f"Error: '{page_path}' no es un directorio válido.", file=sys.stderr)
        sys.exit(1)
    
    # Validar que contiene page_config.yaml
    config_file = page_path / "page_config.yaml"
    if not config_file.exists():
        print(f"Error: No se encontró 'page_config.yaml' en '{page_path}'.", file=sys.stderr)
        sys.exit(1)
    
    # Leer la configuración de la página
    with open(config_file, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    
    # Obtener imágenes reales
    actual_images = sorted(
        p for p in page_path.iterdir()
        if p.is_file() and p.suffix.lower() in VALID_IMAGE_EXTENSIONS
    )
    
    # Crear PageConfig
    page_cfg = PageConfig(
        folder=page_path,
        page_number=data.get("page_number", 0),
        photo_count=len(actual_images),
        layout_seed=data.get("layout_seed", random.randint(0, 2**31)),
        override_background_color=data.get("override_background_color"),
        is_cover=data.get("is_cover", False),
        is_backcover=data.get("is_backcover", False),
        section_titles=data.get("section_titles", []),
        layout_mode=data.get("layout_mode", "mesa_de_luz"),
        featured_photos=data.get("featured_photos", []),
        hero_photos=data.get("hero_photos", []),
    )
    
    logger.info(f"Renderizando página {page_cfg.page_number} …")
    
    # Generar PDF en la carpeta de la página
    output_path = generate_single_page_pdf(page_cfg, global_cfg)
    
    logger.info(f"PDF generado: {output_path}")
    logger.info("Listo.")
