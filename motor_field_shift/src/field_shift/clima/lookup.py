"""Lookup de indicadores climáticos pré-calculados (Oeste do PR) por lat/lon.

indicadores_para(lat, lon) -> dict | None. None se o ponto está fora da região (o chamador deve cair no POWER ao vivo).
"""
from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

ROOT = Path(__file__).resolve().parents[3]
PROC = ROOT / "data/processed/clima"
MUN = ROOT / "data/raw/clima/municipios_oeste_pr.geojson"
DLAT, DLON = 0.5, 0.625
STATS = ["n_anos", "media", "mediana", "p20", "p80", "media_1991_2020", "mediana_1991_2020",
         "p20_1991_2020", "p80_1991_2020"]


@lru_cache(maxsize=1)
def _dados():
    ind = pd.read_parquet(PROC / "indicadores.parquet")
    por_ponto = {pid: g for pid, g in ind.groupby("ponto_id")}
    mun = gpd.read_file(MUN)
    return por_ponto, mun


def celula_id(lat: float, lon: float) -> str:
    return f"cel_{round(lat / DLAT) * DLAT:+.3f}_{round(lon / DLON) * DLON:+.4f}"


def _dict_ponto(g: pd.DataFrame) -> dict:
    out = {}
    for r in g.itertuples(index=False):
        d = {k: (None if pd.isna(getattr(r, k)) else float(getattr(r, k))) for k in STATS}
        if r.indicador == "inicio_chuvas_dias_desde_0109":
            for k in ("mediana", "p80", "p20"):
                if d[k] is not None:
                    dt = date(2001, 9, 1) + timedelta(days=int(round(d[k])))
                    d[f"{k}_ddmm"] = dt.strftime("%d/%m")
        out[r.indicador] = d
    return out


def indicadores_para(lat: float, lon: float) -> dict | None:
    por_ponto, mun = _dados()
    pt = Point(lon, lat)
    hit = mun[mun.geometry.contains(pt)]
    if hit.empty:
        return None
    m = hit.iloc[0]
    cid = celula_id(lat, lon)
    mid = f"mun_{m.cod_ibge}"
    if cid not in por_ponto or mid not in por_ponto:
        return None
    gc = por_ponto[cid].iloc[0]
    return dict(
        dentro_da_regiao=True,
        celula=dict(ponto_id=cid, lat=float(gc.lat), lon=float(gc.lon), elev=float(gc.elev),
                    indicadores=_dict_ponto(por_ponto[cid])),
        municipio=dict(cod_ibge=m.cod_ibge, nome=m.nome, lat=float(m.lat_c), lon=float(m.lon_c),
                       indicadores=_dict_ponto(por_ponto[mid])),
        convencao="ano agrícola Y = jul/Y a jun/Y+1; anos 1991-2024; *_1991_2020 = safras 1991-2019",
    )
