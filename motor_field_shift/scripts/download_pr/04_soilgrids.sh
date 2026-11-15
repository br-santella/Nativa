#!/usr/bin/env bash
# SoilGrids (ISRIC) -> data/raw/soilgrids_pr/
# Retomável: pula o que já foi baixado. Log em data/logs/.
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p data/logs
uv run python ingest/solo_pam_oeste_pr.py soilgrids --regiao pr 2>&1 | tee -a data/logs/soilgrids_pr.log
