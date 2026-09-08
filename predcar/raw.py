"""Immutable raw archive: data/raw/<source>/<YYYY-MM-DD>/<file> + MANIFEST.json (sha256).

Payloads are not versioned in git (too large); the manifest is, so every downstream
artefact can be traced back to an exact file and checksum.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, date, datetime
from pathlib import Path

import httpx

from predcar.paths import RAW_DIR

logger = logging.getLogger(__name__)

MANIFEST_NAME = "MANIFEST.json"
_CHUNK = 1 << 20


class RawArchiveError(RuntimeError):
    """A raw file is missing or does not match its manifest."""


def sha256_of(path: Path) -> str:
    """Return the hex sha256 digest of a file, streamed."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot_dir(source: str, day: date | None = None, root: Path = RAW_DIR) -> Path:
    """Directory for one dated snapshot of a source (created on demand)."""
    path = root / source / (day or datetime.now(UTC).date()).isoformat()
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_manifest(directory: Path) -> dict[str, dict]:
    """Read MANIFEST.json (filename → entry); empty dict if absent."""
    path = directory / MANIFEST_NAME
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _write_manifest(directory: Path, manifest: dict[str, dict]) -> None:
    with (directory / MANIFEST_NAME).open("w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True, ensure_ascii=False)
        fh.write("\n")


def register_file(directory: Path, filename: str, url: str | None = None) -> dict:
    """Add (or refresh) a file's checksum entry in the directory manifest.

    Args:
        directory: Snapshot directory containing the file.
        filename: File name inside the directory.
        url: Where the file came from, for traceability.

    Returns:
        The manifest entry that was written.
    """
    path = directory / filename
    if not path.is_file():
        raise RawArchiveError(f"cannot register missing file {path}")
    entry = {
        "url": url,
        "sha256": sha256_of(path),
        "size_bytes": path.stat().st_size,
        "downloaded_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    manifest = read_manifest(directory)
    manifest[filename] = entry
    _write_manifest(directory, manifest)
    return entry


def download(url: str, dest: Path, client: httpx.Client | None = None) -> Path:
    """Stream a URL to disk atomically: written to ``<dest>.part`` then renamed.

    Raises:
        RawArchiveError: if ``dest`` already exists (snapshots are immutable).
        httpx.HTTPStatusError: on any non-2xx status.
    """
    if dest.exists():
        raise RawArchiveError(
            f"{dest} already exists; raw snapshots are immutable (delete it explicitly "
            "or fetch into a new snapshot)"
        )
    part = dest.with_name(dest.name + ".part")
    own_client = client is None
    client = client or httpx.Client(follow_redirects=True, timeout=120)
    try:
        with client.stream("GET", url) as resp:
            resp.raise_for_status()
            with part.open("wb") as fh:
                for chunk in resp.iter_bytes(_CHUNK):
                    fh.write(chunk)
        part.replace(dest)
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    finally:
        if own_client:
            client.close()
    logger.info("downloaded %s -> %s (%d bytes)", url, dest, dest.stat().st_size)
    return dest


def archive(source: str, url: str, filename: str, client: httpx.Client | None = None) -> Path:
    """Download a file into today's snapshot of a source and register its checksum.

    Refuses to overwrite a file already present in the snapshot.
    """
    directory = snapshot_dir(source)
    dest = download(url, directory / filename, client)
    register_file(directory, filename, url)
    return dest


def latest_snapshot(source: str, root: Path = RAW_DIR) -> Path:
    """Most recent dated snapshot directory of a source."""
    base = root / source
    candidates = sorted(p for p in base.iterdir() if p.is_dir()) if base.is_dir() else []
    if not candidates:
        raise RawArchiveError(f"no raw snapshot for source '{source}' under {base}")
    return candidates[-1]


def verify(directory: Path) -> None:
    """Check that every manifest entry matches the file on disk."""
    manifest = read_manifest(directory)
    if not manifest:
        raise RawArchiveError(f"no {MANIFEST_NAME} in {directory}")
    for filename, entry in manifest.items():
        path = directory / filename
        if not path.is_file():
            raise RawArchiveError(f"{path} listed in manifest but missing")
        actual = sha256_of(path)
        if actual != entry["sha256"]:
            raise RawArchiveError(f"{path}: sha256 {actual} != manifest {entry['sha256']}")
