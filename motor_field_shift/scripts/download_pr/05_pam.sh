#!/usr/bin/env bash
# IBGE PAM (SIDRA 1612 e 839) 399 municípios -> data/raw/ibge/pam_pr.parquet
# Retomável: pula o que já foi baixado. Log em data/logs/.
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p data/logs
uv run python ingest/solo_pam_oeste_pr.py pam --regiao pr 2>&1 | tee -a data/logs/pam_pr.log
