"""Non-destructive sync between source folder and existing workspace.

Detects added/removed photos, renamed/new/removed sections, and applies
changes to the workspace while preserving manual page edits (splits,
deletions, completed flags, featured/hero photos, layout_seed, captions,
section title overrides).

Differs from `regenerate_album` (which wipes the workspace and rebuilds
from scratch).
"""

from __future__ import annotations

import logging
import random
import re
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from src.ingestion.downsampler import downsample_image
from src.ingestion.scanner import scan_directory
from src.ingestion.sorter import sort_photos
from src.utils.naming import (
    build_section_title,
    extract_date_from_folder,
    folder_name_to_slug,
    prettify_folder_name,
)
from src.workspace.config import (
    GlobalConfig,
    PageConfig,
    read_global_config,
    read_page_configs,
    write_global_config,
    write_page_configs,
)
from src.workspace.manifest import (
    PageManifest,
    PhotoManifestEntry,
    collect_workspace_manifests,
    compute_photo_signature,
    read_page_manifest,
    relative_source_path,
    workspace_has_manifests,
    write_page_manifest,
)
from src.workspace.reconciler import _sub_group_from_source_path
from src.workspace.tombstones import (
    read_tombstones,
    remove_tombstone,
    rewrite_section_paths as rewrite_tombstone_section_paths,
)

if TYPE_CHECKING:
    from src.ingestion.scanner import PhotoInfo

logger = logging.getLogger("album.syncer")


@dataclass
class AddedPhoto:
    source_rel: str
    section_id: str
    source_group: str


@dataclass
class RemovedPhoto:
    image_name: str
    page_folder: str
    source_rel: str


@dataclass
class RenamedSection:
    section_id: str
    old_title: str
    new_title: str


@dataclass
class NewSection:
    section_id: str
    source_group: str
    title: str
    photo_count: int


@dataclass
class RemovedSection:
    section_id: str
    title: str
    page_count: int


@dataclass
class SyncDiff:
    added_photos: list[AddedPhoto] = field(default_factory=list)
    removed_photos: list[RemovedPhoto] = field(default_factory=list)
    renamed_sections: list[RenamedSection] = field(default_factory=list)
    new_sections: list[NewSection] = field(default_factory=list)
    removed_sections: list[RemovedSection] = field(default_factory=list)
    has_manifests: bool = True

    def is_empty(self) -> bool:
        return (
            not self.added_photos
            and not self.removed_photos
            and not self.renamed_sections
            and not self.new_sections
            and not self.removed_sections
        )

    def to_dict(self) -> dict:
        return {
            "has_manifests": self.has_manifests,
            "added_photos": [
                {"source_rel": a.source_rel, "source_group": a.source_group}
                for a in self.added_photos
            ],
            "removed_photos": [
                {
                    "image_name": r.image_name,
                    "page_folder": r.page_folder,
                    "source_rel": r.source_rel,
                }
                for r in self.removed_photos
            ],
            "renamed_sections": [
                {
                    "section_id": rn.section_id,
                    "old_title": rn.old_title,
                    "new_title": rn.new_title,
                }
                for rn in self.renamed_sections
            ],
            "new_sections": [
                {
                    "section_id": ns.section_id,
                    "source_group": ns.source_group,
                    "title": ns.title,
                    "photo_count": ns.photo_count,
                }
                for ns in self.new_sections
            ],
            "removed_sections": [
                {"section_id": rs.section_id, "title": rs.title, "page_count": rs.page_count}
                for rs in self.removed_sections
            ],
            "summary": {
                "added": len(self.added_photos),
                "removed": len(self.removed_photos),
                "renamed": len(self.renamed_sections),
                "new_sections": len(self.new_sections),
                "removed_sections": len(self.removed_sections),
            },
        }


# ── Diff computation ─────────────────────────────────────────────────────────


def _read_meta(folder: Path) -> dict:
    import yaml
    meta_path = folder / ".album_meta.yaml"
    if not meta_path.exists():
        return {}
    try:
        with open(meta_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def _write_meta(folder: Path, data: dict) -> None:
    import yaml
    meta_path = folder / ".album_meta.yaml"
    try:
        with open(meta_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True)
    except Exception as e:
        logger.error(f"Failed writing meta {meta_path}: {e}")


def _ensure_source_section_id(source_root: Path, group: str) -> tuple[str, bool]:
    """Return (section_id, was_new). Persist to .album_meta.yaml of group folder."""
    folder = source_root / group
    if not folder.is_dir():
        return uuid.uuid4().hex, True
    meta = _read_meta(folder)
    sid = str(meta.get("section_id", "") or "")
    if sid:
        return sid, False
    sid = uuid.uuid4().hex
    meta["section_id"] = sid
    _write_meta(folder, meta)
    return sid, True


def _section_id_to_workspace_pages(
    pages: list[PageConfig],
) -> dict[str, list[PageConfig]]:
    out: dict[str, list[PageConfig]] = {}
    for p in pages:
        if p.is_cover or p.is_backcover:
            continue
        if not p.section_id:
            continue
        out.setdefault(p.section_id, []).append(p)
    return out


def _backfill_workspace_section_ids(
    workspace: Path,
    pages: list[PageConfig],
    source_root: Path,
    persist: bool = True,
) -> bool:
    """If pages lack section_id but match a source group by title, fill it.

    Returns True if any page was updated.

    When ``persist`` is True (the default), the recovered section_id is also
    written back to page_config.yaml so the recovery survives across runs.
    Earlier behaviour left the fix in memory only, which meant every sync had
    to re-discover the same orphans (and any sort step that ran without the
    backfill, e.g. resort_sections, still saw section_id='').
    """
    changed = False
    title_to_sid: dict[str, str] = {}
    if source_root.is_dir():
        for group_dir in source_root.iterdir():
            if not group_dir.is_dir():
                continue
            if group_dir.name.lower() in ("portada", "contraportada"):
                continue
            title = build_section_title(group_dir.name)
            sid, _ = _ensure_source_section_id(source_root, group_dir.name)
            title_to_sid[title] = sid

    recovered: list[PageConfig] = []
    for p in pages:
        if p.is_cover or p.is_backcover or p.section_id:
            continue
        title = p.section_titles[0] if p.section_titles else ""
        sid = title_to_sid.get(title)
        if sid:
            p.section_id = sid
            recovered.append(p)
            changed = True

    if changed and persist and recovered:
        try:
            write_page_configs(recovered)
        except Exception as exc:
            logger.warning(f"Failed persisting recovered section_ids: {exc}")
    return changed


def _folder_section_id_lookup(pages: list[PageConfig]) -> dict[str, str]:
    """folder name → section_id (from PageConfig, the source of truth)."""
    return {p.folder.name: (p.section_id or "") for p in pages}


def _compute_path_rewrite_map(
    manifests: list[PageManifest],
    group_to_sid: dict[str, str],
    folder_to_sid: dict[str, str],
) -> dict[tuple[str, str], str]:
    """Find (section_id, old_prefix) → new_prefix rewrites for renamed sections.

    A rewrite is needed when a manifest entry's first path component (the
    source folder name) no longer matches the current source group folder
    for that section_id. This happens when the user renames a source folder
    in disk; without rewriting, every photo in the section looks "removed
    from old path, added at new path".
    """
    sid_to_new_group: dict[str, str] = {sid: group for group, sid in group_to_sid.items()}
    rewrite_map: dict[tuple[str, str], str] = {}
    for m in manifests:
        sid = m.section_id or folder_to_sid.get(m.folder.name, "")
        if not sid:
            continue
        new_group = sid_to_new_group.get(sid)
        if not new_group:
            continue
        for entry in m.photos.values():
            sp = entry.source_path
            if not sp:
                continue
            head, sep, _tail = sp.partition("/")
            if not sep:
                continue
            if head != new_group:
                rewrite_map[(sid, head)] = new_group
    return rewrite_map


def _apply_rewrite(path: str, section_id: str, rewrite_map: dict[tuple[str, str], str]) -> str:
    """Return path with its first component substituted per rewrite_map (if any)."""
    head, sep, tail = path.partition("/")
    if not sep:
        return path
    new_prefix = rewrite_map.get((section_id, head))
    if new_prefix is None or new_prefix == head:
        return path
    return f"{new_prefix}/{tail}"


def compute_sync_diff(source_root: Path, workspace: Path) -> SyncDiff:
    """Compare source vs workspace. Returns SyncDiff. Does NOT mutate state."""
    diff = SyncDiff(has_manifests=workspace_has_manifests(workspace))

    cfg = read_global_config(workspace)
    pages = read_page_configs(workspace, cfg)

    if source_root.is_dir():
        _backfill_workspace_section_ids(workspace, pages, source_root)

    scan = scan_directory(source_root)
    sorted_photos = sort_photos(scan.photos)

    # Group source photos by source_group
    source_groups: dict[str, list["PhotoInfo"]] = {}
    for ph in sorted_photos:
        source_groups.setdefault(ph.source_group, []).append(ph)

    # Resolve section_id for each source group
    group_to_sid: dict[str, str] = {}
    for group in source_groups:
        sid, _ = _ensure_source_section_id(source_root, group)
        group_to_sid[group] = sid

    sid_to_pages = _section_id_to_workspace_pages(pages)
    sid_to_existing_titles: dict[str, str] = {
        sid: (group_pages[0].section_titles[0] if group_pages and group_pages[0].section_titles else "")
        for sid, group_pages in sid_to_pages.items()
    }

    # Build set of source rel paths currently in workspace manifests
    manifests = collect_workspace_manifests(workspace)
    folder_to_sid = _folder_section_id_lookup(pages)
    rewrite_map = _compute_path_rewrite_map(manifests, group_to_sid, folder_to_sid)
    tombstones_raw = read_tombstones(workspace)
    # Rewrite tombstone paths in memory so they match current source paths after
    # the user renamed the source folder of a section.
    tombstones = {
        (sid, _apply_rewrite(sp, sid, rewrite_map)) for (sid, sp) in tombstones_raw
    }

    manifest_source_paths: set[str] = set()
    folder_to_manifest: dict[str, PageManifest] = {}
    for m in manifests:
        folder_to_manifest[m.folder.name] = m
        sid = m.section_id or folder_to_sid.get(m.folder.name, "")
        for entry in m.photos.values():
            rewritten = _apply_rewrite(entry.source_path, sid, rewrite_map)
            manifest_source_paths.add(rewritten)

    # Build set of source rel paths currently on disk
    source_rel_set: set[str] = set()
    rel_to_photo: dict[str, "PhotoInfo"] = {}
    for ph in sorted_photos:
        rel = relative_source_path(source_root, ph.path)
        source_rel_set.add(rel)
        rel_to_photo[rel] = ph

    # Added photos: in source, not in manifests, not tombstoned
    for rel, ph in rel_to_photo.items():
        if rel in manifest_source_paths:
            continue
        sid = group_to_sid.get(ph.source_group, "")
        if (sid, rel) in tombstones or ("", rel) in tombstones:
            continue
        diff.added_photos.append(AddedPhoto(
            source_rel=rel, section_id=sid, source_group=ph.source_group,
        ))

    # Removed photos: in manifest but no longer in source (after path rewrite)
    for m in manifests:
        sid = m.section_id or folder_to_sid.get(m.folder.name, "")
        for img_name, entry in m.photos.items():
            if not entry.source_path:
                continue
            rewritten = _apply_rewrite(entry.source_path, sid, rewrite_map)
            if rewritten not in source_rel_set:
                diff.removed_photos.append(RemovedPhoto(
                    image_name=img_name,
                    page_folder=m.folder.name,
                    source_rel=entry.source_path,
                ))

    # Renamed sections: section_id matches but title differs
    for group, sid in group_to_sid.items():
        new_title = build_section_title(group)
        old_title = sid_to_existing_titles.get(sid)
        if old_title and old_title != new_title:
            diff.renamed_sections.append(RenamedSection(
                section_id=sid, old_title=old_title, new_title=new_title,
            ))

    # New sections: section_id in source but not in workspace pages
    for group, sid in group_to_sid.items():
        if sid in sid_to_pages:
            continue
        diff.new_sections.append(NewSection(
            section_id=sid,
            source_group=group,
            title=build_section_title(group),
            photo_count=len(source_groups.get(group, [])),
        ))

    # Removed sections: section_id in workspace but not in source
    source_sids = set(group_to_sid.values())
    for sid, group_pages in sid_to_pages.items():
        if sid in source_sids:
            continue
        title = group_pages[0].section_titles[0] if group_pages and group_pages[0].section_titles else "(sin título)"
        diff.removed_sections.append(RemovedSection(
            section_id=sid, title=title, page_count=len(group_pages),
        ))

    return diff


# ── Apply ────────────────────────────────────────────────────────────────────


def _next_image_seq(page_dir: Path) -> int:
    max_n = 0
    for p in page_dir.iterdir():
        m = re.match(r"img_(\d+)\.", p.name)
        if m:
            max_n = max(max_n, int(m.group(1)))
    return max_n + 1


def _renumber_pages(workspace: Path) -> None:
    """Renumber pagina_NN_* folders to be contiguous 1..N preserving order.

    Uses two-pass rename via temp prefix to avoid collisions.
    """
    page_dirs: list[Path] = []
    for p in sorted(workspace.iterdir()):
        if not p.is_dir():
            continue
        if p.name.lower() in ("portada", "contraportada"):
            continue
        if not p.name.startswith("pagina_"):
            continue
        page_dirs.append(p)

    page_dirs.sort(key=lambda p: p.name)

    tmp_renames: list[tuple[Path, Path]] = []
    for i, p in enumerate(page_dirs):
        m = re.match(r"pagina_\d+_(.*)", p.name)
        slug = m.group(1) if m else folder_name_to_slug(p.name)
        new_name = f"__tmp_pagina_{i:02d}_{slug}"
        tmp = p.with_name(new_name)
        p.rename(tmp)
        tmp_renames.append((tmp, p))

    final_pairs: list[tuple[Path, Path, int]] = []
    for i, (tmp, _orig) in enumerate(tmp_renames):
        m = re.match(r"__tmp_pagina_\d+_(.*)", tmp.name)
        slug = m.group(1) if m else "page"
        final_name = f"pagina_{i + 1:02d}_{slug}"
        final = tmp.with_name(final_name)
        tmp.rename(final)
        final_pairs.append((final, final, i + 1))

    # Update page_number in each page_config.yaml
    import yaml
    for final, _, page_num in final_pairs:
        cfg_path = final / "page_config.yaml"
        if not cfg_path.exists():
            continue
        try:
            with open(cfg_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            data["page_number"] = page_num
            with open(cfg_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
        except Exception as e:
            logger.warning(f"Failed updating page_number in {cfg_path}: {e}")


def _section_chronological_key(group_name: str) -> tuple[int, str]:
    """Sort key for a source group folder name. Date prefix first, then name."""
    date = extract_date_from_folder(group_name)
    if date:
        # date is DD/MM/YYYY → re-encode as YYYYMMDD int
        try:
            d, mo, y = date.split("/")
            return (int(f"{y}{mo}{d}"), group_name)
        except Exception:
            pass
    return (99999999, group_name)


def apply_sync(
    source_root: Path,
    workspace: Path,
    diff: SyncDiff,
    progress_callback=None,
) -> bool:
    """Apply a previously computed SyncDiff to the workspace.

    Strategy:
    - Remove obsolete photos (rebalance NOT applied — preserves splits).
    - Rename section titles in pages whose section_id matches a renamed source group.
    - For each new section: create one or more new page folders at the chronological
      insertion point.
    - For added photos in existing sections: append to the last page of that section;
      if it would exceed photos_per_page_max, create a new page at the end of that section.
    - Remove pages of removed sections.
    - Renumber all pages contiguously and rewrite configs/manifests.
    """

    def _cb(event: dict) -> None:
        if progress_callback:
            progress_callback(event)

    cfg = read_global_config(workspace)
    pages = read_page_configs(workspace, cfg)
    _backfill_workspace_section_ids(workspace, pages, source_root)

    max_per_page = cfg.photos_per_page_max

    # ── 0. Persist source-path rewrites for renamed sections ────────────
    # Same logic used in compute_sync_diff; this writes the new prefix to disk
    # so manifests and tombstones stay in sync with the source on apply.
    scan_for_rewrite = scan_directory(source_root)
    group_to_sid_apply: dict[str, str] = {}
    for ph in scan_for_rewrite.photos:
        if ph.source_group not in group_to_sid_apply:
            sid, _ = _ensure_source_section_id(source_root, ph.source_group)
            group_to_sid_apply[ph.source_group] = sid

    manifests_for_rewrite = collect_workspace_manifests(workspace)
    folder_to_sid_apply = _folder_section_id_lookup(pages)
    rewrite_map_apply = _compute_path_rewrite_map(
        manifests_for_rewrite, group_to_sid_apply, folder_to_sid_apply,
    )
    if rewrite_map_apply:
        for m in manifests_for_rewrite:
            sid = m.section_id or folder_to_sid_apply.get(m.folder.name, "")
            changed = False
            for entry in m.photos.values():
                new_path = _apply_rewrite(entry.source_path, sid, rewrite_map_apply)
                if new_path != entry.source_path:
                    entry.source_path = new_path
                    changed = True
            if changed:
                write_page_manifest(m)
        for (sid, old_prefix), new_prefix in rewrite_map_apply.items():
            rewrite_tombstone_section_paths(workspace, sid, old_prefix, new_prefix)

    # ── 1. Remove obsolete photos ────────────────────────────────────────
    _cb({"step": "removing_photos", "total": len(diff.removed_photos)})
    for i, rp in enumerate(diff.removed_photos, 1):
        page_dir = workspace / rp.page_folder
        if not page_dir.exists():
            continue
        img_path = page_dir / rp.image_name
        try:
            if img_path.exists():
                img_path.unlink()
            manifest = read_page_manifest(page_dir)
            if manifest and rp.image_name in manifest.photos:
                del manifest.photos[rp.image_name]
                write_page_manifest(manifest)
        except Exception as e:
            logger.warning(f"Failed removing {img_path}: {e}")
        _cb({"step": "removing_photos", "current": i, "total": len(diff.removed_photos)})

    # ── 2. Rebuild section titles for all content pages ─────────────────
    # Always rebuild section_titles from (section_id, sub_group_ids) so the
    # FS is the single source of truth: top-level folder rename and sub-folder
    # renames both propagate without manual override.
    sid_to_new_title = {r.section_id: r.new_title for r in diff.renamed_sections}
    pages = read_page_configs(workspace, cfg)
    _backfill_workspace_section_ids(workspace, pages, source_root)
    titles_changed = False

    # ── 2a. Backfill sub_group_ids for legacy pages (pre-2026-05-10 workspaces) ──
    # Pages created before sub_group_ids was introduced have an empty list.
    # Derive the sub-groups from each photo's source_path in the manifest so the
    # title-rebuild loop below can produce the two-element section_titles correctly.
    for p in pages:
        if p.is_cover or p.is_backcover:
            continue
        if p.sub_group_ids:
            continue  # already populated — idempotent guard
        manifest = read_page_manifest(p.folder)
        if manifest is None:
            logger.warning(f"No manifest found for {p.folder.name}; skipping sub_group_ids backfill")
            continue
        seen: list[str] = []
        for entry in manifest.photos.values():
            sg = _sub_group_from_source_path(entry.source_path)
            if sg and sg not in seen:
                seen.append(sg)
        if seen:
            p.sub_group_ids = seen
            titles_changed = True

    for p in pages:
        if p.is_cover or p.is_backcover:
            continue
        # Resolve current top-level title: prefer the renamed-source title
        # if section_id matches; otherwise keep current [0] (first sync of an
        # unchanged page just rewrites the same value).
        if p.section_id and p.section_id in sid_to_new_title:
            top_title = sid_to_new_title[p.section_id]
        elif p.section_titles:
            top_title = p.section_titles[0]
        else:
            top_title = ""
        new_titles = [top_title] if top_title else []
        if p.sub_group_ids:
            sub_label = " / ".join(prettify_folder_name(s) for s in p.sub_group_ids)
            new_titles.append(sub_label)
        if list(p.section_titles) != new_titles:
            p.section_titles = new_titles
            titles_changed = True
    if titles_changed or diff.renamed_sections:
        write_page_configs(pages)

    # ── 3. Remove pages of removed sections ─────────────────────────────
    if diff.removed_sections:
        removed_sids = {rs.section_id for rs in diff.removed_sections}
        pages = read_page_configs(workspace, cfg)
        _backfill_workspace_section_ids(workspace, pages, source_root)
        for p in pages:
            if p.section_id in removed_sids:
                try:
                    shutil.rmtree(p.folder)
                except Exception as e:
                    logger.warning(f"Failed removing section page {p.folder}: {e}")

    # ── 4. Add new photos to existing sections ──────────────────────────
    if diff.added_photos:
        _cb({"step": "adding_photos", "total": len(diff.added_photos)})
        pages = read_page_configs(workspace, cfg)
        _backfill_workspace_section_ids(workspace, pages, source_root)
        sid_to_pages = _section_id_to_workspace_pages(pages)

        # Group additions by section_id and source_group, preserving sort order
        scan = scan_directory(source_root)
        sorted_photos = sort_photos(scan.photos)
        rel_to_photo = {relative_source_path(source_root, ph.path): ph for ph in sorted_photos}

        existing_sids = set(sid_to_pages.keys())
        added_in_existing: dict[str, list[AddedPhoto]] = {}
        for ap in diff.added_photos:
            if ap.section_id in existing_sids:
                added_in_existing.setdefault(ap.section_id, []).append(ap)

        added_done = 0
        for sid, additions in added_in_existing.items():
            section_pages = sorted(sid_to_pages[sid], key=lambda p: p.page_number)
            if not section_pages:
                continue
            target_page = section_pages[-1]
            title_slug_match = re.match(r"pagina_\d+_(.*)", target_page.folder.name)
            title_slug = title_slug_match.group(1) if title_slug_match else "page"
            section_titles = list(target_page.section_titles)
            layout_mode = target_page.layout_mode

            # Sort additions chronologically
            ordered = []
            for ap in additions:
                ph = rel_to_photo.get(ap.source_rel)
                if ph is not None:
                    ordered.append((ph, ap))

            for ph, ap in ordered:
                manifest = read_page_manifest(target_page.folder) or PageManifest(
                    folder=target_page.folder, section_id=sid,
                )
                if len(manifest.photos) >= max_per_page:
                    # Create a new page at the end of the section
                    new_folder_name = f"pagina_{_next_global_seq(workspace):02d}_{title_slug}"
                    new_dir = workspace / new_folder_name
                    new_dir.mkdir(exist_ok=True)
                    sg = getattr(ph, "sub_group", "") or ""
                    new_sub_group_ids = [sg] if sg else []
                    new_titles = [section_titles[0]] if section_titles else []
                    if new_sub_group_ids:
                        new_titles.append(" / ".join(prettify_folder_name(s) for s in new_sub_group_ids))
                    new_pc = PageConfig(
                        folder=new_dir,
                        page_number=0,
                        photo_count=0,
                        section_titles=new_titles,
                        layout_mode=layout_mode,
                        section_id=sid,
                        sub_group_ids=new_sub_group_ids,
                    )
                    write_page_configs([new_pc])
                    target_page = new_pc
                    manifest = PageManifest(folder=new_dir, section_id=sid)
                else:
                    # Append sub_group to target_page if photo introduces a new one
                    sg = getattr(ph, "sub_group", "") or ""
                    if sg and sg not in target_page.sub_group_ids:
                        target_page.sub_group_ids = list(target_page.sub_group_ids) + [sg]
                        # rebuild title[1]
                        top = target_page.section_titles[0] if target_page.section_titles else ""
                        new_titles = [top] if top else []
                        if target_page.sub_group_ids:
                            new_titles.append(" / ".join(prettify_folder_name(s) for s in target_page.sub_group_ids))
                        target_page.section_titles = new_titles
                        write_page_configs([target_page])

                seq = _next_image_seq(target_page.folder)
                ext = ph.path.suffix.lower()
                if ext not in (".jpg", ".jpeg"):
                    ext = ".jpg"
                img_name = f"img_{seq:03d}{ext}"
                dst = target_page.folder / img_name
                if downsample_image(ph.path, dst) is not None:
                    mtime, sha = compute_photo_signature(ph.path)
                    manifest.photos[img_name] = PhotoManifestEntry(
                        image_name=img_name,
                        source_path=ap.source_rel,
                        source_mtime=mtime,
                        sha1=sha,
                    )
                    write_page_manifest(manifest)
                added_done += 1
                _cb({"step": "adding_photos", "current": added_done, "total": len(diff.added_photos)})

    # ── 5. Create new sections (chronological insertion) ────────────────
    if diff.new_sections:
        _cb({"step": "adding_sections", "total": len(diff.new_sections)})
        # Sort new sections chronologically by source_group date prefix
        new_sorted = sorted(
            diff.new_sections, key=lambda ns: _section_chronological_key(ns.source_group)
        )

        scan = scan_directory(source_root)
        sorted_photos = sort_photos(scan.photos)
        group_photos: dict[str, list["PhotoInfo"]] = {}
        for ph in sorted_photos:
            group_photos.setdefault(ph.source_group, []).append(ph)

        layout_modes = ["mesa_de_luz", "grid_compacto", "hibrido"]

        target_per_page = (cfg.photos_per_page_min + cfg.photos_per_page_max) // 2

        for idx, ns in enumerate(new_sorted, 1):
            photos_in = group_photos.get(ns.source_group, [])
            if not photos_in:
                continue
            title = ns.title
            title_slug = folder_name_to_slug(prettify_folder_name(ns.source_group))

            # Simple chunking: target_per_page per page
            chunk_size = max(1, target_per_page)
            chunks = [photos_in[i:i + chunk_size] for i in range(0, len(photos_in), chunk_size)]

            for chunk in chunks:
                seq = _next_global_seq(workspace)
                folder_name = f"pagina_{seq:02d}_{title_slug}"
                page_dir = workspace / folder_name
                page_dir.mkdir(exist_ok=True)
                manifest_entries: dict[str, PhotoManifestEntry] = {}
                for img_seq, ph in enumerate(chunk, start=1):
                    ext = ph.path.suffix.lower()
                    if ext not in (".jpg", ".jpeg"):
                        ext = ".jpg"
                    img_name = f"img_{img_seq:03d}{ext}"
                    dst = page_dir / img_name
                    if downsample_image(ph.path, dst) is not None:
                        mtime, sha = compute_photo_signature(ph.path)
                        manifest_entries[img_name] = PhotoManifestEntry(
                            image_name=img_name,
                            source_path=relative_source_path(source_root, ph.path),
                            source_mtime=mtime,
                            sha1=sha,
                        )

                page_sub_groups: list[str] = []
                for ph in chunk:
                    sg = getattr(ph, "sub_group", "") or ""
                    if sg and sg not in page_sub_groups:
                        page_sub_groups.append(sg)
                titles = [title]
                if page_sub_groups:
                    titles.append(" / ".join(prettify_folder_name(s) for s in page_sub_groups))

                pc = PageConfig(
                    folder=page_dir,
                    page_number=0,
                    photo_count=len(manifest_entries),
                    section_titles=titles,
                    layout_mode=random.choice(layout_modes),
                    section_id=ns.section_id,
                    sub_group_ids=list(page_sub_groups),
                )
                write_page_configs([pc])
                write_page_manifest(PageManifest(
                    folder=page_dir, section_id=ns.section_id, photos=manifest_entries,
                ))

            _cb({"step": "adding_sections", "current": idx, "total": len(diff.new_sections)})

    # ── 6. Reorder pages: cover → sections in chronological order → backcover, then renumber ──
    _reorder_pages_chronologically(workspace, source_root)
    _renumber_pages(workspace)

    # Refresh photo_count in page configs based on disk state
    pages = read_page_configs(workspace, cfg)
    write_page_configs(pages)

    _cb({"step": "done"})
    return True


def _next_global_seq(workspace: Path) -> int:
    """Return next free pagina_NN sequence number not currently used."""
    used = set()
    for p in workspace.iterdir():
        if not p.is_dir():
            continue
        m = re.match(r"(?:__tmp_)?pagina_(\d+)_", p.name)
        if m:
            used.add(int(m.group(1)))
    n = 1
    while n in used:
        n += 1
    return n


def _reorder_pages_chronologically(workspace: Path, source_root: Path) -> None:
    """Rename page folders so chronological order by section is respected.

    Pages of the same section keep their existing relative order (preserves splits).
    New sections inserted in chronological order via section_id → source_group lookup.
    """
    cfg = read_global_config(workspace)
    pages = read_page_configs(workspace, cfg)
    _backfill_workspace_section_ids(workspace, pages, source_root)

    # Build sid → source_group from source_root
    sid_to_group: dict[str, str] = {}
    if source_root.is_dir():
        for d in source_root.iterdir():
            if not d.is_dir():
                continue
            if d.name.lower() in ("portada", "contraportada"):
                continue
            sid = _read_meta(d).get("section_id")
            if sid:
                sid_to_group[str(sid)] = d.name

    def section_key(p: PageConfig) -> tuple:
        if p.is_cover:
            return (0,)
        if p.is_backcover:
            return (3,)
        group = sid_to_group.get(p.section_id, "")
        if group:
            return (1, _section_chronological_key(group), p.page_number)
        # Orphan page (section_id still unresolved after backfill). Use the
        # date prefix of section_titles[0] so it interleaves chronologically
        # with the rest instead of being dumped at the end of the album.
        title = p.section_titles[0] if p.section_titles else ""
        m = re.match(r"^(\d{2})/(\d{2})/(\d{4})\b", title)
        if m:
            date_int = int(f"{m.group(3)}{m.group(2)}{m.group(1)}")
            return (1, (date_int, title), p.page_number)
        return (2, (0, title), p.page_number)

    pages.sort(key=section_key)

    # Rename to temp names then to final names according to new order
    tmp_pairs: list[tuple[Path, PageConfig]] = []
    for i, p in enumerate(pages):
        if p.is_cover or p.is_backcover:
            continue
        m = re.match(r"pagina_\d+_(.*)", p.folder.name)
        slug = m.group(1) if m else folder_name_to_slug(p.folder.name)
        tmp_name = f"__tmp_pagina_{i:04d}_{slug}"
        tmp = p.folder.with_name(tmp_name)
        if p.folder.exists():
            p.folder.rename(tmp)
        tmp_pairs.append((tmp, p))

    seq = 1
    for tmp, p in tmp_pairs:
        m = re.match(r"__tmp_pagina_\d+_(.*)", tmp.name)
        slug = m.group(1) if m else "page"
        final_name = f"pagina_{seq:02d}_{slug}"
        final = tmp.with_name(final_name)
        tmp.rename(final)
        p.folder = final
        p.page_number = seq
        seq += 1
