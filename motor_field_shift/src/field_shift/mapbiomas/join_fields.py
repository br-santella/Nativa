"""Attaches MapBiomas Brasil (Collection 10) to the FTW fields, filters agriculture and builds the annual history.

Source: COG mirror on Source Cooperative (tristangruppwri/mapbiomas), Collection 10, years 2019-2024.
(The official bucket storage.googleapis.com/mapbiomas-public returns 403 to anonymous access.)

Usage: uv run python -m field_shift.mapbiomas.join_fields [--skip-download]
"""
import argparse
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from exactextract import exact_extract
from rasterio.windows import from_bounds

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "data/raw/mapbiomas"
OUT = ROOT / "data/processed/ftw"
FIELDS = OUT / "fields_tile_ge1ha.gpkg"
URL = ("https://data.source.coop/tristangruppwri/mapbiomas/mapbiomas-brazil/"
       "mapbiomas_brazil_{y}/mapbiomas_brazil_{y}.tif")
YEARS = list(range(2019, 2025))
LAST = YEARS[-1]
PAD = 0.02  # degrees of margin

# Collection 10 legend (raw national codes; official MapBiomas class names in Portuguese)
LEGEND = {
    1: "Floresta", 3: "Formacao Florestal", 4: "Formacao Savanica", 5: "Mangue", 6: "Floresta Alagavel",
    9: "Silvicultura", 10: "Vegetacao herbacea e arbustiva", 11: "Campo Alagado/Area Pantanosa",
    12: "Formacao Campestre", 14: "Agropecuaria", 15: "Pastagem", 18: "Agricultura",
    19: "Lavoura Temporaria", 20: "Cana", 21: "Mosaico de Usos", 22: "Area nao vegetada",
    23: "Praia/Duna/Areal", 24: "Area Urbanizada", 25: "Outras areas nao vegetadas", 26: "Corpo d'agua",
    27: "Nao observado", 29: "Afloramento Rochoso", 30: "Mineracao", 31: "Aquicultura",
    32: "Apicum", 33: "Rio, Lago e Oceano", 35: "Dende", 36: "Lavoura Perene", 39: "Soja",
    40: "Arroz", 41: "Outras Lavouras Temporarias", 46: "Cafe", 47: "Citrus",
    48: "Outras Lavouras Perenes", 49: "Restinga arborizada", 50: "Restinga herbacea",
    62: "Algodao (beta)", 75: "Usina fotovoltaica (beta)",
}
TEMP_CROPS = [19, 20, 39, 40, 41, 62]  # temporary crops (19 = parent class)
SOY = 39


def download(bounds):
    RAW.mkdir(parents=True, exist_ok=True)
    for y in YEARS:
        dst = RAW / f"mapbiomas_c10_coverage_{y}.tif"
        if dst.exists():
            continue
        with rasterio.open(URL.format(y=y)) as src:
            win = from_bounds(*bounds, transform=src.transform).round_offsets().round_lengths()
            data = src.read(1, window=win)
            prof = src.profile | dict(height=win.height, width=win.width,
                                      transform=src.window_transform(win), compress="deflate", tiled=False)
            prof.pop("blockxsize", None); prof.pop("blockysize", None)
        with rasterio.open(dst, "w", **prof) as o:
            o.write(data, 1)
        print("baixado", dst.name, data.shape)


def extract_year(gdf4326, y):
    res = exact_extract(str(RAW / f"mapbiomas_c10_coverage_{y}.tif"), gdf4326,
                        ["unique", "frac"], include_cols=["id"], output="pandas", progress=False)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-download", action="store_true")
    a = ap.parse_args()

    gdf = gpd.read_file(FIELDS)
    g4 = gdf.to_crs(4326)
    minx, miny, maxx, maxy = g4.total_bounds
    if not a.skip_download:
        download((minx - PAD, miny - PAD, maxx + PAD, maxy + PAD))

    g4 = g4.reset_index(drop=True)
    g4["_i"] = np.arange(len(g4))
    g4s = g4[["_i", "geometry"]]
    maj, tempfrac, fracs_last = {}, {}, None
    for y in YEARS:
        r = exact_extract(str(RAW / f"mapbiomas_c10_coverage_{y}.tif"), g4s, ["unique", "frac"],
                          include_cols=["_i"], output="pandas", progress=False)
        m = np.zeros(len(g4), dtype="int16"); t = np.zeros(len(g4), dtype="float32")
        fr = []
        for i, u, f in zip(r["_i"], r["unique"], r["frac"]):
            u = np.asarray(u); f = np.asarray(f, dtype=float)
            ok = u != 0  # 0 = nodata
            if not ok.any():
                continue
            u, f = u[ok].astype(int), f[ok]
            m[i] = u[np.argmax(f)]
            t[i] = f[np.isin(u, TEMP_CROPS)].sum() / f.sum()
            if y == LAST:
                fr.append((i, dict(zip(u, f / f.sum()))))
        maj[y], tempfrac[y] = m, t
        if y == LAST:
            fracs_last = fr
        print("ano", y, "ok")

    df = gdf.reset_index(drop=True).copy()
    for y in YEARS:
        df[f"lc_{y}"] = maj[y]
    for y in YEARS:
        df[f"temp_frac_{y}"] = tempfrac[y]
    codes = sorted({c for _, d in fracs_last for c in d})
    fm = np.zeros((len(df), len(codes)), dtype="float32")
    for i, d in fracs_last:
        for c, v in d.items():
            fm[i, codes.index(c)] = v
    for j, c in enumerate(codes):
        df[f"frac_{LAST}_c{c}"] = fm[:, j]
    df[f"lc_{LAST}_name"] = df[f"lc_{LAST}"].map(LEGEND)

    lc = df[[f"lc_{y}" for y in YEARS]].to_numpy()
    df["n_years_soy"] = (lc == SOY).sum(1)
    df["n_years_temp_crop"] = np.isin(lc, TEMP_CROPS).sum(1)
    df["n_distinct_classes"] = [len(set(r[r > 0])) for r in lc]
    df["is_agri"] = df[f"temp_frac_{LAST}"] >= 0.5

    out = df.copy()
    out.drop(columns="geometry").to_parquet(OUT / "fields_tile_mapbiomas.parquet")
    gpd.GeoDataFrame(out, geometry="geometry", crs=gdf.crs).to_parquet(OUT / "fields_tile_mapbiomas_geo.parquet")
    agri = gpd.GeoDataFrame(out[out.is_agri], geometry="geometry", crs=gdf.crs)
    agri.to_file(OUT / "fields_tile_agri.gpkg", driver="GPKG")
    (OUT / "mapbiomas_legend_c10.json").write_text(json.dumps(LEGEND, ensure_ascii=False, indent=1))
    print("total", len(out), "agri", int(out.is_agri.sum()))


if __name__ == "__main__":
    main()
