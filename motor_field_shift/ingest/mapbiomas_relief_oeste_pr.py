"""Regional ingestion (Oeste mesoregion of PR, IBGE 4106): boundary, MapBiomas C10 2000-2024, NASADEM + slope.

Idempotent: skips what already exists.
Usage: uv run python ingest/mapbiomas_relief_oeste_pr.py [--regiao oeste_pr|pr]
  --regiao pr: whole of Paraná (UF 41, 399 municipalities); writes to *_pr (regiao/pr.geojson, mapbiomas_pr/,
  nasadem_pr/, relevo_pr/). Default oeste_pr = original behavior.
"""
import argparse
import json
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
import requests
from rasterio.warp import Resampling, calculate_default_transform, reproject
from rasterio.windows import Window, from_bounds

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "data/raw/regiao"
REGIONS = {
    # meso=None -> whole state (UF 41); blocos=True -> process in blocks (raster too large for RAM)
    "oeste_pr": dict(sufixo="oeste_pr", nome="Oeste Paranaense", meso=4106, n_mun=50, blocos=False),
    "pr": dict(sufixo="pr", nome="Paraná", meso=None, n_mun=399, blocos=True),
}
CFG = REGIONS["oeste_pr"]
MB = ROOT / "data/raw/mapbiomas_oeste_pr"
DEM = ROOT / "data/raw/nasadem_oeste_pr/elev.tif"
SLOPE = ROOT / "data/processed/relevo_oeste_pr/slope_pct.tif"
URL = ("https://data.source.coop/tristangruppwri/mapbiomas/mapbiomas-brazil/"
       "mapbiomas_brazil_{y}/mapbiomas_brazil_{y}.tif")
YEARS = range(2000, 2025)
MARGIN = 0.05
IBGE = "https://servicodados.ibge.gov.br"


def configure(region):
    global CFG, MB, DEM, SLOPE
    CFG = REGIONS[region]
    suf = CFG["sufixo"]
    MB = ROOT / f"data/raw/mapbiomas_{suf}"
    DEM = ROOT / f"data/raw/nasadem_{suf}/elev.tif"
    SLOPE = ROOT / f"data/processed/relevo_{suf}/slope_pct.tif"


def limit():
    suf, meso = CFG["sufixo"], CFG["meso"]
    union_, muni = REG / f"{suf}.geojson", REG / f"municipios_{suf}.geojson"
    if not (union_.exists() and muni.exists()):
        REG.mkdir(parents=True, exist_ok=True)
        loc, mesh = (f"mesorregioes/{meso}", f"mesorregioes/{meso}") if meso else ("estados/41", "estados/41")
        names = {int(m["id"]): m["nome"] for m in requests.get(
            f"{IBGE}/api/v1/localidades/{loc}/municipios", timeout=60).json()}
        r = requests.get(f"{IBGE}/api/v3/malhas/{mesh}", timeout=600, params=dict(
            formato="application/vnd.geo+json", intrarregiao="municipio", qualidade="maxima"))
        r.raise_for_status()
        tmp = REG / "_tmp.geojson"
        tmp.write_bytes(r.content)
        g = gpd.read_file(tmp).to_crs(4326)
        tmp.unlink()
        g["cod_ibge"] = g["codarea"].astype(int)
        g["nome"] = g["cod_ibge"].map(names)
        g = g[["cod_ibge", "nome", "geometry"]]
        assert len(g) == len(names) == CFG["n_mun"], (len(g), len(names))
        g.to_file(muni, driver="GeoJSON")
        info = {"nome": [CFG["nome"]], "cod_meso": [meso]} if meso else {"nome": [CFG["nome"]], "cod_uf": [41]}
        gpd.GeoDataFrame(info, geometry=[g.union_all()], crs=4326).to_file(union_, driver="GeoJSON")
        print("boundary saved,", len(g), "municipalities")
    b = gpd.read_file(union_).total_bounds
    return (b[0] - MARGIN, b[1] - MARGIN, b[2] + MARGIN, b[3] + MARGIN)


def mapbiomas(bounds):
    MB.mkdir(parents=True, exist_ok=True)
    for y in YEARS:
        dst = MB / f"coverage_{y}.tif"
        if dst.exists():
            continue
        try:
            src = rasterio.open(URL.format(y=y))
        except rasterio.errors.RasterioIOError as e:
            # the Source Cooperative mirror only has 2019-2024; earlier years return 404
            print("mapbiomas", y, "indisponivel:", str(e)[:60], flush=True)
            continue
        with src:
            win = from_bounds(*bounds, transform=src.transform).round_offsets().round_lengths()
            prof = dict(height=win.height, width=win.width, count=1, dtype="uint8",
                        crs=src.crs, transform=src.window_transform(win), nodata=0,
                        compress="deflate", predictor=2, tiled=True, blockxsize=512, blockysize=512)
            tmp = dst.with_suffix(".tmp")
            # read in row strips: the whole of PR does not fit comfortably in RAM at once
            with rasterio.open(tmp, "w", driver="GTiff", **prof) as o:
                for r0 in range(0, win.height, 4096):
                    h = min(4096, win.height - r0)
                    sub = Window(win.col_off, win.row_off + r0, win.width, h)
                    o.write(src.read(1, window=sub).astype("uint8"), 1, window=Window(0, r0, win.width, h))
            shape = (win.height, win.width)
        tmp.rename(dst)
        print("mapbiomas", y, shape, flush=True)


def _dem_blocks(bounds):
    """NASADEM in BLOCK x BLOCK pixel blocks (single 1 arcsec grid), written straight into the GeoTIFF."""
    import planetary_computer as pc
    import pystac_client
    from odc.geo.geobox import GeoBox
    from odc.stac import load
    DEM.parent.mkdir(parents=True, exist_ok=True)
    cat = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1", modifier=pc.sign_inplace)
    items = list(cat.search(collections=["nasadem"], bbox=list(bounds)).items())
    print("itens NASADEM:", len(items), flush=True)
    # grid aligned to integer multiples of 1 arcsec (same convention as the Oeste elev.tif)
    bounds = (np.floor(bounds[0] * 3600) / 3600, np.floor(bounds[1] * 3600) / 3600,
              np.ceil(bounds[2] * 3600) / 3600, np.ceil(bounds[3] * 3600) / 3600)
    gbox = GeoBox.from_bbox(bounds, "EPSG:4326", resolution=1 / 3600)
    h, w = gbox.shape.y, gbox.shape.x
    tr = rasterio.transform.from_origin(bounds[0], bounds[3], 1 / 3600, 1 / 3600)
    prof = dict(driver="GTiff", height=h, width=w, count=1, dtype="float32", crs="EPSG:4326", transform=tr,
                nodata=np.nan, compress="deflate", predictor=3, tiled=True, blockxsize=512, blockysize=512)
    tmp = DEM.with_suffix(".tmp")
    B = 3072
    with rasterio.open(tmp, "w", **prof) as o:
        for r0 in range(0, h, B):
            for c0 in range(0, w, B):
                r1, c1 = min(r0 + B, h), min(c0 + B, w)
                for tent in range(4):
                    try:
                        ds = load(items, bands=["elevation"], geobox=gbox[r0:r1, c0:c1], chunks={},
                                  groupby="solar_day")
                        el = ds.elevation.max("time") if "time" in ds.elevation.dims else ds.elevation
                        arr = el.compute().values.astype("float32")
                        break
                    except Exception as ex:  # noqa: BLE001 - rede instavel
                        print("  retry bloco", r0, c0, type(ex).__name__, flush=True)
                        time.sleep(10)
                else:
                    raise RuntimeError(f"NASADEM falhou no bloco {r0},{c0}")
                arr = np.where(arr < -1000, np.nan, arr)
                o.write(arr, 1, window=Window(c0, r0, c1 - c0, r1 - r0))
            print(f"  NASADEM linha {r0}/{h}", flush=True)
    tmp.rename(DEM)
    print("elev.tif", (h, w), flush=True)


def _slope(dem, transform, crs):
    """Slope (%) of an array: reproject to UTM 22S (meters), gradient, back to the original grid."""
    bounds = rasterio.transform.array_bounds(dem.shape[0], dem.shape[1], transform)
    dst_crs = "EPSG:31982"
    tr, w, h = calculate_default_transform(crs, dst_crs, dem.shape[1], dem.shape[0], *bounds, resolution=30)
    utm = np.full((h, w), np.nan, "float32")
    reproject(dem, utm, src_transform=transform, src_crs=crs, dst_transform=tr,
              dst_crs=dst_crs, resampling=Resampling.bilinear, src_nodata=np.nan, dst_nodata=np.nan)
    gy, gx = np.gradient(utm, 30.0)
    sl = (np.hypot(gx, gy) * 100).astype("float32")
    out = np.full(dem.shape, np.nan, "float32")
    reproject(sl, out, src_transform=tr, src_crs=dst_crs, dst_transform=transform,
              dst_crs=crs, resampling=Resampling.bilinear, src_nodata=np.nan, dst_nodata=np.nan)
    out[np.isnan(dem)] = np.nan
    return out


def _slope_blocks():
    """Slope in blocks with a halo (same algorithm as the small case), for rasters that do not fit in RAM."""
    B, HALO = 3000, 48
    with rasterio.open(DEM) as src:
        prof = src.profile | dict(compress="deflate", predictor=3)
        tmp = SLOPE.with_suffix(".tmp")
        with rasterio.open(tmp, "w", **prof) as o:
            for r0 in range(0, src.height, B):
                for c0 in range(0, src.width, B):
                    r1, c1 = min(r0 + B, src.height), min(c0 + B, src.width)
                    ra, ca = max(r0 - HALO, 0), max(c0 - HALO, 0)
                    rb, cb = min(r1 + HALO, src.height), min(c1 + HALO, src.width)
                    win = Window(ca, ra, cb - ca, rb - ra)
                    dem = src.read(1, window=win)
                    if np.isnan(dem[r0 - ra:r1 - ra, c0 - ca:c1 - ca]).all():
                        out = np.full(dem.shape, np.nan, "float32")
                    else:
                        out = _slope(dem, src.window_transform(win), src.crs)
                    o.write(out[r0 - ra:r1 - ra, c0 - ca:c1 - ca], 1, window=Window(c0, r0, c1 - c0, r1 - r0))
                print(f"  slope linha {r0}/{src.height}", flush=True)
    tmp.rename(SLOPE)
    print("slope_pct.tif", (src.height, src.width), flush=True)


def nasadem(bounds):
    if not DEM.exists() and CFG["blocos"]:
        _dem_blocks(bounds)
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
        arr = np.where(arr < -1000, np.nan, arr)  # NASADEM nodata (-32768) -> NaN
        prof = dict(driver="GTiff", height=arr.shape[0], width=arr.shape[1], count=1, dtype="float32",
                    crs="EPSG:4326", transform=tr, nodata=np.nan, compress="deflate", predictor=3,
                    tiled=True, blockxsize=512, blockysize=512)
        tmp = DEM.with_suffix(".tmp")
        with rasterio.open(tmp, "w", **prof) as o:
            o.write(arr.astype("float32"), 1)
        tmp.rename(DEM)
        print("elev.tif", arr.shape, flush=True)
    if not SLOPE.exists() and CFG["blocos"]:
        SLOPE.parent.mkdir(parents=True, exist_ok=True)
        _slope_blocks()
    if not SLOPE.exists():
        SLOPE.parent.mkdir(parents=True, exist_ok=True)
        # slope: reproject to UTM 22S (meters), gradient, back to 4326 on the original grid
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
    ap = argparse.ArgumentParser()
    ap.add_argument("--regiao", choices=sorted(REGIONS), default="oeste_pr")
    ap.add_argument("--so", choices=["limite", "nasadem", "mapbiomas"], help="roda so uma etapa")
    a = ap.parse_args()
    configure(a.region)
    b = limit()
    print("bbox", b)
    if a.so == "limite":
        return
    if a.so in (None, "nasadem"):
        nasadem(b)
    if a.so in (None, "mapbiomas"):
        mapbiomas(b)


if __name__ == "__main__":
    main()
