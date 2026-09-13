.PHONY: install fetch-uk fetch-nl fetch-de ingest-uk ingest-nl ingest-de compress-nl normalize score export site validate test lint

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

compress-nl:         ## Gzip the archived RDW payload so the month can be committed (~1.2 MB)
	uv run predcar compress nl

fetch-de:            ## Archive one KBA FZ 2 vintage: make fetch-de YEAR=2026
	uv run predcar fetch de --year $(YEAR)

ingest-de:           ## Parse the latest KBA vintage into data/silver/fleet_stock_de_kba_<year>.parquet
	uv run predcar ingest de

normalize:           ## Apply mapping/ → data/silver/fleet_stock.parquet, fail if coverage < 95 %
	uv run predcar normalize

score:               ## Indicators + score v1 → data/gold/ (parquet + ranking.csv)
	uv run predcar score

export:              ## Evidence bundle → reports/<date>/ (commit it so the remote reviewer can analyse real data)
	uv run predcar export

site:                ## Static site from the latest reports/<date>/gold/ → site/dist/
	uv run predcar site

validate:            ## Check silver invariants
	uv run predcar validate

test:
	uv run pytest tests/ -v

lint:
	uv run ruff check . && uv run ruff format --check .
