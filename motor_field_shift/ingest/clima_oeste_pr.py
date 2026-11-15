"""Ingestão de clima da mesorregião Oeste do Paraná (NASA POWER diário + INMET).

Uso: uv run python ingest/clima_oeste_pr.py {area,power,inmet,indicadores,validacao,all} [--regiao oeste_pr|pr]
--regiao pr aplica a mesma lógica (células 0,5x0,625 + centroides de município) ao Paraná inteiro (UF 41),
gravando em data/raw/clima_pr/ e data/processed/clima_pr/. Default: oeste_pr (comportamento original).
Idempotente: pula o que já está em cache / já processado.
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

REGIOES = {
    # sufixo dos caminhos; mesorregião IBGE (None = estado inteiro); qualidade da malha
    "oeste_pr": dict(raw="data/raw/clima", proc="data/processed/clima", meso=4106),
    "pr": dict(raw="data/raw/clima_pr", proc="data/processed/clima_pr", meso=None),
}
RAW = ROOT / REGIOES["oeste_pr"]["raw"]
PROC = ROOT / REGIOES["oeste_pr"]["proc"]
MESO = REGIOES["oeste_pr"]["meso"]
REGIAO = "oeste_pr"
MUN_GEOJSON = RAW / "municipios_oeste_pr.geojson"
POWER_DIR = RAW / "power"
INMET_ZIPS = RAW / "inmet/zips"
MARGEM = 0.3
DLAT, DLON = 0.5, 0.625
PARAMS = ["T2M", "T2M_MIN", "T2M_MAX", "PRECTOTCORR", "RH2M", "WS2M", "ALLSKY_SFC_SW_DWN",
          "T2MDEW", "GWETTOP", "GWETROOT"]
POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
UA = {"User-Agent": "field-shift-hackathon/0.1 (pesquisa academica)"}


# ----------------------------------------------------------------------------- 1. Área
def configurar(regiao: str):
    """Aponta os caminhos globais para a região escolhida (default do módulo: oeste_pr)."""
    global RAW, PROC, MESO, REGIAO, MUN_GEOJSON, POWER_DIR, INMET_ZIPS
    c = REGIOES[regiao]
    REGIAO, MESO = regiao, c["meso"]
    RAW, PROC = ROOT / c["raw"], ROOT / c["proc"]
    MUN_GEOJSON = RAW / f"municipios_{regiao}.geojson"
    POWER_DIR = RAW / "power"
    INMET_ZIPS = RAW / "inmet/zips"


def cmd_area() -> gpd.GeoDataFrame:
    if MUN_GEOJSON.exists():
        return gpd.read_file(MUN_GEOJSON)
    RAW.mkdir(parents=True, exist_ok=True)
    loc = f"mesorregioes/{MESO}" if MESO else "estados/41"
    lista = requests.get(f"https://servicodados.ibge.gov.br/api/v1/localidades/{loc}/municipios",
                         timeout=60, headers=UA).json()
    nomes = {str(m["id"]): m["nome"] for m in lista}
    malha = requests.get("https://servicodados.ibge.gov.br/api/v3/malhas/estados/41",
                         params={"intrarregiao": "municipio", "formato": "application/vnd.geo+json",
                                 "qualidade": "intermediaria"}, timeout=180, headers=UA).json()
    gdf = gpd.GeoDataFrame.from_features(malha["features"], crs="EPSG:4326")
    gdf["cod_ibge"] = gdf["codarea"].astype(str)
    gdf = gdf[gdf.cod_ibge.isin(nomes)].copy()
    assert len(gdf) == len(nomes), (len(gdf), len(nomes))
    gdf["nome"] = gdf.cod_ibge.map(nomes)
    proj = gdf.to_crs(5880)
    cen = proj.geometry.centroid
    dentro = proj.geometry.contains(cen)
    cen = cen.where(dentro, proj.geometry.representative_point()).to_crs(4326)
    gdf["lon_c"], gdf["lat_c"] = cen.x.values, cen.y.values
    gdf[["cod_ibge", "nome", "lat_c", "lon_c", "geometry"]].to_file(MUN_GEOJSON, driver="GeoJSON")
    print(f"{len(gdf)} municípios salvos em {MUN_GEOJSON}")
    return gdf


def grade_celulas(gdf) -> list[tuple[float, float]]:
    x0, y0, x1, y1 = gdf.total_bounds
    x0, y0, x1, y1 = x0 - MARGEM, y0 - MARGEM, x1 + MARGEM, y1 + MARGEM
    # célula k: lat em [k*0.5-0.25, k*0.5+0.25]; lon j: [j*0.625-0.3125, j*0.625+0.3125]
    ks = range(math.floor((y0 + DLAT / 2) / DLAT), math.ceil((y1 - DLAT / 2) / DLAT) + 1)
    js = range(math.floor((x0 + DLON / 2) / DLON), math.ceil((x1 - DLON / 2) / DLON) + 1)
    return [(round(k * DLAT, 4), round(j * DLON, 4)) for k in ks for j in js]


def lista_pontos() -> pd.DataFrame:
    gdf = cmd_area()
    linhas = []
    for lat, lon in grade_celulas(gdf):
        linhas.append(dict(ponto_id=f"cel_{lat:+.3f}_{lon:+.4f}", tipo="celula", cod_ibge="", lat=lat, lon=lon))
    for r in gdf.itertuples():
        linhas.append(dict(ponto_id=f"mun_{r.cod_ibge}", tipo="municipio", cod_ibge=r.cod_ibge,
                           lat=round(r.lat_c, 4), lon=round(r.lon_c, 4)))
    return pd.DataFrame(linhas)


# ----------------------------------------------------------------------------- 2. POWER
def baixar_ponto(pid: str, lat: float, lon: float, params: list[str]) -> dict | None:
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
    pts = lista_pontos()
    print(f"{len(pts)} pontos ({(pts.tipo == 'celula').sum()} células, {(pts.tipo == 'municipio').sum()} municípios)")
    for i, p in enumerate(pts.itertuples(), 1):
        novo = not (POWER_DIR / f"{p.ponto_id}.json").exists()
        js = baixar_ponto(p.ponto_id, p.lat, p.lon, PARAMS)
        if js is None:
            print(f"FALHOU {p.ponto_id}")
        if novo:
            print(f"[{i}/{len(pts)}] {p.ponto_id}", flush=True)
            time.sleep(1.0)
    consolidar_power(pts)


def consolidar_power(pts: pd.DataFrame):
    PROC.mkdir(parents=True, exist_ok=True)
    partes, faltantes, ausentes = [], set(), []
    for p in pts.itertuples():
        f = POWER_DIR / f"{p.ponto_id}.json"
        if not f.exists():
            ausentes.append(p.ponto_id)
            continue
        js = json.loads(f.read_text())
        par = js["properties"]["parameter"]
        elev = js["geometry"]["coordinates"][2]
        faltantes |= set(PARAMS) - set(par)
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
        partes.append(df.reset_index())
    out = pd.concat(partes, ignore_index=True)
    for c in PARAMS:
        if c in out:
            out[c] = out[c].astype("float32")
    out.to_parquet(PROC / "power_diario.parquet", index=False)
    print(f"power_diario.parquet: {len(out)} linhas, {out.ponto_id.nunique()} pontos, "
          f"{out.data.min().date()}..{out.data.max().date()}; parâmetros ausentes: {sorted(faltantes) or 'nenhum'}; "
          f"pontos sem arquivo: {ausentes or 'nenhum'}")


# ----------------------------------------------------------------------------- 3. INMET
def cmd_inmet():
    from field_shift.clima.inmet import processar_inmet
    gdf = cmd_area()
    x0, y0, x1, y1 = gdf.total_bounds
    bbox = (x0 - MARGEM, y0 - MARGEM, x1 + MARGEM, y1 + MARGEM)
    processar_inmet(bbox, INMET_ZIPS, PROC, UA)


# ----------------------------------------------------------------------------- 4/5
def cmd_indicadores():
    from field_shift.clima.indicadores import gerar_indicadores
    gerar_indicadores(PROC)


def cmd_validacao():
    from field_shift.clima.validacao import validar
    validar(PROC)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["area", "power", "inmet", "indicadores", "validacao", "all"])
    ap.add_argument("--regiao", choices=sorted(REGIOES), default="oeste_pr")
    a = ap.parse_args()
    configurar(a.regiao)
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
        cmd_indicadores()
    if a.cmd in ("validacao", "all"):
        cmd_validacao()


if __name__ == "__main__":
    main()
