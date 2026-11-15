# Field Shift — Data and app architecture

How the data and the app are structured: what is pre-computed, what is read on demand, and how the modules fit together. Date: 2026-11-14. Pilot: soybean → off-season corn in Western Paraná.

## 1. Principle

Pre-compute only what is expensive to compute. Anything that is just reading a piece of a map is read on demand.

## 2. Strategy per dataset

| Dataset | Strategy | Why |
|---|---|---|
| Climate (NASA POWER indicators) | Pre-computed, in a table per grid cell (~0.5° × 0.625°) and per municipality | Each indicator processes 35 years of daily data (1991–2025): live it would take seconds; pre-computed it is a millisecond lookup. All of Brazil is ~3–4 thousand cells and a few tens of MB |
| MapBiomas | On demand, by windowed COG reads | Reads only the polygon's bounding box (~1 s). Currently via source.coop (the official bucket returns 403); in a production app, mirror it in our own bucket |
| NASADEM (elevation/slope) | On demand, via COG; slope computed on the clip | Windowed reads are cheap and the slope calculation only runs on the clip |
| SoilGrids | On demand, via the API | Light external query, no need to store it |
| SMAP (current moisture) | Daily job per region; the app only reads the latest | The data changes once a day and is the same for every user in the region |
| NDVI / HLS (detected rotation, bare soil) | Asynchronous task (1–3 min) + cache per field | Too slow for a request; the cache avoids repeating it |
| Legal rules / ZARC | Local table | Small, static data |
| FTW (field boundaries) | Outside the flow for now: the polygon comes from the client (drawn on the map / CAR) | FTW is only used for the demo tile (field 72638) |

**Note:** for the hackathon, MapBiomas and NASADEM were downloaded clipped to the whole of Paraná, so the pitch works offline. In a production app they become on-demand reads.

## 3. Flow

```
[Offline pipeline / jobs]                  [Storage]                  [App]
 POWER 35 years → climate indicators ──►  indicators table     ─┐
 Daily SMAP → current moisture       ──►  moisture table        │
                                                                ├─► API  ──► Front (map)
 MapBiomas / NASADEM (COG)           ──►  COG bucket  ──────────┤   "given the polygon,
 SoilGrids (external API)            ──────────────────────────┤    return diagnosis
 HLS NDVI (async task)               ──►  cache per field ──────┘    and ranking"
                                          Legal rules / ZARC (local table)
```

Core: `diagnostico(poligono) → {clima, solo, relevo, historico, rotacao_detectada}` and then `ranking(diagnostico, pesos)`. Each source is a module with the same interface: it receives the polygon (or lat/lon) and returns a dict.

## 4. Modules

```
src/field_shift/
  clima/     indicadores_para(lat, lon)        (in progress)
  regiao/    historico_mapbiomas(), relevo()   (in progress)
  solo/      soilgrids(poligono)               (to do)
  ndvi/      rotacao_detectada(poligono)       (currently in talhoes/ndvi.py)
  regras/    hard rules + ZARC                 (currently inside engine.py)
  motor/     diagnostico() + ranking()         (split out of the current app/engine.py)
  app/       Streamlit (hackathon) → FastAPI + web frontend
```

## 5. Disk space (Western Paraná)

Estimate for the Oeste pilot; update with the real numbers after the downloads. The engine now reads the whole-of-Paraná versions (`*_pr`, ~2 GB in `data/`, the largest being `slope_pct.tif` at 1.1 GB; see `api/README.md`).

| Dataset | Estimated size |
|---|---|
| POWER | ~150–250 MB of raw JSON → ~20–40 MB as parquet |
| INMET | ~300–500 MB of CSV (1–2 GB zips deleted after extraction) → daily parquet of a few MB |
| MapBiomas 2000–2024 | ~150–250 MB |
| NASADEM + slope | ~150–250 MB |
| **Total** | **~0.7–1.2 GB, peaking at 2–3 GB during download** |

Production only needs the climate indicators table (a few MB) plus the clipped rasters (~300–500 MB), or none of that if the COGs are read on demand. The whole of Paraná ≈ 9× that.

## 6. Hackathon vs. production app

- **Until Sunday (15/11/2026):** Streamlit + local files (parquet/GeoTIFF), no infrastructure, but with modules behind the interfaces above, so that swapping local files for a bucket/database later does not touch the engine.
- **Production app:** FastAPI + PostGIS (or parquet/DuckDB) + COG bucket + a queue for NDVI. To expand to another region: run the climate pipeline on that grid and add the state's legal rules; MapBiomas and NASADEM already cover Brazil.
- **Out of scope for now:** livestock/cattle and FTW expansion.
- **Pitch argument:** it scales to Brazil because the heavy work is pre-computed and the rest is on-demand reads.

Engine logic: see docs/motor.md

User inputs: see docs/entradas.md
