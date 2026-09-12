import gzip
from pathlib import Path

import httpx
import pytest

from predcar import raw


def _client(body: bytes = b"x,y\n1,2\n", status: int = 200) -> httpx.Client:
    return httpx.Client(
        transport=httpx.MockTransport(lambda req: httpx.Response(status, content=body))
    )


def test_download_is_atomic_and_refuses_overwrite(tmp_path: Path) -> None:
    dest = tmp_path / "a.csv"
    raw.download("https://example.org/a.csv", dest, _client())
    assert dest.read_bytes() == b"x,y\n1,2\n"
    assert not list(tmp_path.glob("*.part"))
    with pytest.raises(raw.RawArchiveError, match="immutable"):
        raw.download("https://example.org/a.csv", dest, _client(b"changed"))
    assert dest.read_bytes() == b"x,y\n1,2\n"


def test_failed_download_leaves_nothing_behind(tmp_path: Path) -> None:
    dest = tmp_path / "a.csv"
    with pytest.raises(httpx.HTTPStatusError):
        raw.download("https://example.org/a.csv", dest, _client(status=500))
    assert not dest.exists()
    assert not list(tmp_path.glob("*.part"))


def test_register_and_verify_roundtrip(tmp_path: Path) -> None:
    (tmp_path / "a.csv").write_text("x,y\n1,2\n")
    entry = raw.register_file(tmp_path, "a.csv", url="https://example.org/a.csv")
    assert entry["sha256"] == raw.sha256_of(tmp_path / "a.csv")
    assert raw.read_manifest(tmp_path)["a.csv"]["url"] == "https://example.org/a.csv"
    raw.verify(tmp_path)


def test_verify_detects_tampering(tmp_path: Path) -> None:
    (tmp_path / "a.csv").write_text("x,y\n1,2\n")
    raw.register_file(tmp_path, "a.csv")
    (tmp_path / "a.csv").write_text("x,y\n1,3\n")
    with pytest.raises(raw.RawArchiveError, match="sha256"):
        raw.verify(tmp_path)


def test_verify_detects_missing_file(tmp_path: Path) -> None:
    (tmp_path / "a.csv").write_text("x\n")
    raw.register_file(tmp_path, "a.csv")
    (tmp_path / "a.csv").unlink()
    with pytest.raises(raw.RawArchiveError, match="missing"):
        raw.verify(tmp_path)


def test_latest_snapshot_picks_most_recent_date(tmp_path: Path) -> None:
    for day in ("2026-01-01", "2026-03-01", "2025-12-31"):
        (tmp_path / "uk_dft" / day).mkdir(parents=True)
    assert raw.latest_snapshot("uk_dft", tmp_path).name == "2026-03-01"
    with pytest.raises(raw.RawArchiveError):
        raw.latest_snapshot("nl_rdw", tmp_path)


def test_compress_keeps_the_manifest_valid(tmp_path: Path) -> None:
    """Compressing an archived payload must not change its identity."""
    (tmp_path / "a.csv").write_text("x,y\n1,2\n")
    entry = raw.register_file(tmp_path, "a.csv")
    gz = raw.compress(tmp_path, "a.csv")

    assert gz.name == "a.csv.gz"
    assert not (tmp_path / "a.csv").exists()
    assert raw.sha256_of(gz) == entry["sha256"]
    raw.verify(tmp_path)
    assert raw.read_bytes(tmp_path, "a.csv") == b"x,y\n1,2\n"
    assert raw.resolve(tmp_path, "a.csv") == gz


def test_compress_is_idempotent_and_needs_a_file(tmp_path: Path) -> None:
    (tmp_path / "a.csv").write_text("x\n")
    raw.compress(tmp_path, "a.csv")
    assert raw.compress(tmp_path, "a.csv").name == "a.csv.gz"
    assert not list(tmp_path.glob("*.part"))
    with pytest.raises(raw.RawArchiveError, match="not found"):
        raw.compress(tmp_path, "missing.csv")


def test_verify_detects_tampering_of_a_compressed_payload(tmp_path: Path) -> None:
    (tmp_path / "a.csv").write_text("x,y\n1,2\n")
    raw.register_file(tmp_path, "a.csv")
    raw.compress(tmp_path, "a.csv")
    with gzip.open(tmp_path / "a.csv.gz", "wb") as fh:
        fh.write(b"x,y\n1,3\n")
    with pytest.raises(raw.RawArchiveError, match="sha256"):
        raw.verify(tmp_path)


def test_read_bytes_requires_one_of_the_two_forms(tmp_path: Path) -> None:
    assert raw.resolve(tmp_path, "a.csv") is None
    with pytest.raises(raw.RawArchiveError, match="not found"):
        raw.read_bytes(tmp_path, "a.csv")
