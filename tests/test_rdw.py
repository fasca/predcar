import json
from datetime import date
from pathlib import Path

import httpx
import polars as pl
import pytest

from predcar import raw, schemas
from predcar.config import load_sources_config
from predcar.ingest import rdw

PERIOD = date(2026, 9, 8)


def _rows(fixtures: Path) -> list[dict]:
    return json.loads((fixtures / "rdw_agg_page.json").read_text())


# --------------------------------------------------------------------------- query


def test_query_aggregates_server_side_and_never_projects_kenteken() -> None:
    params = rdw.build_query(limit=10, offset=20)
    assert "kenteken" not in json.dumps(params).lower()
    assert "count(*)" in params["$select"]
    assert "date_extract_y(datum_eerste_toelating_dt)" in params["$select"]
    assert "substring" not in params["$select"]  # datum_eerste_toelating is a Socrata Number
    assert params["$group"] == "merk,handelsbenaming,jaar"
    assert params["$order"] == params["$group"]  # stable offset paging
    assert params["$where"] == "voertuigsoort='Personenauto'"
    assert (params["$limit"], params["$offset"]) == ("10", "20")


def test_forbidden_field_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rdw, "COL_MAKE", "kenteken")
    with pytest.raises(rdw.RdwSchemaError, match="forbidden"):
        rdw.build_query()


# --------------------------------------------------------------------------- fetch


def test_fetch_rows_paginates_until_short_page(fixtures: Path) -> None:
    rows = _rows(fixtures)
    seen: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params["$offset"])
        seen.append(offset)
        return httpx.Response(200, json=rows[offset : offset + 3])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    out = rdw.fetch_rows("https://example.org/resource/m9d7-ebf2.json", client, page_size=3)
    assert out == rows
    assert seen == [0, 3, 6]  # last page has 1 row (< 3) → stop


def test_fetch_rows_rejects_non_array_payload() -> None:
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})))
    with pytest.raises(rdw.RdwSchemaError, match="JSON array"):
        rdw.fetch_rows("https://example.org/x.json", client)


def test_fetch_archives_rows_query_and_manifest(fixtures: Path, tmp_path: Path) -> None:
    rows = _rows(fixtures)
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=rows)))

    data_path = rdw.fetch(load_sources_config(), client, root=tmp_path)
    snapshot = data_path.parent
    assert snapshot.parent == tmp_path / rdw.SOURCE
    assert json.loads(data_path.read_text()) == rows
    query = json.loads((snapshot / rdw.QUERY_FILE).read_text())
    assert query["rows"] == len(rows) and "$group" in query["params"]
    assert set(raw.read_manifest(snapshot)) == {rdw.DATA_FILE, rdw.QUERY_FILE}
    raw.verify(snapshot)

    with pytest.raises(raw.RawArchiveError, match="immutable"):
        rdw.fetch(load_sources_config(), client, root=tmp_path)
    assert not list(snapshot.glob("*.part"))


def test_fetch_refuses_empty_response_without_writing(tmp_path: Path) -> None:
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[])))
    with pytest.raises(rdw.RdwSchemaError, match="empty"):
        rdw.fetch(load_sources_config(), client, root=tmp_path)
    assert not (tmp_path / rdw.SOURCE).exists() or not any((tmp_path / rdw.SOURCE).rglob("*"))


# --------------------------------------------------------------------------- parse


def test_parse_rows_to_fleet_stock(fixtures: Path) -> None:
    out = rdw.parse_rows(_rows(fixtures), PERIOD)
    schemas.check_fleet_stock(out)

    assert set(out["country"].to_list()) == {"NL"}
    assert set(out["period"].to_list()) == {PERIOD}
    assert out["status"].null_count() == out.height
    assert out["model_gen_raw"].null_count() == out.height

    m3_2002 = out.filter((pl.col("model_raw") == "M3") & (pl.col("year_first_reg") == 2002))
    assert m3_2002["count"].to_list() == [100]  # "M3" + "m3 " normalized and summed

    s2000 = out.filter(pl.col("model_raw") == "S2000")
    null_year = s2000.filter(pl.col("year_first_reg").is_null())
    assert null_year["count"].to_list() == [5]  # 1899 and "" → null-year bucket
    assert s2000.filter(pl.col("year_first_reg") == 2000)["count"].to_list() == [310]


def test_parse_rows_accepts_json_numbers() -> None:
    rows = [{"merk": "BMW", "handelsbenaming": "M3", "jaar": 2001, "n": 7}]
    out = rdw.parse_rows(rows, PERIOD)
    assert out["year_first_reg"].to_list() == [2001]
    assert out["count"].to_list() == [7]


def test_parse_rows_keeps_rows_without_trade_name_under_explicit_label() -> None:
    rows = [
        {"merk": "BMW", "handelsbenaming": "M3", "jaar": "2001", "n": "5"},
        {"merk": "BMW", "jaar": "1957", "n": "1"},  # Socrata omits a null handelsbenaming
        {"merk": "BMW", "n": "2"},  # no trade name, no year
    ]
    out = rdw.parse_rows(rows, PERIOD)
    missing = out.filter(pl.col("model_raw") == rdw.MODEL_MISSING).sort("year_first_reg")
    assert missing["count"].to_list() == [2, 1]
    assert missing["year_first_reg"].to_list() == [None, 1957]
    assert out["count"].sum() == 8


def test_parse_rows_rejects_empty_and_malformed() -> None:
    with pytest.raises(rdw.RdwSchemaError, match="empty"):
        rdw.parse_rows([], PERIOD)
    with pytest.raises(rdw.RdwSchemaError, match="missing columns"):
        rdw.parse_rows([{"merk": "BMW", "n": "1"}], PERIOD)
    with pytest.raises(rdw.RdwSchemaError, match="non-integer"):
        rdw.parse_rows([{"merk": "BMW", "handelsbenaming": "M3", "jaar": "2001", "n": "x"}], PERIOD)


# --------------------------------------------------------------------------- ingest


def _snapshot(fixtures: Path, tmp_path: Path, register: tuple[str, ...] | None = None) -> Path:
    snapshot = tmp_path / "raw" / rdw.SOURCE / PERIOD.isoformat()
    snapshot.mkdir(parents=True)
    (snapshot / rdw.DATA_FILE).write_bytes((fixtures / "rdw_agg_page.json").read_bytes())
    (snapshot / rdw.QUERY_FILE).write_text("{}")
    for name in register if register is not None else (rdw.DATA_FILE, rdw.QUERY_FILE):
        raw.register_file(snapshot, name)
    return snapshot


def test_ingest_snapshot_end_to_end(fixtures: Path, tmp_path: Path) -> None:
    out = rdw.ingest(_snapshot(fixtures, tmp_path), tmp_path / "silver")
    assert out.name == f"fleet_stock_nl_rdw_{PERIOD.isoformat()}.parquet"
    stock = pl.read_parquet(out)
    schemas.check_fleet_stock(stock)
    assert stock["count"].sum() == 575


@pytest.mark.parametrize("registered", [(rdw.QUERY_FILE,), (rdw.DATA_FILE,)])
def test_ingest_refuses_snapshot_missing_a_registered_file(
    fixtures: Path, tmp_path: Path, registered: tuple[str, ...]
) -> None:
    with pytest.raises(raw.RawArchiveError, match="incomplete"):
        rdw.ingest(_snapshot(fixtures, tmp_path, register=registered), tmp_path / "silver")


def test_ingest_refuses_snapshot_without_query_file(fixtures: Path, tmp_path: Path) -> None:
    snapshot = _snapshot(fixtures, tmp_path, register=(rdw.DATA_FILE,))
    (snapshot / rdw.QUERY_FILE).unlink()
    with pytest.raises(raw.RawArchiveError, match="query.json"):
        rdw.ingest(snapshot, tmp_path / "silver")
