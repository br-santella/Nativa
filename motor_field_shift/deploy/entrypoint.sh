#!/bin/sh
# Syncs the API inputs (data/raw and data/processed) from a Hugging Face dataset when
# HF_DATA_REPO is set, then starts the API on $PORT. Only new or changed files are downloaded.
set -e

if [ -n "$HF_DATA_REPO" ]; then
  echo "Syncing data from $HF_DATA_REPO..."
  hf download "$HF_DATA_REPO" --repo-type dataset --local-dir /app/data --quiet
fi

exec uvicorn field_shift_api.main:app --app-dir api --host 0.0.0.0 --port "${PORT:-7860}"
