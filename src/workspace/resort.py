"""Resort workspace content pages by section date.

Reads existing page_configs, groups by section_id, derives a sort key per
section, and renames page folders + updates page_number in page_config.yaml
while preserving ALL other state.

Rename strategy: same atomic phase-1/phase-2 pattern used in workspace_manager.
"""

from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path

import yaml

from src.utils.naming import build_section_title

logger = logging.getLogger("album.resort")


def _backfill_empty_section_ids(workspace: Path, source_root: Path | None) -> int:
    """Recover section_id for pages where page_config.yaml has it empty.

    Strategy: cross-reference section_titles[0] against the canonical title
    built from each source folder name (build_section_title). When a match is
    found, copy section_id from the source's .album_meta.yaml into the page's
    page_config.yaml. Returns number of pages fixed.

    Idempotent: pages that already have a section_id are skipped. Pages whose
    title cannot be matched (or whose source folder lacks .album_meta.yaml)
    are left untouched — resort_sections mints a synthetic per-page sid for
    those so they don't collapse into a single super-group.
    """
    if source_root is None or not source_root.is_dir():
        return 0

    title_to_sid: dict[str, str] = {}
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
        if title and title not in title_to_sid:
            title_to_sid[title] = sid

    if not title_to_sid:
        return 0

    fixed = 0
    for entry in workspace.iterdir():
        if not entry.is_dir() or not entry.name.startswith("pagina_"):
            continue
        cfg_path = entry / "page_config.yaml"
        if not cfg_path.exists():
            continue
        try:
            with open(cfg_path, encoding="utf-8") as f:
                cfg_data = yaml.safe_load(f) or {}
        except Exception:
            continue
        if cfg_data.get("is_cover") or cfg_data.get("is_backcover"):
            continue
        if str(cfg_data.get("section_id", "") or ""):
            continue
        titles = list(cfg_data.get("section_titles", []) or [])
        if not titles:
            continue
        sid = title_to_sid.get(titles[0])
        if not sid:
            continue
        cfg_data["section_id"] = sid
        try:
            with open(cfg_path, "w", encoding="utf-8") as f:
                yaml.dump(cfg_data, f, allow_unicode=True, default_flow_style=False)
            fixed += 1
        except Exception as exc:
            logger.warning(f"Failed persisting section_id for {entry.name}: {exc}")
    return fixed


def _parse_dd_mm_yyyy(date_str: str) -> tuple[int, int, int] | None:
    """Parse 'DD/MM/YYYY' into (YYYY, MM, DD) for comparison. Returns None on failure."""
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", date_str.strip())
    if m:
        return (int(m.group(3)), int(m.group(2)), int(m.group(1)))
    return None


def _parse_section_title_date(section_titles: list[str]) -> tuple[int, int, int] | None:
    """Try to extract (YYYY, MM, DD) from 'DD/MM/YYYY - Name' in section_titles[0]."""
    if not section_titles:
        return None
    title = section_titles[0]
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})\b", title)
    if m:
        return (int(m.group(3)), int(m.group(2)), int(m.group(1)))
    return None


def _exif_date_from_source(source_path_str: str, source_root: Path | None) -> float | None:
    """Open the original source JPG and read EXIF DateTimeOriginal → float timestamp.

    Returns None if unavailable.
    """
    if not source_path_str:
        return None

    # Resolve source path
    candidate: Path | None = None
    if source_root is not None:
        candidate = (source_root / source_path_str).resolve()
        if not candidate.is_file():
            candidate = None

    if candidate is None:
        # Try as absolute path
        try:
            abs_candidate = Path(source_path_str)
            if abs_candidate.is_file():
                candidate = abs_candidate
        except Exception:
            pass

    if candidate is None:
        return None

    try:
        from PIL import Image
        with Image.open(candidate) as img:
            exif = img.getexif()
            # Tag 36867 = DateTimeOriginal
            dto = exif.get(36867)
            if dto:
                import datetime
                dt = datetime.datetime.strptime(dto, "%Y:%m:%d %H:%M:%S")
                return dt.timestamp()
    except Exception:
        pass
    return None


def _mtime_from_source(source_path_str: str, source_root: Path | None) -> float | None:
    """Return mtime of source file as fallback."""
    if not source_path_str:
        return None
    candidate: Path | None = None
    if source_root is not None:
        candidate = (source_root / source_path_str).resolve()
        if not candidate.is_file():
            candidate = None
    if candidate is None:
        try:
            abs_candidate = Path(source_path_str)
            if abs_candidate.is_file():
                candidate = abs_candidate
        except Exception:
            pass
    if candidate is None:
        return None
    try:
        return candidate.stat().st_mtime
    except Exception:
        return None


def resort_sections(workspace: Path, source_root: Path | None = None) -> dict:
    """Resort content pages by section_date, preserving intra-section order.

    Sort key per section (P17):
      1. section_date from page_config (DD/MM/YYYY).
      2. Date parsed from section_titles[0] prefix 'DD/MM/YYYY - Name'.
      3. Median EXIF DateTimeOriginal of source photos via manifest.
      4. mtime of source file.
      5. section_id as stable final fallback.

    Tie-break: current section order (stable sort).

    Returns:
        {
          "success": bool,
          "error": str | None,
          "renamed_pages": [{"old_id": str, "new_id": str}, ...],
          "focus_section_id": str | None,
        }
    """
    folder_pattern = re.compile(r"^pagina_(\d+)_(.+)$")

    try:
        # ── 0. Recover empty section_id from source .album_meta.yaml ─────────
        # Pages created by "Explotar página en dos" before the fix landed have
        # section_id=''. Without this recovery, every such page would collapse
        # into the same "" super-group below, defeating the resort entirely.
        recovered = _backfill_empty_section_ids(workspace, source_root)
        if recovered:
            logger.info(f"Recovered section_id for {recovered} orphan pages")

        # ── 1. Collect all content pages ────────────────────────────────────
        entries: list[tuple[Path, dict]] = []
        for entry in workspace.iterdir():
            if not entry.is_dir():
                continue
            cfg_path = entry / "page_config.yaml"
            if not cfg_path.exists():
                continue
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg_data = yaml.safe_load(f) or {}
            if cfg_data.get("is_cover") or cfg_data.get("is_backcover"):
                continue
            entries.append((entry, cfg_data))

        if not entries:
            return {"success": True, "error": None, "renamed_pages": [], "focus_section_id": None}

        # Sort by current page_number to establish stable intra-section order
        entries.sort(key=lambda x: (x[1].get("page_number", 0), x[0].name))

        # ── 2. Group pages by section_id, preserving intra-section order ────
        # section_id → list of (entry_path, cfg_data) in page order.
        # For pages still missing a section_id, mint a synthetic per-page sid
        # so each orphan stays its own one-page "section" instead of getting
        # collapsed into a single "" super-group that the sort cannot break up.
        from collections import OrderedDict
        sections: OrderedDict[str, list[tuple[Path, dict]]] = OrderedDict()
        for entry, cfg_data in entries:
            sid = str(cfg_data.get("section_id", "") or "")
            if not sid:
                sid = f"__orphan__{entry.name}"
            if sid not in sections:
                sections[sid] = []
            sections[sid].append((entry, cfg_data))

        # ── 3. Compute sort key per section ─────────────────────────────────
        def _section_sort_key(sid: str, pages: list[tuple[Path, dict]]) -> tuple:
            # Use first page as representative (all pages in a section share the date)
            first_cfg = pages[0][1]
            first_path = pages[0][0]

            # Priority 1: section_date field
            section_date_str = str(first_cfg.get("section_date", "") or "")
            if section_date_str:
                parsed = _parse_dd_mm_yyyy(section_date_str)
                if parsed:
                    return (0, parsed, 0.0, sid)

            # Priority 2: section_titles[0] date prefix
            section_titles = list(first_cfg.get("section_titles", []) or [])
            title_date = _parse_section_title_date(section_titles)
            if title_date:
                return (1, title_date, 0.0, sid)

            # Priority 3 & 4: EXIF / mtime from manifest source photos
            manifest_path = first_path / ".photo_manifest.yaml"
            source_timestamps: list[float] = []
            if manifest_path.exists():
                try:
                    with open(manifest_path, encoding="utf-8") as f:
                        mdata = yaml.safe_load(f) or {}
                    for _photo_name, photo_entry in (mdata.get("photos", {}) or {}).items():
                        src_path_str = str(photo_entry.get("source_path", "") or "")
                        ts = _exif_date_from_source(src_path_str, source_root)
                        if ts is None:
                            ts = _mtime_from_source(src_path_str, source_root)
                        if ts is not None:
                            source_timestamps.append(ts)
                except Exception as exc:
                    logger.debug(f"Manifest read failed for {first_path.name}: {exc}")

            if source_timestamps:
                import statistics
                median_ts = statistics.median(sorted(source_timestamps))
                return (2, (0, 0, 0), median_ts, sid)

            # Priority 5: section_id stable fallback
            return (3, (0, 0, 0), 0.0, sid)

        # Build (sort_key, current_index, sid) list and stable-sort
        section_items = list(sections.items())
        indexed = [(i, sid, pages) for i, (sid, pages) in enumerate(section_items)]
        indexed.sort(key=lambda x: (_section_sort_key(x[1], x[2]), x[0]))

        # Ordered list of section_id after resort
        sorted_section_ids = [x[1] for x in indexed]

        # ── 4. Build new ordered page list ───────────────────────────────────
        new_ordered_pages: list[tuple[Path, dict]] = []
        for sid in sorted_section_ids:
            new_ordered_pages.extend(sections[sid])

        # ── 5. Check if anything needs to change ────────────────────────────
        start_num = min(d.get("page_number", 1) for _, d in entries)
        new_numbers = {
            entry.name: start_num + i
            for i, (entry, _) in enumerate(new_ordered_pages)
        }

        needs_rename = [
            (entry, cfg_data)
            for entry, cfg_data in new_ordered_pages
            if cfg_data.get("page_number") != new_numbers[entry.name]
        ]

        if not needs_rename:
            return {
                "success": True,
                "error": None,
                "renamed_pages": [],
                "focus_section_id": sorted_section_ids[0] if sorted_section_ids else None,
            }

        # ── 6. Phase-1: rename to tmp names ──────────────────────────────────
        uid = uuid.uuid4().hex[:8]
        tmp_mapping: dict[str, Path] = {}
        for entry, _ in needs_rename:
            tmp_name = f"_resort_tmp_{uid}_{entry.name}"
            tmp_path = workspace / tmp_name
            entry.rename(tmp_path)
            tmp_mapping[entry.name] = tmp_path
            logger.info(f"resort phase-1: {entry.name} → {tmp_name}")

        # ── 7. Phase-2: rename to final names, update page_number ────────────
        renamed_pages: list[dict] = []
        for entry, cfg_data in needs_rename:
            tmp_path = tmp_mapping[entry.name]
            new_num = new_numbers[entry.name]

            m = folder_pattern.match(entry.name)
            slug = m.group(2) if m else entry.name
            new_folder_name = f"pagina_{new_num:02d}_{slug}"
            new_path = workspace / new_folder_name
            tmp_path.rename(new_path)
            logger.info(f"resort phase-2: {tmp_path.name} → {new_folder_name}")

            cfg_path = new_path / "page_config.yaml"
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            data["page_number"] = new_num
            if "photo_captions" not in data:
                data["photo_captions"] = {}
            with open(cfg_path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, allow_unicode=True, default_flow_style=False)

            renamed_pages.append({"old_id": entry.name, "new_id": new_folder_name})

        focus_section_id = sorted_section_ids[0] if sorted_section_ids else None

        return {
            "success": True,
            "error": None,
            "renamed_pages": renamed_pages,
            "focus_section_id": focus_section_id,
        }

    except Exception as exc:
        logger.error(f"resort_sections failed: {exc}")
        return {
            "success": False,
            "error": str(exc),
            "renamed_pages": [],
            "focus_section_id": None,
        }
