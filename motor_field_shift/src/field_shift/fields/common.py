from pathlib import Path
import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
FTW = ROOT / "data/processed/ftw"
OUT = ROOT / "data/processed/talhoes_demo"
OUT.mkdir(parents=True, exist_ok=True)
YEARS = list(range(2019, 2025))
SOY = 39


def candidates(amin=20, amax=200, min_soy=5):
    d = gpd.read_parquet(FTW / "fields_tile_mapbiomas_geo.parquet")
    d = d[d.area_ha.between(amin, amax) & (d.n_years_soy >= min_soy)].copy()
    return d.reset_index(drop=True)
