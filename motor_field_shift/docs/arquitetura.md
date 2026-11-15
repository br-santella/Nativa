# Field Shift — Data and app architecture

How the data and the app are structured: what is pre-computed, what is read on demand, and how the modules fit together. Date: 2026-11-14. Pilot: soybean → off-season corn in Western Paraná.

## 1. Principle

Pre-compute only what is expensive to compute. Anything that is just reading a piece of a map is read on demand.

## 2. Strategy per dataset

| Dataset | Strategy | Why |
|---|---|---|
| Climate (NASA POWER indicators) | Pre-computed, in a table per grid cell (~0.5° × 0.625°) and per municipality | Each indicator processes 34 seasons of daily data (1991–2024): live it would take seconds; pre-computed it is a millisecond lookup. All of Brazil is ~3–4 thousand cells and a few tens of MB |
| MapBiomas | On demand, by windowed COG reads | Reads only the polygon's bounding box (~1 s). Currently via source.coop (the official bucket returns 403); in a production app, mirror it in our own bucket |
| NASADEM (elevation/slope) | On demand, via COG; slope computed on the clip | Windowed reads are cheap and the slope calculation only runs on the clip |
| SoilGrids | Local rasters for Paraná (`data/raw/soilgrids_pr/`); the REST API only as a fallback for pixels without value (e.g. urban areas, ~15 s) | The REST API is too slow for every request |
| SMAP (current moisture) | Read at request time in `/v1/contexto` (only the field pixel, range requests), cached 24 h per pixel; informational only | The data changes once a day; a daily job per region would be the production version |
| NDVI / HLS (detected rotation, bare soil) | Pre-computed only for demo field 72638 (`ingest/field_timelapse.py`); in production, an asynchronous task (1–3 min) + cache per field | Too slow for a request; the cache avoids repeating it |
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
  core/service.py   API service layer: options, diagnose, recommend, warm_up
  app/engine.py     rotation catalog, hard rules, criteria, ranking and card texts
  app/field_state.py  farmer-reported area problems and soil fertility
  app/mvp.py        Streamlit teaching version
  climate/          precomputed NASA POWER indicators (lookup), INMET, POWER x station validation
  water/            daily FAO-56 water balance per 2nd-crop candidate
  soil/             SoilGrids per polygon + farmer soil analysis (AWC by Saxton & Rawls)
  region/           MapBiomas/relief clip per polygon; soybean-free period (ADAPAR)
  pam/              IBGE PAM municipal yield (expected yield = trend)
  income/           margins (PAM x SEAB/DERAL price - CONAB cost), price history, data/ref updater
  context/          informative current context: ENSO, MJO, SMAP, pests, INMET alerts
  fields/           demo fields: NDVI and relief
  zarc.py           ZARC (MAPA) checks per crop and sowing date
  crop_calendar.py  summer-crop stage -> harvest -> 2nd-window sowing
  i18n/             response translation pt-BR -> en (catalog en.json, applied by the API middleware)
  validation/       offline validation (backtest, sensitivity, satellite, ZARC agreement)
api/field_shift_api/  FastAPI app (main.py: language middleware and error handlers; routes.py; schemas.py)
```

All code (identifiers, comments, logs) is in English; the public API contract (JSON keys such as `rotacao_atual`, ids/slugs)
and the user-facing texts stay in Portuguese, with English answers produced by `i18n` (see `api/README.md`, "Response language").

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

- **Hackathon (delivered 15/11/2026):** FastAPI in Docker on an Azure VM (data synced from a private Hugging Face dataset) + React frontend on Vercel, reading local files (parquet/GeoTIFF), with modules behind the interfaces above, so that swapping local files for a bucket/database later does not touch the engine. The Streamlit app (`app/mvp.py`) remains as a teaching version.
- **Production app:** FastAPI + PostGIS (or parquet/DuckDB) + COG bucket + a queue for NDVI. To expand to another region: run the climate pipeline on that grid and add the state's legal rules; MapBiomas and NASADEM already cover Brazil.
- **Out of scope for now:** livestock/cattle and FTW expansion.
- **Pitch argument:** it scales to Brazil because the heavy work is pre-computed and the rest is on-demand reads.

Engine logic: see docs/motor.md

User inputs: see docs/entradas.md
