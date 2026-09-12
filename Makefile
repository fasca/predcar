.PHONY: install fetch-uk fetch-nl ingest-uk ingest-nl normalize score export validate site site-dev test lint

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

normalize:           ## Apply mapping/ → data/silver/fleet_stock.parquet, fail if coverage < 95 %
	uv run predcar normalize

score:               ## Indicators + score v1 → data/gold/ (parquet + ranking.csv)
	uv run predcar score

export:              ## Evidence bundle → reports/<date>/ (commit it so the remote reviewer can analyse real data)
	uv run predcar export

validate:            ## Check silver invariants
	uv run predcar validate

site:                ## Build the static site from the latest reports/<date>/gold/ into site/dist/
	cd site && npm ci && npm run build

site-dev:            ## Serve the site locally with hot reload
	cd site && npm install && npm run dev

test:
	uv run pytest tests/ -v

lint:
	uv run ruff check . && uv run ruff format --check .
