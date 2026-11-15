#!/usr/bin/env bash
# Limite do PR (UF 41) + 399 municípios (IBGE) -> data/raw/regiao/pr.geojson, municipios_pr.geojson
# Retomável: pula o que já foi baixado. Log em data/logs/.
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p data/logs
uv run python ingest/mapbiomas_relevo_oeste_pr.py --regiao pr --so limite
