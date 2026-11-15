#!/usr/bin/env bash
# MapBiomas coverage 2019-2024 (Source Cooperative) -> data/raw/mapbiomas_pr/
# Retomável: pula o que já foi baixado. Log em data/logs/.
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p data/logs
uv run python ingest/mapbiomas_relevo_oeste_pr.py --regiao pr --so mapbiomas 2>&1 | tee -a data/logs/mapbiomas_pr.log
