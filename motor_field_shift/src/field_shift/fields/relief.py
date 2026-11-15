"""Passo 2: relevo (NASADEM, Planetary Computer) por talhao candidato."""
import numpy as np, pandas as pd, geopandas as gpd, planetary_computer as pc, pystac_client
import rioxarray  # noqa
from odc.stac import load
from exactextract import exact_extract
import rasterio
from rasterio.transform import from_origin
from field_shift.fields.common import OUT, candidates

def main():
    c = candidates()
    print("candidatos 20-200 ha, soja>=5/6:", len(c))
    c4 = c.to_crs(4326)
    b = c4.total_bounds; pad = 0.03
    bbox = [b[0]-pad, b[1]-pad, b[2]+pad, b[3]+pad]
    cat = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1", modifier=pc.sign_inplace)
    items = list(cat.search(collections=["nasadem"], bbox=bbox).items())
    print("itens NASADEM:", len(items))
    ds = load(items, bands=["elevation"], bbox=bbox, crs="EPSG:4326", resolution=1/3600, chunks={})
    el = ds.elevation.isel(time=0).compute().astype("float32")
    el = el.where(el > -1000)
    arr = el.values; lat = el.latitude.values; lon = el.longitude.values
    # declividade em %
    dy = abs(lat[1]-lat[0])*111320.0
    dx = abs(lon[1]-lon[0])*111320.0*np.cos(np.deg2rad(lat))[:, None]
    gy, gx = np.gradient(arr, dy, axis=0)[0:1][0] if False else (np.gradient(arr, axis=0)/dy, None)
    gx = np.gradient(arr, axis=1)/dx
    slope = np.hypot(gy, gx)*100
    res = abs(lon[1]-lon[0])
    tr = from_origin(lon.min()-res/2, lat.max()+res/2, res, res)
    # latitude decresce? garantir norte no topo
    if lat[0] < lat[-1]:
        arr = arr[::-1]; slope = slope[::-1]
    prof = dict(driver="GTiff", height=arr.shape[0], width=arr.shape[1], count=1, dtype="float32",
                crs="EPSG:4326", transform=tr, nodata=np.nan, compress="deflate")
    for name, a in [("nasadem_elev", arr), ("nasadem_slope_pct", slope)]:
        with rasterio.open(OUT / f"{name}.tif", "w", **prof) as o:
            o.write(a.astype("float32"), 1)
    ids = c4[["id"]].reset_index(drop=True)
    # raster precisa de estatistica por poligono
    def stats(layer, ops, geoms):
        g = gpd.GeoDataFrame({"id": c4["id"].values}, geometry=geoms, crs=4326)
        return exact_extract(str(OUT / f"{layer}.tif"), g, ops, include_cols=["id"], output="pandas", progress=False)
    s_el = stats("nasadem_elev", ["mean"], c4.geometry)
    s_sl = stats("nasadem_slope_pct", ["mean", "quantile(q=0.9)"], c4.geometry)
    ring = c.geometry.buffer(1000).difference(c.geometry)
    ring = gpd.GeoSeries(ring, crs=c.crs).to_crs(4326)
    s_ring = stats("nasadem_elev", ["mean"], ring.values)
    out = pd.DataFrame({"id": c4["id"].values,
                        "elev_mean": s_el["mean"].values,
                        "slope_mean_pct": s_sl["mean"].values,
                        "slope_p90_pct": s_sl.filter(like="quantile").iloc[:, 0].values,
                        "elev_ring1km": s_ring["mean"].values})
    out["alt_rel"] = out.elev_mean - out.elev_ring1km
    out.to_csv(OUT / "relevo_candidatos.csv", index=False)
    print(out.describe().T)

if __name__ == "__main__":
    main()
