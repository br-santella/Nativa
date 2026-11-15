#!/usr/bin/env bash
# IBGE PAM (SIDRA 1612 and 1002): sorghum and 2nd-season beans, 399 municipalities -> data/raw/ibge/pam_extra_pr.parquet
# Resumable: skips the file if it exists (use --force in the python call to redo it). Log in data/logs/.
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p data/logs
uv run python ingest/pam_culturas_extra.py --regiao pr 2>&1 | tee -a data/logs/pam_extra_pr.log
