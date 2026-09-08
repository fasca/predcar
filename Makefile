.PHONY: install fetch-uk fetch-nl ingest-uk ingest-nl validate test lint

install:
	uv sync

fetch-uk:            ## Download DfT/DVLA CSVs into data/raw/uk_dft/<date>/ with MANIFEST.json
	uv run predcar fetch uk

ingest-uk:           ## Parse latest raw UK files into data/silver/*.parquet
	uv run predcar ingest uk

fetch-nl:            ## Archive one aggregated RDW snapshot into data/raw/nl_rdw/<date>/
	uv run predcar fetch nl

ingest-nl:           ## Parse latest raw RDW snapshot into data/silver/fleet_stock_nl_rdw_<date>.parquet
	uv run predcar ingest nl

validate:            ## Check silver invariants
	uv run predcar validate

test:
	uv run pytest tests/ -v

lint:
	uv run ruff check . && uv run ruff format --check .
