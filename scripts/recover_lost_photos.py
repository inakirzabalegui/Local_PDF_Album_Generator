#!/usr/bin/env python3
"""Recupera fotos perdidas por el bug de sobrescritura en move_photos.

Detecta fotos del source que NO están referenciadas en ningún manifest del
workspace y que tampoco aparecen en los tombstones (borrados intencionales).
Esas fotos son víctimas del bug. El script las restaura copiando una versión
downsampleada en la última página de su sección y marca esa página como
`completed: false` para que el usuario pueda revisarla.

Uso:
    python scripts/recover_lost_photos.py \\
        --workspace /Users/jzabalegui/Pictures/2025_album \\
        --source    /Users/jzabalegui/Pictures/2025 \\
        [--apply]

Sin --apply el script es dry-run: imprime el plan sin tocar nada.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from src.ingestion.downsampler import downsample_image  # noqa: E402
from src.workspace.config import (  # noqa: E402
    PageConfig,
    VALID_IMAGE_EXTENSIONS,
    read_global_config,
    read_page_configs,
)
from src.workspace.manifest import (  # noqa: E402
    add_photo_to_manifest,
    collect_workspace_manifests,
    compute_photo_signature,
)
from src.workspace.tombstones import read_tombstones  # noqa: E402


logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(message)s",
)
logger = logging.getLogger("recover_lost_photos")

COVER_FOLDERS = {"portada", "contraportada"}


def enumerate_source_photos(source_root: Path) -> set[str]:
    """Fotos del source como rutas relativas POSIX, sin portada/contraportada.

    Excluye también carpetas ocultas (empiezan por '.') a cualquier nivel,
    incluyendo la papelera `.trash/` que pueda existir junto al source.
    """
    out: set[str] = set()
    for p in source_root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in VALID_IMAGE_EXTENSIONS:
            continue
        try:
            rel = p.relative_to(source_root).as_posix()
        except ValueError:
            continue
        parts = rel.split("/")
        if any(seg.startswith(".") for seg in parts):
            continue
        top = parts[0]
        if top.lower() in COVER_FOLDERS:
            continue
        out.add(rel)
    return out


def collect_referenced_paths(workspace: Path) -> set[str]:
    """Todos los source_path referenciados en cualquier manifest del workspace."""
    referenced: set[str] = set()
    for pm in collect_workspace_manifests(workspace):
        for entry in pm.photos.values():
            if entry.source_path:
                referenced.add(entry.source_path)
    return referenced


def build_section_index(source_root: Path) -> dict[str, str]:
    """source_group_name -> section_id (leído de cada .album_meta.yaml)."""
    index: dict[str, str] = {}
    for child in source_root.iterdir():
        if not child.is_dir():
            continue
        if child.name.lower() in COVER_FOLDERS:
            continue
        meta = child / ".album_meta.yaml"
        if not meta.exists():
            continue
        try:
            with open(meta, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except Exception as exc:
            logger.warning("No se pudo leer %s: %s", meta, exc)
            continue
        sid = str(data.get("section_id", "") or "")
        if sid:
            index[child.name] = sid
    return index


def group_pages_by_section(pages: list[PageConfig]) -> dict[str, list[PageConfig]]:
    out: dict[str, list[PageConfig]] = defaultdict(list)
    for cfg in pages:
        if cfg.is_cover or cfg.is_backcover:
            continue
        if not cfg.section_id:
            continue
        out[cfg.section_id].append(cfg)
    for v in out.values():
        v.sort(key=lambda c: c.page_number)
    return out


def next_free_img_name(folder: Path, ext: str, reserved: set[str]) -> str:
    """Primer img_NNN<ext> libre en folder, considerando nombres ya reservados.

    `reserved` mantiene los nombres que vamos a usar dentro de esta misma
    ejecución (las restauraciones se planifican antes de tocar disco).
    """
    if ext not in (".jpg", ".jpeg"):
        ext = ".jpg"
    existing = [
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in VALID_IMAGE_EXTENSIONS
    ]
    seq = len(existing) + 1
    while True:
        candidate = f"img_{seq:03d}{ext}"
        if not (folder / candidate).exists() and candidate not in reserved:
            return candidate
        seq += 1


def mark_page_not_completed(page_folder: Path) -> None:
    cfg_path = page_folder / "page_config.yaml"
    if not cfg_path.exists():
        return
    with open(cfg_path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if data.get("completed") is False:
        return
    data["completed"] = False
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)


def plan_recoveries(
    orphans: list[str],
    section_index: dict[str, str],
    pages_by_section: dict[str, list[PageConfig]],
) -> tuple[list[dict], list[dict]]:
    """Devuelve (recoverable, skipped). Cada item incluye motivo y destino."""
    recoverable: list[dict] = []
    skipped: list[dict] = []

    # Reservas por página para que múltiples huérfanas de la misma sección
    # obtengan nombres distintos en la misma corrida.
    reserved_per_folder: dict[Path, set[str]] = defaultdict(set)

    for orphan in sorted(orphans):
        source_group = orphan.split("/", 1)[0]
        section_id = section_index.get(source_group, "")
        if not section_id:
            skipped.append({
                "orphan": orphan,
                "reason": f"sin section_id para grupo '{source_group}' "
                          f"(¿falta .album_meta.yaml?)",
            })
            continue

        candidate_pages = pages_by_section.get(section_id) or []
        if not candidate_pages:
            skipped.append({
                "orphan": orphan,
                "reason": f"sección {section_id[:8]}... sin páginas en workspace",
            })
            continue

        dest_page = candidate_pages[-1]
        src_ext = Path(orphan).suffix.lower()
        dst_ext = src_ext if src_ext in (".jpg", ".jpeg") else ".jpg"
        reserved = reserved_per_folder[dest_page.folder]
        img_name = next_free_img_name(dest_page.folder, dst_ext, reserved)
        reserved.add(img_name)

        recoverable.append({
            "orphan": orphan,
            "section_id": section_id,
            "dest_folder": dest_page.folder,
            "dest_page_number": dest_page.page_number,
            "img_name": img_name,
        })

    return recoverable, skipped


def print_plan(recoverable: list[dict], skipped: list[dict]) -> None:
    print("─" * 72)
    if not recoverable and not skipped:
        print("No se detectaron fotos huérfanas. Nada que restaurar.")
        return

    for item in recoverable:
        print(f"[ORPHAN] {item['orphan']}")
        print(f"  → restaurar en {item['dest_folder'].name} como {item['img_name']}")
        print(f"  → marcar {item['dest_folder'].name} como completed=false")

    for item in skipped:
        print(f"[SKIP]   {item['orphan']}")
        print(f"  motivo: {item['reason']}")

    print("─" * 72)
    print(
        f"Resumen: {len(recoverable) + len(skipped)} huérfanas detectadas, "
        f"{len(recoverable)} restaurables, {len(skipped)} ignoradas."
    )


def apply_recoveries(
    recoverable: list[dict],
    source_root: Path,
    target_dpi: int,
) -> tuple[int, int, set[Path]]:
    """Ejecuta el plan. Devuelve (ok, errores, páginas tocadas)."""
    ok = 0
    errors = 0
    touched_pages: set[Path] = set()

    for item in recoverable:
        orphan_rel = item["orphan"]
        dest_folder: Path = item["dest_folder"]
        img_name: str = item["img_name"]
        section_id: str = item["section_id"]

        src_path = source_root / orphan_rel
        if not src_path.exists():
            print(f"[ERROR]  {orphan_rel} — el archivo source ha desaparecido")
            errors += 1
            continue

        dst_path = dest_folder / img_name

        result = downsample_image(src_path, dst_path, dpi=target_dpi)
        if result is None:
            print(f"[ERROR]  {orphan_rel} — fallo de downsample")
            errors += 1
            continue

        mtime, sha = compute_photo_signature(src_path)
        try:
            add_photo_to_manifest(
                dest_folder,
                img_name,
                source_path=orphan_rel,
                source_mtime=mtime,
                sha1=sha,
                section_id=section_id,
            )
        except Exception as exc:
            print(f"[ERROR]  {orphan_rel} — fallo al actualizar manifest: {exc}")
            # Limpiar el archivo si el manifest falla.
            try:
                dst_path.unlink()
            except OSError:
                pass
            errors += 1
            continue

        touched_pages.add(dest_folder)
        ok += 1
        print(f"[OK]     {orphan_rel} → {dest_folder.name}/{img_name}")

    for page_folder in touched_pages:
        try:
            mark_page_not_completed(page_folder)
        except Exception as exc:
            logger.warning(
                "No se pudo marcar %s como pendiente: %s", page_folder.name, exc
            )

    return ok, errors, touched_pages


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Recupera fotos perdidas por el bug de move_photos.",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        required=True,
        help="Workspace afectado (con global_config.yaml).",
    )
    parser.add_argument(
        "--source",
        type=Path,
        required=True,
        help="Carpeta source original (las fotos sin downsamplear).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Aplicar cambios. Sin esta flag se ejecuta en dry-run.",
    )
    args = parser.parse_args()

    workspace: Path = args.workspace.expanduser().resolve()
    source_root: Path = args.source.expanduser().resolve()

    if not (workspace / "global_config.yaml").exists():
        print(
            f"ERROR: {workspace} no parece un workspace (sin global_config.yaml).",
            file=sys.stderr,
        )
        return 2
    if not source_root.is_dir():
        print(f"ERROR: source root no existe o no es un directorio: {source_root}",
              file=sys.stderr)
        return 2

    print(f"Workspace: {workspace}")
    print(f"Source:    {source_root}")
    print(f"Modo:      {'APLICAR' if args.apply else 'DRY-RUN'}")
    print()

    global_cfg = read_global_config(workspace)
    pages = read_page_configs(workspace, global_cfg)
    pages_by_section = group_pages_by_section(pages)

    source_photos = enumerate_source_photos(source_root)
    referenced = collect_referenced_paths(workspace)
    tombstoned = {sp for (_, sp) in read_tombstones(workspace)}

    orphans = sorted(source_photos - referenced - tombstoned)

    section_index = build_section_index(source_root)
    recoverable, skipped = plan_recoveries(orphans, section_index, pages_by_section)

    print_plan(recoverable, skipped)

    if not args.apply:
        print()
        print("Dry-run. Para aplicar:")
        print(
            f"  python {Path(__file__).relative_to(ROOT)} "
            f"--workspace {workspace} --source {source_root} --apply"
        )
        return 0

    if not recoverable:
        print("Nada que aplicar.")
        return 0

    print()
    print(f"BACKUP: copia {workspace} antes de continuar.")
    print("Escribe 'APLICAR' (mayúsculas) para ejecutar la restauración:")
    try:
        answer = input("> ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nCancelado.")
        return 1
    if answer != "APLICAR":
        print("Cancelado: no se ha escrito 'APLICAR'.")
        return 1

    print()
    ok, errors, touched = apply_recoveries(
        recoverable, source_root, global_cfg.target_resolution_dpi
    )
    print()
    print("─" * 72)
    print(f"Restauradas: {ok}   Errores: {errors}   Páginas marcadas pendientes: {len(touched)}")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
