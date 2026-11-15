"""Export a light Paraná boundary and the municipality list for the frontend coverage check.

Writes frontend/src/parana.json:
  boundary: rings of [lon, lat] (simplified, buffered ~1 km outward so border farms are not
            rejected by the simplification; the engine still does the exact check and answers 422)
  municipalities: [name, lat, lon] with a point guaranteed inside each municipality

Run: uv run python scripts/export_parana_frontend.py
"""
from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
from shapely.geometry import MultiPolygon

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data/raw/regiao/pr.geojson"
MUNICIPALITIES = ROOT / "data/raw/regiao/municipios_pr.geojson"
OUT = ROOT.parent / "frontend/src/parana.json"

BUFFER_DEG = 0.01  # ~1 km
SIMPLIFY_DEG = 0.005


def main() -> None:
    state = gpd.read_file(STATE).to_crs(4326).geometry.iloc[0]
    light = state.buffer(BUFFER_DEG).simplify(SIMPLIFY_DEG)
    polygons = light.geoms if isinstance(light, MultiPolygon) else [light]
    boundary = [[[round(x, 4), round(y, 4)] for x, y in p.exterior.coords] for p in polygons]

    mun = gpd.read_file(MUNICIPALITIES).to_crs(4326).sort_values("nome")
    municipalities = []
    for name, geom in zip(mun["nome"], mun.geometry):
        pt = geom.representative_point()
        municipalities.append([name, round(pt.y, 4), round(pt.x, 4)])

    OUT.write_text(json.dumps({"boundary": boundary, "municipalities": municipalities},
                              ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"{OUT}: {sum(len(r) for r in boundary)} vertices, {len(municipalities)} municipalities, "
          f"{OUT.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
