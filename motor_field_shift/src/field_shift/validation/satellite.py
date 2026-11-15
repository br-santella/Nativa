"""Satellite check of the catalog (docs/validation.md, section 5): MapBiomas land cover and HLS NDVI of real fields.

- MapBiomas (annual, 2019–2024, attributes already joined to the FTW fields): is soybean in summer the norm in the Oeste?
- HLS NDVI (NASA Harmonized Landsat Sentinel-2, via Planetary Computer) of a sample of FTW fields around field 72638, with the
  engine's own detection (`engine.picos_por_ano_agricola`, NDVI < 0.35 = bare soil):
    * what rotations are practised (two NDVI peaks per agricultural year = summer crop + second crop);
    * bare-soil days per year, double-crop vs single-crop years (catalog: `dias_descobertos`);
    * NDVI of the following soybean after a double-crop vs a single-crop year (proxy for the catalog bonus).

Each HLS scene is read once, in a window covering every sampled field; the per-field mean NDVI uses only clear pixels (Fmask).
"""
from __future__ import annotations

import os
import time
import warnings
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

os.environ.update(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_MAX_RETRY="4", GDAL_HTTP_RETRY_DELAY="1",
                  CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif")

import geopandas as gpd  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from field_shift.app import engine as E  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
FTW = ROOT / "data/processed/ftw/fields_tile_mapbiomas_geo.parquet"
OUT = ROOT / "data/processed/validation"
NDVI_FILE = OUT / "satellite_ndvi_fields.parquet"
STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
NIR = {"hls2-l30": "B05", "hls2-s30": "B8A"}
CENTER_FIELD = "72638"
HALF_BOX_M = 10_000      # 20 × 20 km box around field 72638
MIN_AREA_HA = 20.0
START, END = "2019-07-01", "2025-08-31"   # agricultural years 2019/20 … 2024/25 (Sep–Aug)
MAX_CLOUD = 80
MIN_CLEAR = 0.7          # same threshold as engine.carregar_ndvi


# MapBiomas


def mapbiomas_summary() -> dict:
    """Share of the agricultural area (FTW fields with is_agri) by number of soybean years in 2019–2024."""
    g = pd.read_parquet(FTW, columns=["id", "area_ha", "is_agri", "n_years_soy", "lc_2024_name"])
    a = g[g["is_agri"]]
    share = (a.groupby("n_years_soy")["area_ha"].sum() / a["area_ha"].sum()).to_dict()
    return dict(fields=len(a), area_ha=float(a["area_ha"].sum()), share_area_by_soy_years={int(k): float(v) for k, v in share.items()},
                share_area_soy_every_year=float(share.get(6, 0.0)))


# HLS sample


def sample_fields() -> gpd.GeoDataFrame:
    g = gpd.read_parquet(FTW)
    c = g[g["id"].astype(str) == CENTER_FIELD].geometry.centroid.iloc[0]
    box = c.buffer(HALF_BOX_M, cap_style=3)
    s = g[g["is_agri"] & (g["area_ha"] >= MIN_AREA_HA) & g.geometry.centroid.within(box)]
    return s[["id", "area_ha", "n_years_soy", "geometry"]].reset_index(drop=True)


def _retry(f, n=4):
    err = None
    for i in range(n):
        try:
            return f()
        except Exception as e:  # network hiccups on signed COG reads
            err = e
            time.sleep(1.5 * (i + 1))
    raise err


def _scene(args) -> list[dict]:
    """Per-field mean NDVI and clear fraction for one HLS scene."""
    import planetary_computer as pc
    import rasterio
    from rasterio.features import rasterize
    from rasterio.windows import Window, from_bounds

    item, coll, fields = args
    try:
        def go():
            it = pc.sign(item)
            out = {}
            for k, b in (("red", "B04"), ("nir", NIR[coll]), ("fm", "Fmask")):
                with rasterio.open(it.assets[b].href) as src:
                    f = fields.to_crs(src.crs)
                    w = from_bounds(*f.total_bounds, transform=src.transform)
                    w = Window(int(np.floor(w.col_off)) - 1, int(np.floor(w.row_off)) - 1,
                               int(np.ceil(w.width)) + 3, int(np.ceil(w.height)) + 3)
                    out[k] = src.read(1, window=w, boundless=True, fill_value=255 if k == "fm" else -9999)
                    tr, crs = src.window_transform(w), src.crs
            return out, tr, crs

        out, tr, crs = _retry(go)
        f = fields.to_crs(crs)
        shapes = [(geom.buffer(-30), i + 1) for i, geom in enumerate(f.geometry) if not geom.buffer(-30).is_empty]
        lab = rasterize(shapes, out_shape=out["red"].shape, transform=tr, fill=0, dtype="int32")
        red, nir, fm = out["red"].astype("float32"), out["nir"].astype("float32"), out["fm"]
        ok = (fm != 255) & ((fm & 0b111111) == 0) & (red > -9000) & (nir > -9000) & ((red + nir) > 0)
        ndvi = np.where(ok, (nir - red) / np.where((nir + red) == 0, 1, nir + red), 0.0)
        n = len(f) + 1
        tot = np.bincount(lab.ravel(), minlength=n)
        clear = np.bincount(lab.ravel(), weights=ok.ravel().astype(float), minlength=n)
        s = np.bincount(lab.ravel(), weights=ndvi.ravel(), minlength=n)
        day = pd.Timestamp(item.datetime).tz_localize(None).normalize()
        sensor = "L30" if coll == "hls2-l30" else "S30"
        return [dict(id=str(fields["id"].iloc[i - 1]), data=day, sensor=sensor,
                     ndvi_mean=float(s[i] / clear[i]) if clear[i] else np.nan, frac_clear=float(clear[i] / tot[i]))
                for i in range(1, n) if tot[i] > 0]
    except Exception as e:
        print("HLS FAIL", item.id, str(e)[:100], flush=True)
        return []


def fetch_ndvi(fields: gpd.GeoDataFrame, start: str = START, end: str = END, workers: int = 16) -> pd.DataFrame:
    """HLS L30 + S30 scenes over the sample (cloud cover ≤ MAX_CLOUD), per-field NDVI. Saves NDVI_FILE."""
    import pystac_client
    warnings.filterwarnings("ignore")
    cat = pystac_client.Client.open(STAC)
    box = gpd.GeoSeries([fields.union_all().envelope], crs=fields.crs).to_crs(4326).iloc[0].__geo_interface__
    jobs = []
    for coll in NIR:
        items = list(cat.search(collections=[coll], intersects=box, datetime=f"{start}/{end}",
                                query={"eo:cloud_cover": {"lte": MAX_CLOUD}}).items())
        jobs += [(i, coll, fields) for i in items]
    print("HLS scenes:", len(jobs), flush=True)
    rows = []
    with ThreadPoolExecutor(workers) as ex:
        for k, r in enumerate(ex.map(_scene, jobs), start=1):
            rows += r
            if k % 100 == 0:
                print(f"  {k}/{len(jobs)} scenes", flush=True)
    df = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_parquet(NDVI_FILE)
    return df


# Per field-year metrics (engine logic)


def daily_series(obs: pd.DataFrame) -> pd.Series:
    """Same smoothing as engine.carregar_ndvi: clear obs, same-day mean, daily interpolation, 15-day rolling mean."""
    d = obs[(obs["frac_clear"] >= MIN_CLEAR) & obs["ndvi_mean"].notna()]
    s = d.groupby("data")["ndvi_mean"].mean().sort_index()
    s = s.resample("D").mean().interpolate(limit_area="inside")
    return s.rolling(15, center=True, min_periods=1).mean()


def field_years(ndvi: pd.DataFrame, max_gap_days: int = 45) -> pd.DataFrame:
    """One row per field × agricultural year (Sep–Aug): peaks (engine rule), bare-soil days (NDVI < 0.35), summer peak NDVI
    (Nov–Feb max) and integral of NDVI over the summer (Oct–Mar). Years with a clear-observation gap > max_gap_days are
    dropped (interpolation would invent or hide a crop)."""
    from scipy.signal import find_peaks
    rows = []
    for fid, obs in ndvi.groupby("id"):
        s = daily_series(obs)
        if s.empty:
            continue
        clear_days = obs[(obs["frac_clear"] >= MIN_CLEAR) & obs["ndvi_mean"].notna()]["data"].drop_duplicates().sort_values()
        for year in range(2019, 2025):
            start, end = pd.Timestamp(year, 9, 1), pd.Timestamp(year + 1, 8, 31)
            if start < s.index.min() or end > s.index.max():
                continue
            cd = clear_days[(clear_days >= start - pd.Timedelta(days=20)) & (clear_days <= end + pd.Timedelta(days=20))]
            gap = cd.diff().dt.days.max() if len(cd) > 1 else 999
            t = s[start:end]
            p, _ = find_peaks(t.values, height=0.6, prominence=0.2, distance=40)  # same rule as the engine
            summer = s[pd.Timestamp(year, 11, 1):pd.Timestamp(year + 1, 2, 28)]
            rows.append(dict(id=fid, year=f"{year}/{str(year + 1)[2:]}", y0=year, peaks=len(p), max_gap=float(gap),
                             bare_days=int((t < E.SOIL_THRESHOLD).sum()),
                             bare_days_2nd_window=int((s[pd.Timestamp(year + 1, 1, 15):pd.Timestamp(year + 1, 8, 31)] < E.SOIL_THRESHOLD).sum()),
                             summer_peak=float(summer.max()), summer_integral=float(s[pd.Timestamp(year, 10, 1):pd.Timestamp(year + 1, 3, 31)].sum())))
    fy = pd.DataFrame(rows)
    fy = fy[fy["max_gap"] <= max_gap_days].copy()
    fy["double"] = fy["peaks"] >= 2
    return fy


def following_soy_effect(fy: pd.DataFrame) -> pd.DataFrame:
    """Summer NDVI of year t+1 by the previous year's pattern (double vs single crop), with field and year effects removed
    (two-way demeaning of the outcome); only soybean-every-year fields."""
    nxt = fy[["id", "y0", "summer_peak", "summer_integral"]].copy()
    nxt["y0"] -= 1
    d = fy[["id", "y0", "double"]].merge(nxt, on=["id", "y0"], suffixes=("", "_next"))
    out = []
    for col in ("summer_peak", "summer_integral"):
        v = d[col]
        resid = v - d.groupby("id")[col].transform("mean") - d.groupby("y0")[col].transform("mean") + v.mean()
        out.append(dict(outcome=f"{col} of next summer", n=len(d), n_after_double=int(d["double"].sum()),
                        raw_after_double=float(v[d["double"]].mean()), raw_after_single=float(v[~d["double"]].mean()),
                        adjusted_diff=float(resid[d["double"]].mean() - resid[~d["double"]].mean())))
    return pd.DataFrame(out)
