#!/usr/bin/env bash
# Clima: NASA POWER por ponto (143 células + 399 municípios), INMET (estações do bbox do PR) e indicadores -> data/raw/clima_pr/, data/processed/clima_pr/ (POWER leva ~40 min)
# Retomável: pula o que já foi baixado. Log em data/logs/.
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p data/logs
uv run python ingest/clima_oeste_pr.py all --regiao pr 2>&1 | tee -a data/logs/clima_pr.log
