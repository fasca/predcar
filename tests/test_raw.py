from pathlib import Path

import pytest

from predcar import raw


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
