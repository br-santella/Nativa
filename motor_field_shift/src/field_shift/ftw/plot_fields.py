"""Figura RGB + polígonos FTW. Uso: plot_fields.py scene.tif fields.gpkg out.png"""
import sys, numpy as np, rasterio, geopandas as gpd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
scene, fields, out = sys.argv[1:4]
with rasterio.open(scene) as s:
    img = s.read().astype(float); b = s.bounds
g = gpd.read_file(fields).to_crs(32722)
def rgb(off):  # ordem FTW: R,G,B,NIR por janela
    x = np.moveaxis(img[off:off+3], 0, -1)
    return np.clip(x / np.nanpercentile(x, 98), 0, 1)
ext = (b.left, b.right, b.bottom, b.top)
cx, cy = (b.left+b.right)/2, (b.bottom+b.top)/2
zoom = (cx-1000, cx+1000, cy-1000, cy+1000)
fig, ax = plt.subplots(2, 2, figsize=(16, 16))
for j, (off, nm) in enumerate([(0, "Janela A (nov/2023)"), (4, "Janela B (jan/2024)")]):
    ax[0, j].imshow(rgb(off), extent=ext); ax[0, j].set_title(nm + " RGB")
    ax[1, j].imshow(rgb(off), extent=ext)
    g.boundary.plot(ax=ax[1, j], color="yellow", linewidth=0.5)
    ax[1, j].set_title(nm + " + talhões FTW")
for a in ax.ravel(): a.set_xticks([]); a.set_yticks([])
fig.tight_layout(); fig.savefig(out.replace(".png", "_overview.png"), dpi=90)
fig, ax = plt.subplots(1, 2, figsize=(16, 8))
for j, off in enumerate([0, 4]):
    ax[j].imshow(rgb(off), extent=ext)
    g.boundary.plot(ax=ax[j], color="yellow" if j else "cyan", linewidth=1)
    ax[j].set_xlim(zoom[0], zoom[1]); ax[j].set_ylim(zoom[2], zoom[3]); ax[j].set_xticks([]); ax[j].set_yticks([])
fig.tight_layout(); fig.savefig(out.replace(".png", "_zoom2km.png"), dpi=90)
