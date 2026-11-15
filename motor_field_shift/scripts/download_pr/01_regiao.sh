#!/usr/bin/env bash
# Paraná boundary (UF 41) + 399 municipalities (IBGE) -> data/raw/regiao/pr.geojson, municipios_pr.geojson
# Resumable: skips what has already been downloaded. Log in data/logs/.
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p data/logs
uv run python ingest/mapbiomas_relevo_oeste_pr.py --regiao pr --so limite
