"""Timelapse of an FTW field: Sentinel-2 L2A frames + HLS NDVI curve (Planetary Computer).

Usage: uv run python ingest/field_timelapse.py --id 72638 --start 2024-01-01 --end 2026-11-14
"""
import argparse
import os
import subprocess
import time
import warnings
os.environ.update(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR', GDAL_HTTP_MAX_RETRY='4',
                  GDAL_HTTP_RETRY_DELAY='1', CPL_VSIL_CURL_ALLOWED_EXTENSIONS='.tif')
import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
import pystac_client
import planetary_computer as pc
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from rasterio.windows import from_bounds, Window
from rasterio.features import geometry_mask
from scipy.signal import savgol_filter
from concurrent.futures import ThreadPoolExecutor
from PIL import Image
warnings.filterwarnings('ignore')

STAC = 'https://planetarycomputer.microsoft.com/api/stac/v1'
FTW = 'data/processed/ftw/fields_tile_mapbiomas_geo.parquet'
EVENTS = [('2024-02-06', 'colheita soja +\nsemeadura milho'), ('2024-07-19', 'colheita milho'),
          ('2024-10-04', 'semeadura soja')]
NIR = {'hls2-l30': 'B05', 'hls2-s30': 'B8A'}
BAD_SCL = {0, 1, 3, 8, 9, 10, 11}


def ap():
    p = argparse.ArgumentParser()
    p.add_argument('--id', default='72638'); p.add_argument('--start', default='2024-01-01')
    p.add_argument('--end', default='2026-11-14'); p.add_argument('--out', default='data/processed/timelapse')
    p.add_argument('--margin', type=float, default=400); p.add_argument('--min-clear-s2', type=float, default=0.9)
    p.add_argument('--min-clear-hls', type=float, default=0.7); p.add_argument('--fps', type=float, default=2.5)
    p.add_argument('--title-place', default='Toledo/PR')
    return p.parse_args()


def retry(f, n=3):
    for i in range(n):
        try: return f()
        except Exception as e:
            err = e; time.sleep(1.5)
    raise err


# HLS
def hls_obs(args):
    item, coll, poly, crs = args
    try:
        def go():
            it = pc.sign(item); out = {}
            for k, b in [('red', 'B04'), ('nir', NIR[coll]), ('fm', 'Fmask')]:
                with rasterio.open(it.assets[b].href) as s:
                    p = gpd.GeoSeries([poly], crs=crs).to_crs(s.crs).iloc[0]
                    w = from_bounds(*p.bounds, transform=s.transform)
                    c0 = int(np.floor(w.col_off)) - 1; r0 = int(np.floor(w.row_off)) - 1
                    w = Window(c0, r0, int(np.ceil(w.col_off + w.width)) - c0 + 1, int(np.ceil(w.row_off + w.height)) - r0 + 1)
                    out[k] = s.read(1, window=w, boundless=True, fill_value=s.nodata if s.nodata is not None else 0)
                    tr = s.window_transform(w)
            return out, p, tr
        out, p, tr = retry(go)
        m = ~geometry_mask([p], out_shape=out['red'].shape, transform=tr)
        if m.sum() == 0: return None
        fm = out['fm']; red = out['red'].astype('float32'); nir = out['nir'].astype('float32')
        bad = (fm == 255) | ((fm & 0b111111) != 0)
        ok = (~bad) & (red > -9000) & (nir > -9000) & ((red + nir) > 0)
        sel = m & ok
        nd = (nir - red) / (nir + red)
        return dict(data=pd.Timestamp(item.datetime).tz_localize(None).normalize(),
                    sensor='L30' if coll == 'hls2-l30' else 'S30',
                    ndvi_mean=float(nd[sel].mean()) if sel.any() else np.nan,
                    frac_clear=float(sel.sum() / m.sum()))
    except Exception as e:
        print('HLS FAIL', item.id, str(e)[:80], flush=True); return None


def run_hls(cat, geom, crs, ll, start, end):
    poly = geom.buffer(-30); jobs = []
    for coll in NIR:
        its = list(cat.search(collections=[coll], intersects=ll, datetime=f'{start}/{end}').items())
        jobs += [(i, coll, poly, crs) for i in its]
    print('HLS itens:', len(jobs), flush=True)
    with ThreadPoolExecutor(16) as ex: res = [r for r in ex.map(hls_obs, jobs) if r]
    return pd.DataFrame(res).sort_values('data').reset_index(drop=True)


def smooth(df, start, end, min_clear):
    d = df[(df.frac_clear >= min_clear) & df.ndvi_mean.notna()]
    grid = pd.date_range(start, end, freq='10D')
    k = ((d.data - grid[0]).dt.days // 10).clip(0, len(grid) - 1)
    b = d.groupby(k).ndvi_mean.mean().reindex(range(len(grid)))
    s = pd.Series(b.values.astype(float), index=grid).interpolate(limit_direction='both')
    return pd.Series(savgol_filter(s.values, 5, 2), index=grid)


# S2
def s2_scl(args):
    item, bounds, shape, mask = args
    try:
        def go():
            it = pc.sign(item)
            with rasterio.open(it.assets['SCL'].href) as s:
                w = from_bounds(*bounds, transform=s.transform)
                return s.read(1, window=w, out_shape=shape, resampling=rasterio.enums.Resampling.nearest, boundless=True, fill_value=0)
        scl = retry(go)
        ok = ~np.isin(scl, list(BAD_SCL))
        return item, float((ok & mask).sum() / mask.sum())
    except Exception as e:
        print('SCL FAIL', item.id, str(e)[:80], flush=True); return item, None


def s2_bands(args):
    item, bounds, shape = args
    def go():
        it = pc.sign(item); arr = []
        for b in ['B04', 'B03', 'B02', 'B08', 'SCL']:
            with rasterio.open(it.assets[b].href) as s:
                w = from_bounds(*bounds, transform=s.transform)
                arr.append(s.read(1, window=w, out_shape=shape, resampling=rasterio.enums.Resampling.nearest if b == 'SCL' else rasterio.enums.Resampling.bilinear, boundless=True, fill_value=0).astype('float32'))
        return np.stack(arr)
    return retry(go)


def main():
    a = ap(); os_ = a.out; os.makedirs(f'{os_}/frames', exist_ok=True)
    g = gpd.read_parquet(FTW); g = g[g.id.astype(str) == str(a.id)]
    assert len(g) == 1, 'talhão não encontrado'
    geom = g.geometry.iloc[0]; crs = g.crs
    ll = gpd.GeoSeries([geom.centroid], crs=crs).to_crs(4326).iloc[0].__geo_interface__
    cat = pystac_client.Client.open(STAC)
    start, end = a.start, a.end

    # HLS
    hls_csv = f'{os_}/ndvi_hls_{a.id}.csv'
    hls = run_hls(cat, geom, crs, ll, start, end)
    hls.to_csv(hls_csv, index=False); print('HLS obs:', len(hls))
    curve = smooth(hls, start, end, a.min_clear_hls)

    # S2 window: bbox + margin, on the 10 m grid
    minx, miny, maxx, maxy = geom.bounds; m = a.margin
    bx = [np.floor((minx - m) / 10) * 10, np.floor((miny - m) / 10) * 10, np.ceil((maxx + m) / 10) * 10, np.ceil((maxy + m) / 10) * 10]
    shape = (int((bx[3] - bx[1]) / 10), int((bx[2] - bx[0]) / 10))
    tr = rasterio.transform.from_bounds(*bx, shape[1], shape[0])
    fmask = ~geometry_mask([geom], out_shape=shape, transform=tr)
    epsg = crs.to_epsg()
    items = [i for i in cat.search(collections=['sentinel-2-l2a'], intersects=ll, datetime=f'{start}/{end}').items()
             if i.properties.get('proj:code', f"EPSG:{i.properties.get('proj:epsg')}") == f'EPSG:{epsg}']
    print('S2 itens (mesmo CRS):', len(items), flush=True)
    with ThreadPoolExecutor(16) as ex: res = [r for r in ex.map(s2_scl, [(i, bx, shape, fmask) for i in items]) if r[1] is not None]
    scn = pd.DataFrame([dict(data=pd.Timestamp(i.datetime).tz_localize(None).normalize(), cena=i.id, frac_clear=f) for i, f in res])
    byid = {i.id: i for i, _ in res}
    scn['item'] = scn.cena
    scn.drop(columns='item').sort_values('data').to_csv(f'{os_}/cenas_s2_{a.id}.csv', index=False)
    print('S2 cenas avaliadas:', len(scn))
    # selection per 10-day window
    grid = pd.date_range(start, end, freq='10D')
    scn['jan'] = ((scn.data - pd.Timestamp(start)).dt.days // 10)
    good = scn[scn.frac_clear >= a.min_clear_s2]
    sel = good.sort_values(['frac_clear', 'data'], ascending=[False, True]).groupby('jan').head(1).sort_values('data').reset_index(drop=True)
    print('Quadros selecionados:', len(sel), flush=True)
    sel[['data', 'cena', 'frac_clear']].to_csv(f'{os_}/cenas_s2_selecionadas_{a.id}.csv', index=False)

    with ThreadPoolExecutor(8) as ex:
        data = list(ex.map(s2_bands, [(byid[c], bx, shape) for c in sel.cena]))
    rgbs = []; ndvis = []; clears = []
    for d in data:
        refl = (d[:4] - 1000) / 10000
        rgbs.append(np.moveaxis(refl[:3], 0, -1))
        nd = (refl[3] - refl[0]) / (refl[3] + refl[0] + 1e-9)
        ok = ~np.isin(d[4], list(BAD_SCL))
        ndvis.append(np.where(ok, nd, np.nan)); clears.append(ok)
    inside = np.concatenate([r[fmask & c] for r, c in zip(rgbs, clears)]).ravel()
    lo, hi = np.percentile(inside, [2, 98]); print('estiramento', lo, hi)

    extent = (bx[0], bx[2], bx[1], bx[3])
    ex_, ey_ = geom.exterior.coords.xy if geom.geom_type == 'Polygon' else geom.geoms[0].exterior.coords.xy
    def outline(ax):
        ax.plot(ex_, ey_, color='yellow', lw=1.6)
    smax = pd.Timestamp(end)
    for idx, row in sel.iterrows():
        dt = row.data
        fig = plt.figure(figsize=(12.8, 7.2), dpi=100)
        gs = fig.add_gridspec(2, 2, height_ratios=[2.3, 1], left=0.04, right=0.97, top=0.84, bottom=0.08, hspace=0.28, wspace=0.0)
        a1 = fig.add_subplot(gs[0, 0]); a2 = fig.add_subplot(gs[0, 1]); a3 = fig.add_subplot(gs[1, :])
        img = np.clip((rgbs[idx] - lo) / (hi - lo), 0, 1)
        a1.imshow(img, extent=extent); a2.imshow(ndvis[idx], extent=extent, cmap='RdYlGn', vmin=0, vmax=1)
        for ax in (a1, a2):
            outline(ax); ax.set_xlim(extent[0], extent[1]); ax.set_ylim(extent[2], extent[3]); ax.set_xticks([]); ax.set_yticks([])
        x0 = extent[0] + 40; y0 = extent[2] + 40
        a1.plot([x0, x0 + 500], [y0, y0], color='white', lw=3); a1.text(x0 + 250, y0 + 25, '500 m', color='white', ha='center', fontsize=9, fontweight='bold')
        a1.set_title('Cor verdadeira (B4/B3/B2)', fontsize=10); a2.set_title('NDVI Sentinel-2 (0–1)', fontsize=10)
        sm = plt.cm.ScalarMappable(cmap='RdYlGn', norm=plt.Normalize(0, 1)); cb = fig.colorbar(sm, cax=a2.inset_axes([0.1, -0.07, 0.8, 0.03]), orientation='horizontal'); cb.ax.tick_params(labelsize=7)
        a1.set_anchor('E'); a2.set_anchor('W')
        # curva
        a3.plot(hls[hls.frac_clear >= a.min_clear_hls].data, hls[hls.frac_clear >= a.min_clear_hls].ndvi_mean, '.', color='0.6', ms=3, label='HLS obs.')
        a3.plot(curve.index, curve.values, color='darkgreen', lw=2, label='NDVI suavizado')
        for y in range(pd.Timestamp(start).year, smax.year + 1):
            s0, s1 = pd.Timestamp(f'{y}-06-02'), pd.Timestamp(f'{y}-08-31')
            a3.axvspan(s0, s1, color='tab:orange', alpha=0.18, lw=0)
            a3.text(s0 + (s1 - s0) / 2, 1.04, 'vazio sanitário', ha='center', va='bottom', fontsize=7.5, color='darkorange')
        for k, (e, lab) in enumerate(EVENTS):
            a3.axvline(pd.Timestamp(e), color='k', lw=0.7, ls='--'); a3.text(pd.Timestamp(e), 0.02 + 0.0 * k, ' ' + lab, fontsize=7, va='bottom', ha='left', rotation=0)
        a3.axvline(dt, color='red', lw=2)
        a3.set_xlim(pd.Timestamp(start), smax); a3.set_ylim(0, 1.0); a3.set_ylabel('NDVI', fontsize=9)
        a3.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 4, 7, 10])); a3.xaxis.set_major_formatter(mdates.DateFormatter('%m/%y')); a3.tick_params(labelsize=8)
        a3.legend(loc='upper right', fontsize=7, ncol=2, bbox_to_anchor=(1, 0.995), frameon=False)
        # fase inferida
        v = float(curve.iloc[np.argmin(np.abs((curve.index - dt).days))]); mo = dt.month
        if v < 0.4: phase = 'pousio / solo exposto'
        elif mo in (10, 11, 12, 1): phase = 'soja'
        elif mo in (2, 3, 4, 5, 6, 7): phase = 'milho safrinha' if mo >= 3 or v > 0.5 else 'soja (final) / milho'
        else: phase = 'pousio / vegetação'
        fig.suptitle(f'Talhão {a.id} — {a.title_place} — {dt:%d/%m/%Y}', fontsize=16, fontweight='bold', y=0.97)
        fig.text(0.5, 0.905, f'Sentinel-2 L2A (cena {row.cena[-22:-16]}, {row.frac_clear*100:.0f}% limpa) | NDVI curva: HLS | fase inferida: {phase}', ha='center', fontsize=10, color='0.25')
        fig.text(0.5, 0.012, 'Imagem: Copernicus Sentinel-2 | NDVI: NASA HLS | Limite: Fields of The World', ha='center', fontsize=8, color='0.45')
        fig.savefig(f'{os_}/frames/frame_{idx:03d}.png'); plt.close(fig)
    print('quadros salvos')

    files = [f'{os_}/frames/frame_{i:03d}.png' for i in range(len(sel))]
    ims = [Image.open(f).convert('RGB') for f in files]
    w = 960; gif_ims = [im.resize((w, int(w * 9 / 16)), Image.LANCZOS).quantize(128, dither=Image.Dither.NONE) for im in ims]
    gif_ims[0].save(f'{os_}/talhao_{a.id}.gif', save_all=True, append_images=gif_ims[1:], duration=int(1000 / a.fps), loop=0, optimize=True)
    print('gif MB', os.path.getsize(f'{os_}/talhao_{a.id}.gif') / 1e6)
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-framerate', str(a.fps), '-i', f'{os_}/frames/frame_%03d.png',
                    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', f'{os_}/talhao_{a.id}.mp4'], check=True)
    print('ok')


if __name__ == '__main__':
    main()
