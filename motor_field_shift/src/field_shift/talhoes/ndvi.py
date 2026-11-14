"""Passo 3: serie mensal de NDVI (Sentinel-2 L2A, Planetary Computer) por talhao."""
import sys, time
import numpy as np, pandas as pd, geopandas as gpd, planetary_computer as pc, pystac_client, xarray as xr
import rasterio
from rasterio.transform import from_origin
from odc.stac import load
from exactextract import exact_extract
from field_shift.talhoes.common import OUT, candidates, YEARS

BOX = [-53.64, -24.72, -53.40, -24.60]   # recorte de trabalho (~24 x 13 km)
RES = 20

def main():
    c = candidates()
    c4 = c.to_crs(4326)
    cen = c4.to_crs(31982).geometry.centroid.to_crs(4326)
    sel = c4[(cen.x.between(BOX[0], BOX[2])) & (cen.y.between(BOX[1], BOX[3]))].copy()
    sel["id"] = sel["id"].astype(str)
    print("candidatos na caixa:", len(sel), flush=True)
    sel[["id"]].assign(geometry=sel.geometry).pipe(gpd.GeoDataFrame, crs=4326).to_file(OUT / "candidatos_box.gpkg", driver="GPKG")
    b = sel.total_bounds; pad = 0.003
    bbox = [b[0]-pad, b[1]-pad, b[2]+pad, b[3]+pad]
    cat = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1", modifier=pc.sign_inplace)
    rows = []
    for y in YEARS:
        t0 = time.time()
        items = list(cat.search(collections=["sentinel-2-l2a"], bbox=bbox, datetime=f"{y}-01-01/{y}-12-31",
                                query={"eo:cloud_cover": {"lt": 85}}).items())
        # offset de reflectancia: baseline >= 04.00 => -1000
        off = {}
        for it in items:
            bl = it.properties.get("s2:processing_baseline", "02.00")
            off.setdefault(it.datetime.strftime("%Y-%m-%d"), []).append(1000 if float(bl) >= 4.0 else 0)
        ds = load(items, bands=["B04", "B08", "SCL"], bbox=bbox, crs="EPSG:32722", resolution=RES,
                  groupby="solar_day", chunks={"x": 512, "y": 512}, dtype={"SCL": "uint8"} if False else None,
                  resampling={"SCL": "nearest", "*": "bilinear"}, fail_on_error=False)
        days = pd.to_datetime(ds.time.values).strftime("%Y-%m-%d")
        o = xr.DataArray([max(off.get(d, [0])) for d in days], dims="time", coords={"time": ds.time})
        red = (ds.B04.astype("float32") - o).clip(min=0); nir = (ds.B08.astype("float32") - o).clip(min=0)
        ndvi = (nir - red) / (nir + red + 1e-6)
        ok = ds.SCL.isin([4, 5, 6]) & (ds.B04 > 0)
        ndvi = ndvi.where(ok)
        mon = ndvi.groupby("time.month").median("time", skipna=True).compute()
        cnt = ok.groupby("time.month").sum("time").compute()  # obs validas por pixel (soma)
        print(y, "itens", len(items), "dias", len(days), f"{time.time()-t0:.0f}s", flush=True)
        # zonal por mes
        xs = ds.x.values; ys = ds.y.values
        tr = from_origin(xs.min()-RES/2, ys.max()+RES/2, RES, RES)
        g32 = sel.to_crs(32722)
        for m in mon.month.values:
            a = mon.sel(month=m).values.astype("float32")
            if np.isnan(a).all():
                continue
            fn = OUT / "_tmp_ndvi.tif"
            with rasterio.open(fn, "w", driver="GTiff", height=a.shape[0], width=a.shape[1], count=1, dtype="float32",
                               crs="EPSG:32722", transform=tr, nodata=np.nan) as dst:
                dst.write(a, 1)
            r = exact_extract(str(fn), g32, ["mean", "median", "count", "coverage"] if False else ["mean", "count"],
                              include_cols=["id"], output="pandas", progress=False)
            r["year"] = y; r["month"] = int(m)
            r["n_obs_dias"] = int((pd.Series(days).str[5:7].astype(int) == m).sum())
            rows.append(r)
    (OUT / "_tmp_ndvi.tif").unlink(missing_ok=True)
    df = pd.concat(rows).rename(columns={"mean": "ndvi", "count": "n_pix_validos"})
    df["id"] = df.id.astype(str)
    df["date"] = pd.to_datetime(dict(year=df.year, month=df.month, day=1))
    df.to_csv(OUT / "ndvi_mensal_candidatos.csv", index=False)
    print(df.shape, df.ndvi.describe())

if __name__ == "__main__":
    main()
