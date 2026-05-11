"""Auto-updater for the self-hosted PDF.js vendor files.

Checks npm registry for the latest pdfjs-dist v3.x release and silently
updates the local files if a newer version is available.
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

_NPM_REGISTRY_URL = "https://registry.npmjs.org/pdfjs-dist"
_JSDELIVR_BASE = "https://cdn.jsdelivr.net/npm/pdfjs-dist@{version}/build"

# Minimum expected file sizes (bytes) — guards against HTML error pages
_MIN_SIZE_PDF_JS = 50 * 1024        # 50 KB  (actual: ~313 KB)
_MIN_SIZE_PDF_WORKER = 200 * 1024   # 200 KB (actual: ~1 MB)


def _parse_version(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in v.split("."))


def _read_current_version(vendor_dir: Path) -> str:
    version_file = vendor_dir / "VERSION"
    if not version_file.exists():
        return "0.0.0"
    return version_file.read_text(encoding="utf-8").strip()


def _fetch_latest_version(target_major: int, timeout: float) -> str:
    """Return the latest semver string matching target_major from the npm registry."""
    with urllib.request.urlopen(_NPM_REGISTRY_URL, timeout=timeout) as resp:
        data = json.loads(resp.read())

    pattern = re.compile(rf"^{target_major}\.\d+\.\d+$")
    candidates = [v for v in data["versions"] if pattern.match(v)]
    if not candidates:
        raise ValueError(f"No v{target_major}.x versions found on npm registry")

    return max(candidates, key=_parse_version)


def _download_file(url: str, dest: Path, timeout: float) -> None:
    """Download url to dest (overwrites if exists)."""
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        content = resp.read()
    dest.write_bytes(content)


def check_and_update_pdfjs(
    vendor_dir: Path,
    target_major: int = 3,
    timeout: float = 3.0,
) -> dict:
    """Check npm registry for the latest pdfjs-dist v{target_major}.x.x and
    update the local files if a newer version is available.

    Returns dict: {"checked": bool, "updated": bool, "from": str|None,
                   "to": str|None, "error": str|None}
    Never raises — all failures fall back to the existing version.
    """
    current = _read_current_version(vendor_dir)
    result: dict = {
        "checked": False,
        "updated": False,
        "from": current,
        "to": None,
        "error": None,
    }

    tmp_pdf = vendor_dir / "pdf.min.js.tmp"
    tmp_worker = vendor_dir / "pdf.worker.min.js.tmp"

    try:
        latest = _fetch_latest_version(target_major, timeout)
        result["checked"] = True

        if _parse_version(latest) <= _parse_version(current):
            result["to"] = current
            logger.debug("PDF.js is up to date (%s)", current)
            return result

        logger.info("PDF.js update available: %s → %s. Downloading…", current, latest)
        base = _JSDELIVR_BASE.format(version=latest)

        # Download to temp files
        _download_file(f"{base}/pdf.min.js", tmp_pdf, timeout=30.0)
        _download_file(f"{base}/pdf.worker.min.js", tmp_worker, timeout=60.0)

        # Validate sizes
        pdf_size = tmp_pdf.stat().st_size
        worker_size = tmp_worker.stat().st_size

        if pdf_size < _MIN_SIZE_PDF_JS:
            raise ValueError(
                f"pdf.min.js download too small ({pdf_size} bytes); likely an error page"
            )
        if worker_size < _MIN_SIZE_PDF_WORKER:
            raise ValueError(
                f"pdf.worker.min.js download too small ({worker_size} bytes); likely an error page"
            )

        # Atomic replace
        os.replace(tmp_pdf, vendor_dir / "pdf.min.js")
        os.replace(tmp_worker, vendor_dir / "pdf.worker.min.js")

        # Update VERSION last — only after both files are in place
        (vendor_dir / "VERSION").write_text(latest, encoding="utf-8")

        result["updated"] = True
        result["to"] = latest
        logger.info("PDF.js updated to %s", latest)

    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
        logger.debug("PDF.js update check failed: %s", exc)
        # Clean up temp files if they exist
        for tmp in (tmp_pdf, tmp_worker):
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass

    return result
