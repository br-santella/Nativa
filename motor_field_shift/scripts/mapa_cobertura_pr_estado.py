"""Generate docs/figuras/mapa_cobertura_api_pr_estado.png: API coverage over the whole state of Paraná."""
from pathlib import Path

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/figuras/mapa_cobertura_api_pr_estado.png"
FIELD_ID = "72638"
GREEN, GREEN_DARK = "#1b7f5c", "#0b4a35"
CITIES = ["Curitiba", "Londrina", "Maringá", "Ponta Grossa", "Cascavel", "Foz do Iguaçu",
          "Guarapuava", "Toledo", "Umuarama", "Francisco Beltrão", "Paranavaí", "Campo Mourão"]


def fmt_br(value: float) -> str:
    """Format an integer with pt-BR thousands separator."""
    return f"{value:,.0f}".replace(",", ".")


mun = gpd.read_file(ROOT / "data/raw/regiao/municipios_pr.geojson").to_crs(4326)
state = gpd.read_file(ROOT / "data/raw/regiao/pr.geojson").to_crs(4326)
west = gpd.read_file(ROOT / "data/raw/regiao/oeste_pr.geojson").to_crs(4326)
west_mun = gpd.read_file(ROOT / "data/raw/regiao/municipios_oeste_pr.geojson").to_crs(4326)
climate = pd.read_parquet(ROOT / "data/processed/clima_pr/indicadores.parquet")
stations = pd.read_csv(ROOT / "data/processed/clima_pr/inmet_estacoes.csv")
field = gpd.read_parquet(ROOT / "data/processed/ftw/fields_tile_mapbiomas_geo.parquet")
field = field[field["id"].astype(str) == FIELD_ID]
fc = field.to_crs(31982).centroid.to_crs(4326).iloc[0]

n_mun = len(mun)
area_km2 = mun.to_crs(5880).union_all().area / 1e6
cells = climate[climate["tipo"] == "celula"][["lat", "lon"]].drop_duplicates()
if "uf" in stations.columns:
    stations = stations[stations["uf"] == "PR"]
print(f"Area: {area_km2:,.0f} km2 | municipios: {n_mun} | celulas POWER: {len(cells)} | estacoes INMET: {len(stations)}")

fig, ax = plt.subplots(figsize=(12, 8.2))
mun.plot(ax=ax, facecolor=GREEN, alpha=0.45, edgecolor="white", linewidth=0.3)
west_mun.plot(ax=ax, facecolor=GREEN, alpha=0.30, edgecolor="none")
west.boundary.plot(ax=ax, color=GREEN_DARK, linewidth=2.2)
state.boundary.plot(ax=ax, color="#222", linewidth=1.2)

for la, lo in zip(cells.lat, cells.lon):
    ax.add_patch(Rectangle((lo - .3125, la - .25), .625, .5, fill=False, ec="#2b6cb0", lw=0.5,
                           ls="--", alpha=.7, zorder=3))
ax.scatter(stations.lon, stations.lat, marker="^", s=45, c="#d97706", ec="black", lw=.6, zorder=6)
ax.scatter([fc.x], [fc.y], marker="*", s=330, c="#e11d48", ec="black", lw=.8, zorder=7)
ax.annotate(f"Talhão demo {FIELD_ID}", (fc.x, fc.y), xytext=(-70, -50), textcoords="offset points",
            fontsize=8.5, fontweight="bold", color="#e11d48",
            arrowprops=dict(arrowstyle="-", color="#e11d48", lw=.8),
            bbox=dict(boxstyle="round,pad=.2", fc="white", ec="#e11d48", lw=.6), zorder=8)

mun_m = mun.to_crs(5880)
for name in CITIES:
    row = mun_m[mun_m["nome"].str.lower() == name.lower()]
    if row.empty:
        print("cidade-polo nao encontrada:", name)
        continue
    pt = gpd.GeoSeries([row.geometry.iloc[0].representative_point()], crs=5880).to_crs(4326).iloc[0]
    ax.plot(pt.x, pt.y, "o", ms=3, c="black", zorder=5)
    ax.annotate(name, (pt.x, pt.y), xytext=(4, 3), textcoords="offset points", fontsize=8, zorder=9,
                path_effects=[pe.withStroke(linewidth=2.4, foreground="white")])

minx, miny, maxx, maxy = state.total_bounds
print("bounds:", minx, miny, maxx, maxy)
ax.set_xlim(minx - .3, maxx + .3)
ax.set_ylim(miny - .3, maxy + .3)
ax.set_aspect(1 / np.cos(np.radians((miny + maxy) / 2)))
ax.set_xlabel("Longitude")
ax.set_ylabel("Latitude")
ax.grid(ls=":", lw=.3, alpha=.5)
ax.set_title("Field Shift — Cobertura da API no Paraná", fontsize=16, fontweight="bold", pad=12)

handles = [
    Patch(fc=GREEN, alpha=.45, ec="white", label=f"Municípios cobertos ({n_mun})"),
    Patch(fc=GREEN, alpha=.75, ec=GREEN_DARK, lw=2, label="Oeste do PR — região piloto\n(talhão demo, validação)"),
    Line2D([], [], color="#2b6cb0", ls="--", lw=1, label=f"Células NASA POWER ({len(cells)}; 0,5° x 0,625°)"),
    Line2D([], [], marker="^", ls="", mfc="#d97706", mec="black", ms=8, label=f"Estações INMET ({len(stations)})"),
    Line2D([], [], marker="*", ls="", mfc="#e11d48", mec="black", ms=14, label=f"Talhão demo {FIELD_ID}"),
]
ax.legend(handles=handles, loc="lower right", fontsize=8.5, framealpha=.95)
ax.text(.015, .975, f"Área coberta: {fmt_br(area_km2)} km² ({n_mun} municípios — 100% do PR)",
        transform=ax.transAxes, fontsize=9, va="top", bbox=dict(fc="white", ec="#999", boxstyle="round,pad=.4"))

ax.annotate("N", xy=(.95, .93), xytext=(.95, .83), xycoords="axes fraction", ha="center", fontsize=13,
            fontweight="bold", arrowprops=dict(arrowstyle="-|>", color="black", lw=2))
x0, y0 = minx - .1, miny - .15
km_per_deg = 111.32 * np.cos(np.radians((miny + maxy) / 2))
ax.plot([x0, x0 + 100 / km_per_deg], [y0, y0], c="black", lw=3, zorder=9)
ax.text(x0 + 50 / km_per_deg, y0 + .06, "100 km", ha="center", fontsize=8, zorder=9)

fig.text(.5, .012, "Fontes: IBGE (malha municipal, PAM), NASA POWER (clima), INMET (estações), SoilGrids (solo), "
         "MapBiomas (uso do solo), NASADEM (relevo), FTW/Field Boundaries (talhão).",
         ha="center", fontsize=8, color="#444")
fig.tight_layout(rect=(0, .03, 1, 1))
fig.savefig(OUT, dpi=200)
print("salvo", OUT)
