#!/usr/bin/env bash
# Runs every ingestion for the whole of Paraná in sequence (each one is resumable).
# Usage: scripts/download_pr/run_all.sh   (or run each 0X_*.sh separately / in parallel)
set -uo pipefail
d="$(dirname "$0")"
for s in 01_regiao 02_mapbiomas 03_relevo 04_soilgrids 05_pam 06_clima; do
  echo "== $s"; "$d/$s.sh" || echo "FAILED: $s (continuing)"
done
