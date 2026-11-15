"""Clips MapBiomas (2000-2024) and terrain (NASADEM) of the Western Paraná mesoregion by a polygon.

Input: shapely Polygon/MultiPolygon in EPSG:4326, or a GeoJSON dict (Geometry, Feature or FeatureCollection).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import geometry_mask
from rasterio.windows import from_bounds
from shapely.geometry import shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[3]
MB = ROOT / "data/raw/mapbiomas_oeste_pr"
DEM = ROOT / "data/raw/nasadem_oeste_pr/elev.tif"
SLOPE = ROOT / "data/processed/relevo_oeste_pr/slope_pct.tif"
REGIAO = ROOT / "data/raw/regiao/oeste_pr.geojson"
LEGENDA = ROOT / "data/processed/ftw/mapbiomas_legend_c10.json"

# Embrapa slope classes (upper limit %, name)
CLASSES_EMBRAPA = [(3, "plano"), (8, "suave ondulado"), (20, "ondulado"),
                   (45, "forte ondulado"), (np.inf, "montanhoso")]


def _geom(poligono):
    if isinstance(poligono, dict):
        t = poligono.get("type")
        if t == "FeatureCollection":
            return unary_union([shape(f["geometry"]) for f in poligono["features"]])
        if t == "Feature":
            return shape(poligono["geometry"])
        return shape(poligono)
    return poligono


@lru_cache(maxsize=1)
def _regiao():
    return gpd.read_file(REGIAO).geometry.iloc[0]


@lru_cache(maxsize=1)
def _legenda() -> dict[int, str]:
    return {int(k): v for k, v in json.loads(LEGENDA.read_text()).items()}


def dentro_da_regiao(poligono) -> bool:
    """True if the polygon is entirely inside the Western mesoregion (tolerance ~10 m)."""
    g = _geom(poligono)
    return bool(_regiao().buffer(1e-4).contains(g))


def _ler(path, g, all_touched=False):
    """Raster pixels whose center falls inside the polygon (fallback: touched pixels, for tiny polygons)."""
    with rasterio.open(path) as src:
        win = from_bounds(*g.bounds, transform=src.transform).round_offsets().round_lengths()
        win = win.intersection(rasterio.windows.Window(0, 0, src.width, src.height))
        data = src.read(1, window=win)
        tr = src.window_transform(win)
        nodata = src.nodata
    m = ~geometry_mask([g], out_shape=data.shape, transform=tr, all_touched=all_touched)
    if not m.any():
        m = ~geometry_mask([g], out_shape=data.shape, transform=tr, all_touched=True)
    v = data[m]
    if nodata is not None:
        v = v[~np.isnan(v)] if np.isnan(nodata) else v[v != nodata]
    return v


def _anos() -> list[int]:
    return sorted(int(p.stem.split("_")[1]) for p in MB.glob("coverage_*.tif"))


def historico_mapbiomas(poligono) -> pd.DataFrame:
    """One row per year: dominant class (code/name), its fraction and `fracoes` {code: fraction} (sum 1)."""
    g = _geom(poligono)
    leg = _legenda()
    linhas = []
    for a in _anos():
        v = _ler(MB / f"coverage_{a}.tif", g)
        if v.size == 0:
            linhas.append(dict(ano=a, classe=0, nome_classe=None, fracao_dominante=np.nan, fracoes={}))
            continue
        cod, n = np.unique(v, return_counts=True)
        fr = n / n.sum()
        k = int(np.argmax(fr))
        linhas.append(dict(ano=a, classe=int(cod[k]), nome_classe=leg.get(int(cod[k]), "?"),
                           fracao_dominante=float(fr[k]),
                           fracoes={int(c): float(f) for c, f in zip(cod, fr)}))
    return pd.DataFrame(linhas)


def classe_embrapa(decl_pct: float) -> str:
    for lim, nome in CLASSES_EMBRAPA:
        if decl_pct <= lim:
            return nome
    return "montanhoso"


def relevo(poligono) -> dict:
    """Elevation (m) and slope (%) means/extremes inside the polygon + Embrapa class."""
    g = _geom(poligono)
    el = _ler(DEM, g)
    sl = _ler(SLOPE, g)
    if el.size == 0 or sl.size == 0:
        raise ValueError("Polygon without terrain data (outside the covered area)")
    dm = float(np.mean(sl))
    return dict(altitude_media=float(np.mean(el)), altitude_min=float(np.min(el)),
                altitude_max=float(np.max(el)), declividade_media=dm,
                declividade_p90=float(np.percentile(sl, 90)), classe_embrapa=classe_embrapa(dm))
