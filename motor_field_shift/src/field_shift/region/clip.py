"""Recorta MapBiomas (2000-2024) e relevo (NASADEM) do Parana por um poligono.

Entrada: shapely Polygon/MultiPolygon em EPSG:4326, ou GeoJSON dict (Geometry, Feature ou FeatureCollection).
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
MB = ROOT / "data/raw/mapbiomas_pr"
DEM = ROOT / "data/raw/nasadem_pr/elev.tif"
SLOPE = ROOT / "data/processed/relevo_pr/slope_pct.tif"
REGION = ROOT / "data/raw/regiao/pr.geojson"  # whole state of Paraná
OESTE = ROOT / "data/raw/regiao/oeste_pr.geojson"  # Oeste mesoregion: reference region for costs, prices and calendar
LEGEND = ROOT / "data/processed/ftw/mapbiomas_legend_c10.json"

# classes Embrapa de declividade (limite superior %, nome)
CLASSES_EMBRAPA = [(3, "plano"), (8, "suave ondulado"), (20, "ondulado"),
                   (45, "forte ondulado"), (np.inf, "montanhoso")]


def _geom(polygon):
    if isinstance(polygon, dict):
        t = polygon.get("type")
        if t == "FeatureCollection":
            return unary_union([shape(f["geometry"]) for f in polygon["features"]])
        if t == "Feature":
            return shape(polygon["geometry"])
        return shape(polygon)
    return polygon


@lru_cache(maxsize=1)
def _region():
    return gpd.read_file(REGION).geometry.iloc[0]


@lru_cache(maxsize=1)
def _legend() -> dict[int, str]:
    return {int(k): v for k, v in json.loads(LEGEND.read_text()).items()}


@lru_cache(maxsize=1)
def _oeste():
    return gpd.read_file(OESTE).geometry.iloc[0]


def inside_oeste(polygon) -> bool:
    """True if the geometry (point or polygon) lies inside the Oeste mesoregion (reference region of costs/calendar)."""
    return bool(_oeste().buffer(1e-4).contains(_geom(polygon)))


def inside_region(polygon) -> bool:
    """True se o poligono esta inteiramente dentro do Parana (tolerancia ~10 m)."""
    g = _geom(polygon)
    return bool(_region().buffer(1e-4).contains(g))


def _read(path, g, all_touched=False):
    """Pixels do raster cujo centro cai dentro do poligono (fallback: pixels tocados, p/ poligonos minusculos)."""
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


def _years() -> list[int]:
    return sorted(int(p.stem.split("_")[1]) for p in MB.glob("coverage_*.tif"))


def mapbiomas_history(polygon) -> pd.DataFrame:
    """Uma linha por ano: classe dominante (codigo/nome), fracao dela e `fracoes` {codigo: fracao} (soma 1)."""
    g = _geom(polygon)
    leg = _legend()
    lines = []
    for a in _years():
        v = _read(MB / f"coverage_{a}.tif", g)
        if v.size == 0:
            lines.append(dict(ano=a, classe=0, nome_classe=None, fracao_dominante=np.nan, fracoes={}))
            continue
        cod, n = np.unique(v, return_counts=True)
        fr = n / n.sum()
        k = int(np.argmax(fr))
        lines.append(dict(ano=a, classe=int(cod[k]), nome_classe=leg.get(int(cod[k]), "?"),
                           fracao_dominante=float(fr[k]),
                           fracoes={int(c): float(f) for c, f in zip(cod, fr)}))
    return pd.DataFrame(lines)


def embrapa_class(slope_pct: float) -> str:
    for lim, nome in CLASSES_EMBRAPA:
        if slope_pct <= lim:
            return nome
    return "montanhoso"


def relief(polygon) -> dict:
    """Altitude (m) e declividade (%) medias/extremos dentro do poligono + classe Embrapa."""
    g = _geom(polygon)
    el = _read(DEM, g)
    sl = _read(SLOPE, g)
    if el.size == 0 or sl.size == 0:
        raise ValueError("Poligono sem dados de relevo (fora da area coberta)")
    dm = float(np.mean(sl))
    return dict(altitude_media=float(np.mean(el)), altitude_min=float(np.min(el)),
                altitude_max=float(np.max(el)), declividade_media=dm,
                declividade_p90=float(np.percentile(sl, 90)), classe_embrapa=embrapa_class(dm))
