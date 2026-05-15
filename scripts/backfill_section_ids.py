"""One-time backfill for pages where page_config.yaml lost section_id (and
optionally section_titles / sub_group_ids).

Root cause: `create_page_after` in src/editor/workspace_manager.py did not
propagate section_id when creating split pages, so any "Explotar página en
dos" produced a PageConfig with section_id=''. A subsequent Sincronizar would
then send those pages to the end of the album, because
`_reorder_pages_chronologically` ranks pages with empty section_id after every
page that does map to a source group.

Strategy:
1. For each pagina_*/page_config.yaml with empty section_id, look up the
   sibling .photo_manifest.yaml — the manifest preserves section_id correctly
   because move_photo_in_manifest sets it.
2. If section_titles is also empty, reconstruct it from the manifest photo
   source_paths: parts[0] is the top-level source group, parts[1] is the
   sub_group; the top title uses build_section_title and the sub title joins
   prettified sub_groups.

Run with the workspace path as the single positional argument. Use --dry-run
to inspect changes without writing.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.utils.naming import build_section_title, prettify_folder_name


def _load_source_title_to_sid(source_root: Path | None) -> dict[str, str]:
    """Map canonical section title → section_id from each source group's .album_meta.yaml.

    Empty dict when source_root is missing or unreadable.
    """
    out: dict[str, str] = {}
    if source_root is None or not source_root.is_dir():
        return out
    for d in source_root.iterdir():
        if not d.is_dir():
            continue
        if d.name.lower() in ("portada", "contraportada"):
            continue
        meta_path = d / ".album_meta.yaml"
        if not meta_path.exists():
            continue
        try:
            with open(meta_path, encoding="utf-8") as f:
                meta = yaml.safe_load(f) or {}
        except Exception:
            continue
        sid = str((meta or {}).get("section_id", "") or "")
        if not sid:
            continue
        title = build_section_title(d.name)
        if title and title not in out:
            out[title] = sid
    return out


def _split_source_path(source_path: str) -> tuple[str, str]:
    """Return (source_group, sub_group). sub_group is '' for top-level photos."""
    if not source_path:
        return "", ""
    parts = source_path.split("/")
    top = parts[0] if parts else ""
    sub = parts[1] if len(parts) >= 3 else ""
    return top, sub


def _rebuild_titles(top_group: str, sub_groups: list[str]) -> list[str]:
    titles: list[str] = []
    top_title = build_section_title(top_group) if top_group else ""
    if top_title:
        titles.append(top_title)
    if sub_groups:
        titles.append(" / ".join(prettify_folder_name(s) for s in sub_groups))
    return titles


def backfill_page(page_dir: Path, dry_run: bool, source_title_to_sid: dict[str, str]) -> dict:
    cfg_path = page_dir / "page_config.yaml"
    manifest_path = page_dir / ".photo_manifest.yaml"

    if not cfg_path.exists():
        return {"folder": page_dir.name, "status": "skip", "reason": "no page_config"}

    with open(cfg_path, encoding="utf-8") as f:
        cfg_data = yaml.safe_load(f) or {}

    if cfg_data.get("is_cover") or cfg_data.get("is_backcover"):
        return {"folder": page_dir.name, "status": "skip", "reason": "cover/backcover"}

    current_sid = str(cfg_data.get("section_id", "") or "")
    current_titles = list(cfg_data.get("section_titles", []) or [])
    current_subgroups = list(cfg_data.get("sub_group_ids", []) or [])

    needs_sid = not current_sid
    needs_titles = not current_titles
    # sub_group_ids: only fill if missing AND the manifest reveals real sub-groups.
    # An empty list is legitimate for sections whose photos live at the top level.

    if not (needs_sid or needs_titles):
        return {"folder": page_dir.name, "status": "ok"}

    manifest_sid = ""
    photos: dict = {}
    if manifest_path.exists():
        with open(manifest_path, encoding="utf-8") as f:
            manifest_data = yaml.safe_load(f) or {}
        manifest_sid = str(manifest_data.get("section_id", "") or "")
        photos = manifest_data.get("photos", {}) or {}

    # Manifest-less fallback: cross-reference section_titles[0] with source folders.
    # The user split a page (which created the broken state) but the manifest got
    # detached. The title still carries the date prefix, so we can resolve sid
    # via .album_meta.yaml of the matching source group.
    if not manifest_sid and current_titles:
        manifest_sid = source_title_to_sid.get(current_titles[0], "")

    if not manifest_sid and not photos:
        return {"folder": page_dir.name, "status": "orphan", "reason": "no manifest"}

    # Collect source_group and sub_group lists from photo source_paths
    top_groups: list[str] = []
    sub_groups: list[str] = []
    for entry in photos.values():
        src = str((entry or {}).get("source_path", "") or "")
        top, sub = _split_source_path(src)
        if top and top not in top_groups:
            top_groups.append(top)
        if sub and sub not in sub_groups:
            sub_groups.append(sub)

    # Choose the dominant top group (page sections are isolated, so there should be one)
    top_group = top_groups[0] if top_groups else ""

    changes: dict[str, tuple] = {}

    if needs_sid and manifest_sid:
        changes["section_id"] = (current_sid, manifest_sid)
        cfg_data["section_id"] = manifest_sid

    # Backfill sub_group_ids opportunistically: only when both empty and recoverable.
    if not current_subgroups and sub_groups:
        changes["sub_group_ids"] = (current_subgroups, sub_groups)
        cfg_data["sub_group_ids"] = sub_groups

    if needs_titles and top_group:
        new_titles = _rebuild_titles(top_group, sub_groups)
        if new_titles:
            changes["section_titles"] = (current_titles, new_titles)
            cfg_data["section_titles"] = new_titles

    if not changes:
        return {
            "folder": page_dir.name,
            "status": "orphan",
            "reason": "manifest carries no recoverable info",
        }

    if not dry_run:
        with open(cfg_path, "w", encoding="utf-8") as f:
            yaml.dump(cfg_data, f, allow_unicode=True, default_flow_style=False)

    return {"folder": page_dir.name, "status": "fixed", "changes": changes}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("workspace", type=Path, help="Workspace root (contains pagina_*/ folders)")
    ap.add_argument(
        "--source-root",
        type=Path,
        default=None,
        help=(
            "Source folder (contains the original YYYYMMDD_* event folders). "
            "Used as fallback for pages whose manifest is missing but whose "
            "section_titles[0] still carries a date prefix. Defaults to the "
            "sibling folder derived from the '_album' suffix."
        ),
    )
    ap.add_argument("--dry-run", action="store_true", help="Report changes without writing")
    args = ap.parse_args()

    workspace: Path = args.workspace
    if not workspace.is_dir():
        print(f"ERROR: workspace path is not a directory: {workspace}", file=sys.stderr)
        return 2

    source_root: Path | None = args.source_root
    if source_root is None and workspace.name.endswith("_album"):
        guess = workspace.parent / workspace.name[: -len("_album")]
        if guess.is_dir():
            source_root = guess

    source_title_to_sid = _load_source_title_to_sid(source_root)
    if source_root and not source_title_to_sid:
        print(
            f"NOTE: source root {source_root} found but no .album_meta.yaml carries "
            f"section_id — manifest-less pages cannot be cross-referenced."
        )

    page_dirs = sorted(
        p for p in workspace.iterdir()
        if p.is_dir() and p.name.startswith("pagina_")
    )

    results = [backfill_page(p, args.dry_run, source_title_to_sid) for p in page_dirs]

    fixed = [r for r in results if r["status"] == "fixed"]
    orphans = [r for r in results if r["status"] == "orphan"]

    print(f"Scanned {len(results)} pages.")
    print(f"  fixed:   {len(fixed)}")
    print(f"  orphan:  {len(orphans)} (cannot recover automatically)")
    print()

    if fixed:
        verb = "WOULD FIX" if args.dry_run else "FIXED"
        for r in fixed:
            print(f"{verb}: {r['folder']}")
            for field_name, (before, after) in r["changes"].items():
                print(f"    {field_name}: {before!r} → {after!r}")
        print()

    if orphans:
        print("Pages that could not be recovered (manifest missing or empty):")
        for r in orphans:
            print(f"  {r['folder']}: {r['reason']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
