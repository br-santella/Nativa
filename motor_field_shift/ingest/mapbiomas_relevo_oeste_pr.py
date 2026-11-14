"""Ingestao regional (mesorregiao Oeste do PR, IBGE 4106): limite, MapBiomas C10 2000-2024, NASADEM + declividade.

Idempotente: pula o que ja existe. Uso: uv run python ingest/mapbiomas_relevo_oeste_pr.py
"""
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
import requests
from rasterio.warp import Resampling, calculate_default_transform, reproject
from rasterio.windows import from_bounds

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "data/raw/regiao"
MB = ROOT / "data/raw/mapbiomas_oeste_pr"
DEM = ROOT / "data/raw/nasadem_oeste_pr/elev.tif"
SLOPE = ROOT / "data/processed/relevo_oeste_pr/slope_pct.tif"
URL = ("https://data.source.coop/tristangruppwri/mapbiomas/mapbiomas-brazil/"
       "mapbiomas_brazil_{y}/mapbiomas_brazil_{y}.tif")
YEARS = range(2000, 2025)
MARGEM = 0.05
IBGE = "https://servicodados.ibge.gov.br"


def limite():
    uniao, muni = REG / "oeste_pr.geojson", REG / "municipios_oeste_pr.geojson"
    if not (uniao.exists() and muni.exists()):
        REG.mkdir(parents=True, exist_ok=True)
        nomes = {int(m["id"]): m["nome"] for m in requests.get(
            f"{IBGE}/api/v1/localidades/mesorregioes/4106/municipios", timeout=60).json()}
        r = requests.get(f"{IBGE}/api/v3/malhas/mesorregioes/4106", timeout=180, params=dict(
            formato="application/vnd.geo+json", intrarregiao="municipio", qualidade="maxima"))
        r.raise_for_status()
        tmp = REG / "_tmp.geojson"
        tmp.write_bytes(r.content)
        g = gpd.read_file(tmp).to_crs(4326)
        tmp.unlink()
        g["cod_ibge"] = g["codarea"].astype(int)
        g["nome"] = g["cod_ibge"].map(nomes)
        g = g[["cod_ibge", "nome", "geometry"]]
        assert len(g) == len(nomes) == 50, (len(g), len(nomes))
        g.to_file(muni, driver="GeoJSON")
        gpd.GeoDataFrame({"nome": ["Oeste Paranaense"], "cod_meso": [4106]},
                         geometry=[g.union_all()], crs=4326).to_file(uniao, driver="GeoJSON")
        print("limite salvo,", len(g), "municipios")
    b = gpd.read_file(uniao).total_bounds
    return (b[0] - MARGEM, b[1] - MARGEM, b[2] + MARGEM, b[3] + MARGEM)


def mapbiomas(bounds):
    MB.mkdir(parents=True, exist_ok=True)
    for y in YEARS:
        dst = MB / f"coverage_{y}.tif"
        if dst.exists():
            continue
        try:
            src = rasterio.open(URL.format(y=y))
        except rasterio.errors.RasterioIOError as e:
            # o espelho do Source Cooperative so tem 2019-2024; anos anteriores dao 404
            print("mapbiomas", y, "indisponivel:", str(e)[:60], flush=True)
            continue
        with src:
            win = from_bounds(*bounds, transform=src.transform).round_offsets().round_lengths()
            data = src.read(1, window=win).astype("uint8")
            prof = dict(driver="GTiff", height=win.height, width=win.width, count=1, dtype="uint8",
                        crs=src.crs, transform=src.window_transform(win), nodata=0,
                        compress="deflate", predictor=2, tiled=True, blockxsize=512, blockysize=512)
        tmp = dst.with_suffix(".tmp")
        with rasterio.open(tmp, "w", driver="GTiff", **{k: v for k, v in prof.items() if k != "driver"}) as o:
            o.write(data, 1)
        tmp.rename(dst)
        print("mapbiomas", y, data.shape, flush=True)


def nasadem(bounds):
    if not DEM.exists():
        import planetary_computer as pc
        import pystac_client
        from odc.stac import load
        DEM.parent.mkdir(parents=True, exist_ok=True)
        cat = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1",
                                        modifier=pc.sign_inplace)
        items = list(cat.search(collections=["nasadem"], bbox=list(bounds)).items())
        print("itens NASADEM:", len(items), flush=True)
        ds = load(items, bands=["elevation"], bbox=bounds, crs="EPSG:4326", resolution=1 / 3600,
                  chunks={}, groupby="solar_day")
        el = ds.elevation.max("time").compute().astype("float32") if "time" in ds.elevation.dims else ds.elevation
        lat, lon = el.latitude.values, el.longitude.values
        arr = el.values
        if lat[0] < lat[-1]:
            arr = arr[::-1]
        res = abs(lon[1] - lon[0])
        tr = rasterio.transform.from_origin(lon.min() - res / 2, max(lat) + res / 2, res, res)
        arr = np.where(arr < -1000, np.nan, arr)  # nodata do NASADEM (-32768) -> NaN
        prof = dict(driver="GTiff", height=arr.shape[0], width=arr.shape[1], count=1, dtype="float32",
                    crs="EPSG:4326", transform=tr, nodata=np.nan, compress="deflate", predictor=3,
                    tiled=True, blockxsize=512, blockysize=512)
        tmp = DEM.with_suffix(".tmp")
        with rasterio.open(tmp, "w", **prof) as o:
            o.write(arr.astype("float32"), 1)
        tmp.rename(DEM)
        print("elev.tif", arr.shape, flush=True)
    if not SLOPE.exists():
        SLOPE.parent.mkdir(parents=True, exist_ok=True)
        # declividade: reprojeta para UTM 22S (metros), gradiente, volta para 4326 na grade original
        with rasterio.open(DEM) as src:
            dem = src.read(1)
            dst_crs = "EPSG:31982"
            tr, w, h = calculate_default_transform(src.crs, dst_crs, src.width, src.height, *src.bounds,
                                                   resolution=30)
            utm = np.full((h, w), np.nan, "float32")
            reproject(dem, utm, src_transform=src.transform, src_crs=src.crs, dst_transform=tr,
                      dst_crs=dst_crs, resampling=Resampling.bilinear, src_nodata=np.nan, dst_nodata=np.nan)
            gy, gx = np.gradient(utm, 30.0)
            sl = (np.hypot(gx, gy) * 100).astype("float32")
            out = np.full(dem.shape, np.nan, "float32")
            reproject(sl, out, src_transform=tr, src_crs=dst_crs, dst_transform=src.transform,
                      dst_crs=src.crs, resampling=Resampling.bilinear, src_nodata=np.nan, dst_nodata=np.nan)
            out[np.isnan(dem)] = np.nan
            prof = src.profile | dict(compress="deflate", predictor=3)
        tmp = SLOPE.with_suffix(".tmp")
        with rasterio.open(tmp, "w", **prof) as o:
            o.write(out, 1)
        tmp.rename(SLOPE)
        print("slope_pct.tif", out.shape, flush=True)


def main():
    b = limite()
    print("bbox", b)
    nasadem(b)
    mapbiomas(b)


if __name__ == "__main__":
    main()
