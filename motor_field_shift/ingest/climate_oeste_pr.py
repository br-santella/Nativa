"""Climate ingestion for the Oeste mesoregion of Paraná (daily NASA POWER + INMET).

Usage: uv run python ingest/climate_oeste_pr.py {area,power,inmet,indicadores,validacao,all} [--regiao oeste_pr|pr]
--regiao pr applies the same logic (0.5x0.625 cells + municipality centroids) to the whole of Paraná (UF 41),
writing to data/raw/clima_pr/ and data/processed/clima_pr/. Default: oeste_pr (original behavior).
Idempotent: skips what is already cached / processed.
"""
from __future__ import annotations

import argparse
import io
import json
import math
import re
import shutil
import sys
import time
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

REGIONS = {
    # path suffix; IBGE mesoregion (None = whole state); mesh quality
    "oeste_pr": dict(raw="data/raw/clima", proc="data/processed/clima", meso=4106),
    "pr": dict(raw="data/raw/clima_pr", proc="data/processed/clima_pr", meso=None),
}
RAW = ROOT / REGIONS["oeste_pr"]["raw"]
PROC = ROOT / REGIONS["oeste_pr"]["proc"]
MESO = REGIONS["oeste_pr"]["meso"]
REGION = "oeste_pr"
MUN_GEOJSON = RAW / "municipios_oeste_pr.geojson"
POWER_DIR = RAW / "power"
INMET_ZIPS = RAW / "inmet/zips"
MARGIN = 0.3
DLAT, DLON = 0.5, 0.625
PARAMS = ["T2M", "T2M_MIN", "T2M_MAX", "PRECTOTCORR", "RH2M", "WS2M", "ALLSKY_SFC_SW_DWN",
          "T2MDEW", "GWETTOP", "GWETROOT"]
POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
UA = {"User-Agent": "field-shift-hackathon/0.1 (pesquisa academica)"}


# ----------------------------------------------------------------------------- 1. Area
def configure(region: str):
    """Point the global paths to the chosen region (module default: oeste_pr)."""
    global RAW, PROC, MESO, REGION, MUN_GEOJSON, POWER_DIR, INMET_ZIPS
    c = REGIONS[region]
    REGION, MESO = region, c["meso"]
    RAW, PROC = ROOT / c["raw"], ROOT / c["proc"]
    MUN_GEOJSON = RAW / f"municipios_{region}.geojson"
    POWER_DIR = RAW / "power"
    INMET_ZIPS = RAW / "inmet/zips"


def cmd_area() -> gpd.GeoDataFrame:
    if MUN_GEOJSON.exists():
        return gpd.read_file(MUN_GEOJSON)
    RAW.mkdir(parents=True, exist_ok=True)
    loc = f"mesorregioes/{MESO}" if MESO else "estados/41"
    items_list = requests.get(f"https://servicodados.ibge.gov.br/api/v1/localidades/{loc}/municipios",
                         timeout=60, headers=UA).json()
    names = {str(m["id"]): m["nome"] for m in items_list}
    mesh = requests.get("https://servicodados.ibge.gov.br/api/v3/malhas/estados/41",
                         params={"intrarregiao": "municipio", "formato": "application/vnd.geo+json",
                                 "qualidade": "intermediaria"}, timeout=180, headers=UA).json()
    gdf = gpd.GeoDataFrame.from_features(mesh["features"], crs="EPSG:4326")
    gdf["cod_ibge"] = gdf["codarea"].astype(str)
    gdf = gdf[gdf.cod_ibge.isin(names)].copy()
    assert len(gdf) == len(names), (len(gdf), len(names))
    gdf["nome"] = gdf.cod_ibge.map(names)
    proj = gdf.to_crs(5880)
    scn = proj.geometry.centroid
    inside = proj.geometry.contains(scn)
    scn = scn.where(inside, proj.geometry.representative_point()).to_crs(4326)
    gdf["lon_c"], gdf["lat_c"] = scn.x.values, scn.y.values
    gdf[["cod_ibge", "nome", "lat_c", "lon_c", "geometry"]].to_file(MUN_GEOJSON, driver="GeoJSON")
    print(f"{len(gdf)} municipalities saved to {MUN_GEOJSON}")
    return gdf


def cell_grid(gdf) -> list[tuple[float, float]]:
    x0, y0, x1, y1 = gdf.total_bounds
    x0, y0, x1, y1 = x0 - MARGIN, y0 - MARGIN, x1 + MARGIN, y1 + MARGIN
    # cell k: lat in [k*0.5-0.25, k*0.5+0.25]; lon j: [j*0.625-0.3125, j*0.625+0.3125]
    ks = range(math.floor((y0 + DLAT / 2) / DLAT), math.ceil((y1 - DLAT / 2) / DLAT) + 1)
    js = range(math.floor((x0 + DLON / 2) / DLON), math.ceil((x1 - DLON / 2) / DLON) + 1)
    return [(round(k * DLAT, 4), round(j * DLON, 4)) for k in ks for j in js]


def list_points() -> pd.DataFrame:
    gdf = cmd_area()
    lines = []
    for lat, lon in cell_grid(gdf):
        lines.append(dict(ponto_id=f"cel_{lat:+.3f}_{lon:+.4f}", tipo="celula", cod_ibge="", lat=lat, lon=lon))
    for r in gdf.itertuples():
        lines.append(dict(ponto_id=f"mun_{r.cod_ibge}", tipo="municipio", cod_ibge=r.cod_ibge,
                           lat=round(r.lat_c, 4), lon=round(r.lon_c, 4)))
    return pd.DataFrame(lines)


# ----------------------------------------------------------------------------- 2. POWER
def download_point(pid: str, lat: float, lon: float, params: list[str]) -> dict | None:
    f = POWER_DIR / f"{pid}.json"
    if f.exists():
        return json.loads(f.read_text())
    q = dict(parameters=",".join(params), community="AG", longitude=lon, latitude=lat,
             start="19910101", end="20251231", format="JSON")
    for t in range(6):
        try:
            r = requests.get(POWER_URL, params=q, timeout=300, headers=UA)
            if r.status_code == 200:
                js = r.json()
                f.write_text(json.dumps(js))
                return js
            print(f"  {pid}: HTTP {r.status_code} {r.text[:200]}", flush=True)
            if r.status_code == 422:
                return None
        except Exception as e:  # noqa: BLE001
            print(f"  {pid}: {type(e).__name__} {e}", flush=True)
        time.sleep(5 * 2 ** t)
    return None


def cmd_power():
    POWER_DIR.mkdir(parents=True, exist_ok=True)
    pts = list_points()
    print(f"{len(pts)} points ({(pts.tipo == 'celula').sum()} cells, {(pts.tipo == 'municipio').sum()} municipalities)")
    for i, p in enumerate(pts.itertuples(), 1):
        new = not (POWER_DIR / f"{p.ponto_id}.json").exists()
        js = download_point(p.ponto_id, p.lat, p.lon, PARAMS)
        if js is None:
            print(f"FALHOU {p.ponto_id}")
        if new:
            print(f"[{i}/{len(pts)}] {p.ponto_id}", flush=True)
            time.sleep(1.0)
    consolidate_power(pts)


def consolidate_power(pts: pd.DataFrame):
    PROC.mkdir(parents=True, exist_ok=True)
    parts, missing_values, missing = [], set(), []
    for p in pts.itertuples():
        f = POWER_DIR / f"{p.ponto_id}.json"
        if not f.exists():
            missing.append(p.ponto_id)
            continue
        js = json.loads(f.read_text())
        par = js["properties"]["parameter"]
        elev = js["geometry"]["coordinates"][2]
        missing_values |= set(PARAMS) - set(par)
        df = pd.DataFrame({k: pd.Series(v) for k, v in par.items()})
        df.index = pd.to_datetime(df.index, format="%Y%m%d")
        df = df.where(df > -998)
        df.insert(0, "ponto_id", p.ponto_id)
        df.insert(1, "tipo", p.tipo)
        df.insert(2, "cod_ibge", p.cod_ibge)
        df.insert(3, "lat", p.lat)
        df.insert(4, "lon", p.lon)
        df.insert(5, "elev", float(elev))
        df.index.name = "data"
        parts.append(df.reset_index())
    out = pd.concat(parts, ignore_index=True)
    for c in PARAMS:
        if c in out:
            out[c] = out[c].astype("float32")
    out.to_parquet(PROC / "power_diario.parquet", index=False)
    print(f"power_diario.parquet: {len(out)} rows, {out.ponto_id.nunique()} points, "
          f"{out.data.min().date()}..{out.data.max().date()}; missing parameters: {sorted(missing_values) or 'none'}; "
          f"points without a file: {missing or 'none'}")


# ----------------------------------------------------------------------------- 3. INMET
def cmd_inmet():
    from field_shift.climate.inmet import process_inmet
    gdf = cmd_area()
    x0, y0, x1, y1 = gdf.total_bounds
    bbox = (x0 - MARGIN, y0 - MARGIN, x1 + MARGIN, y1 + MARGIN)
    process_inmet(bbox, INMET_ZIPS, PROC, UA)


# ----------------------------------------------------------------------------- 4/5
def cmd_indicators():
    from field_shift.climate.indicators import build_indicators
    build_indicators(PROC)


def cmd_validation():
    from field_shift.climate.station_validation import validate
    validate(PROC)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["area", "power", "inmet", "indicadores", "validacao", "all"])
    ap.add_argument("--regiao", choices=sorted(REGIONS), default="oeste_pr")
    a = ap.parse_args()
    configure(a.region)
    if a.cmd in ("area",):
        cmd_area()
    if a.cmd in ("power", "all"):
        cmd_power()
    if a.cmd in ("inmet", "all"):
        try:
            cmd_inmet()
        except Exception as e:  # noqa: BLE001
            print(f"INMET falhou (seguindo sem): {type(e).__name__}: {e}")
    if a.cmd in ("indicadores", "all"):
        cmd_indicators()
    if a.cmd in ("validacao", "all"):
        cmd_validation()


if __name__ == "__main__":
    main()
