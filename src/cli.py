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

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.init:
        _run_init(args.init.resolve())
    elif args.render:
        _run_render(args.render.resolve())


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


def _run_render(project_dir: Path) -> None:
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

    logger.info(f"Generando PDF ({len(pages)} página(s)) …")
    output_paths = generate_album(pages, global_cfg, project_dir)

    for p in output_paths:
        logger.info(f"PDF generado: {p}")
    logger.info("Listo.")
