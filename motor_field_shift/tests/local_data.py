"""Marker for the engine tests that read the local data in `data/raw` and `data/processed` (not in git).

On a fresh clone without that data they are skipped instead of failing; with the data they run as usual.
"""
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parents[1] / "data"
# One file per family the engine loads at start-up (region, climate lookup, demo field).
REQUIRED = [
    DATA / "raw/regiao/pr.geojson",
    DATA / "processed/clima_pr/indicadores.parquet",
    DATA / "processed/ftw/fields_tile_mapbiomas_geo.parquet",
]
MISSING = [str(p.relative_to(DATA.parent)) for p in REQUIRED if not p.exists()]

needs_data = pytest.mark.skipif(
    bool(MISSING), reason=f"local data missing ({', '.join(MISSING)}); see api/README.md, 'Required data in data/'"
)
