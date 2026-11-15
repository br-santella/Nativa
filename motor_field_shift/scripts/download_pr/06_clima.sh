#!/usr/bin/env bash
# Climate: NASA POWER per point (143 cells + 399 municipalities), INMET (stations in the Paraná bbox) and indicators -> data/raw/clima_pr/, data/processed/clima_pr/ (POWER takes ~40 min)
# Resumable: skips what has already been downloaded. Log in data/logs/.
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p data/logs
uv run python ingest/clima_oeste_pr.py all --regiao pr 2>&1 | tee -a data/logs/clima_pr.log
