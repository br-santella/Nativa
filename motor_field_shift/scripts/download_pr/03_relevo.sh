#!/usr/bin/env bash
# NASADEM elev.tif + slope slope_pct.tif (Planetary Computer; via STAC, no Earthdata) -> data/raw/nasadem_pr/, data/processed/relevo_pr/
# Resumable: skips what has already been downloaded. Log in data/logs/.
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p data/logs
uv run python ingest/mapbiomas_relevo_oeste_pr.py --regiao pr --so nasadem 2>&1 | tee -a data/logs/nasadem_pr.log
