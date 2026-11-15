"""Gera docs/figuras/mapa_cobertura_api_pr.png: onde a API do Field Shift funciona no Paraná."""
from pathlib import Path

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/figuras/mapa_cobertura_api_pr.png"
TALHAO_ID = "72638"

pr = gpd.read_file(ROOT / "data/raw/ibge/malha_pr_municipios.geojson").to_crs(4326)
oeste = gpd.read_file(ROOT / "data/raw/regiao/oeste_pr.geojson").to_crs(4326)
mun = gpd.read_file(ROOT / "data/raw/regiao/municipios_oeste_pr.geojson").to_crs(4326)
clima = pd.read_parquet(ROOT / "data/processed/clima/indicadores.parquet")
est = pd.read_csv(ROOT / "data/processed/clima/inmet_estacoes.csv")
tal = gpd.read_parquet(ROOT / "data/processed/ftw/fields_tile_mapbiomas_geo.parquet")
tal = tal[tal["id"].astype(str) == TALHAO_ID]
tcent = tal.to_crs(31982).centroid.to_crs(4326).iloc[0]

# areas in a metric projection
a_pr = pr.to_crs(5880).union_all().area / 1e6
a_oe = oeste.to_crs(5880).union_all().area / 1e6
print(f"PR {a_pr:,.0f} km2 | Oeste {a_oe:,.0f} km2 | {100*a_oe/a_pr:.1f}%")

COR_OESTE, COR_FORA = "#1b7f5c", "#e4e4e0"
fig, ax = plt.subplots(figsize=(11, 8.2))
pr.plot(ax=ax, facecolor=COR_FORA, edgecolor="#b5b5b0", linewidth=0.3)
mun.plot(ax=ax, facecolor=COR_OESTE, alpha=0.55, edgecolor="white", linewidth=0.5)
oeste.boundary.plot(ax=ax, color="#0b4a35", linewidth=1.8)
gpd.GeoSeries([pr.union_all()], crs=4326).boundary.plot(ax=ax, color="#333", linewidth=1.1)

# NASA POWER cell grid (0.5° x 0.625°)
cel = clima[clima["tipo"] == "celula"][["lat", "lon"]].drop_duplicates()
for la, lo in zip(cel.lat, cel.lon):
    ax.add_patch(Rectangle((lo - .3125, la - .25), .625, .5, fill=False, ec="#2b6cb0", lw=0.5, ls="--", alpha=.7, zorder=3))

ax.scatter(est.lon, est.lat, marker="^", s=55, c="#d97706", ec="black", lw=.6, zorder=6)
ax.scatter([tcent.x], [tcent.y], marker="*", s=330, c="#e11d48", ec="black", lw=.8, zorder=7)
ax.annotate("Demo field 72638", (tcent.x, tcent.y), xytext=(55, -45), textcoords="offset points",
            fontsize=8.5, fontweight="bold", color="#e11d48",
            arrowprops=dict(arrowstyle="-", color="#e11d48", lw=.8),
            bbox=dict(boxstyle="round,pad=.2", fc="white", ec="#e11d48", lw=.6), zorder=8)

# hub municipalities
polos = ["Cascavel", "Toledo", "Foz do Iguaçu", "Marechal Cândido Rondon", "Medianeira", "Palotina", "Assis Chateaubriand"]
mp = mun.to_crs(5880)
for n in polos:
    r = mun[mun["nome"].str.lower() == n.lower()]
    if r.empty:
        print("no hub:", n); continue
    p = mp[mp["nome"].str.lower() == n.lower()].geometry.iloc[0].representative_point()
    p = gpd.GeoSeries([p], crs=5880).to_crs(4326).iloc[0]
    ax.plot(p.x, p.y, "o", ms=3, c="black", zorder=5)
    off = (-4, 5) if n == "Assis Chateaubriand" else (4, 3)
    ax.annotate(n, (p.x, p.y), xytext=off, ha="right" if n == "Assis Chateaubriand" else "left", textcoords="offset points", fontsize=7.5, zorder=9,
                path_effects=[__import__("matplotlib.patheffects", fromlist=["x"]).withStroke(linewidth=2.2, foreground="white")])

ax.set_xlim(-54.9, -48.0); ax.set_ylim(-26.85, -22.4)
ax.set_aspect(1 / 0.92)
ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude")
ax.grid(ls=":", lw=.3, alpha=.5)
ax.set_title("Field Shift — API coverage in Paraná", fontsize=16, fontweight="bold", pad=12)

hand = [
    Patch(fc=COR_OESTE, alpha=.55, ec="#0b4a35", lw=1.5, label="Covered by the API — 50 municipalities"),
    Patch(fc=COR_FORA, ec="#b5b5b0", label="Outside the region (422 fora_da_regiao)"),
    Line2D([], [], color="#2b6cb0", ls="--", lw=1, label="NASA POWER climate cells (0.5° x 0.625°)"),
    Line2D([], [], marker="^", ls="", mfc="#d97706", mec="black", ms=8, label="INMET stations (validation)"),
    Line2D([], [], marker="*", ls="", mfc="#e11d48", mec="black", ms=14, label="Demo field 72638"),
]
ax.legend(handles=hand, loc="lower right", fontsize=8.5, framealpha=.95)
ax.text(.015, .965, f"Covered area: {a_oe:,.0f} km² ({100*a_oe/a_pr:.1f}% of Paraná)",
        transform=ax.transAxes, fontsize=9, va="top", bbox=dict(fc="white", ec="#999", boxstyle="round,pad=.4"))

# north arrow
ax.annotate("N", xy=(.95, .93), xytext=(.95, .83), xycoords="axes fraction", ha="center", fontsize=13,
            fontweight="bold", arrowprops=dict(arrowstyle="-|>", color="black", lw=2))
# escala (~100 km a -25°: 1° lon ≈ 100.9 km)
x0, y0 = -54.6, -26.6
ax.plot([x0, x0 + 100 / 100.9], [y0, y0], c="black", lw=3, zorder=9)
ax.text(x0 + 50 / 100.9, y0 + .05, "100 km", ha="center", fontsize=8, zorder=9)

fig.text(.5, .01, "Sources: IBGE (municipal boundaries), NASA POWER (climate, 0.5°x0.625° cells), INMET (automatic stations), "
         "FTW/Field Boundaries (field).", ha="center", fontsize=8, color="#444")
fig.tight_layout(rect=(0, .03, 1, 1))
fig.savefig(OUT, dpi=200)
print("salvo", OUT)
