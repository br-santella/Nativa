#!/usr/bin/env bash
# Dispara todas as ingestões do Paraná inteiro em sequência (cada uma é retomável).
# Uso: scripts/download_pr/run_all.sh   (ou rode cada 0X_*.sh separadamente / em paralelo)
set -uo pipefail
d="$(dirname "$0")"
for s in 01_regiao 02_mapbiomas 03_relevo 04_soilgrids 05_pam 06_clima 07_pam_extra; do
  echo "== $s"; "$d/$s.sh" || echo "FALHOU: $s (seguindo)"
done
