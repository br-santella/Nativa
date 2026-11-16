# Contracts

Interfaces between the backend (engine), the catalog and the frontend. A pull request that changes one of
these interfaces updates this file.

The backend is the engine API in `motor_field_shift/`. The complete reference (every field, rule and
example) is [motor_field_shift/api/README.md](../motor_field_shift/api/README.md) and the Swagger UI at
`http://localhost:8000/docs`.

> Field names, routes and error codes are in Portuguese, as defined in the engine code.

## C1 — Engine local data

The engine reads local files in `motor_field_shift/data/`. `/v1/contexto` and the SoilGrids fallback query
external sources at request time.

- `data/raw/` and `data/processed/` (~2.1 GB) are not in git. The list of files, their sizes and the
  script that generates each one is in the "Dados necessários" section of the API README.
- `data/ref/precos_custos.json` and `data/contexto/pragas_alertas.json` are versioned.
- The only live fallback is SoilGrids 2.0 (REST), for areas inside Paraná where the local rasters have no value.
  Climate comes only from the pre-computed table; areas outside Paraná are rejected (422) before any fallback runs.

## C2 — Catalog

- `catalog/crops.yaml`: one block per crop. Every number is a range (`min`/`max`) with a unit and a
  `fonte` (source).
- `catalog/vocabulario.yaml`: closed lists for the catalog, the farm form and the frontend (machinery,
  irrigation, labor, soil textures).

The engine's crop list and parameters (FAO-56 Kc and stages, costs, risks) stay internal, exposed by `/v1/opcoes`; the valid
ids for the API are the ones returned there. `crops.yaml` is read by `field_shift.crop_sheets` for two informative uses that never
change the score: the farmer's pH (`analise_solo.ph`) is compared with each crop's pH range on the card, and the sheets are served by
`GET /v1/culturas/fichas` (each crop in `/v1/opcoes` carries its `ficha` id, or `null`). The Docker image has no `catalog/`, so it
uses the identical copy `motor_field_shift/data/ref/crops.yaml` (a test keeps them equal). From `vocabulario.yaml` the engine reads
only the `problemas_area` list (with a built-in copy when `catalog/` is absent); `scripts/i18n_extract.py` also extracts its texts
for the English catalog.

## C3 — API

Base URL: `http://localhost:8000`. CORS open to all origins. No authentication. All routes are stateless:
the client sends all the data with every request.

| Method | Route | Description |
| --- | --- | --- |
| GET | `/health` | Service status and whether the data loaded (`ok` / `degradado`) |
| GET | `/v1/opcoes` | Summer and second-window crops, valid combinations, sowing dates, criteria, default weights, income references, demo fields |
| GET | `/v1/talhoes/demo` | Demo fields |
| GET | `/v1/culturas/fichas` | Crop sheets of `catalog/crops.yaml` with sources, and the engine crop -> sheet map |
| POST | `/v1/diagnostico` | Terrain, soil, MapBiomas history, detected rotation, climate and risks, yields |
| POST | `/v1/recomendacao` | Ranking, current rotation, alternatives, eliminated rotations, cards |
| GET | `/v1/clima` | Climate block only, for a point |
| GET | `/v1/clima/mensal` | Monthly mean temperature (°C) and rainfall total (mm) of one year at a point (`lat`, `lon`, `ano`), from NASA POWER |
| GET, POST | `/v1/contexto` | Current conditions (ENSO, SMAP, MJO, pests). Informational: does not change the score |

### Area (shared by `/diagnostico`, `/recomendacao` and `POST /contexto`)

Exactly one form: `{"talhao_id": "72638"}`, `{"lat": -24.95, "lon": -53.45}` or
`{"geometry": <GeoJSON Polygon/MultiPolygon/Feature>}` (EPSG:4326, max. 5000 ha). A point becomes a
1000 m × 1000 m square (~100 ha).

### `POST /v1/recomendacao`

Minimal request:

```json
{ "area": {"talhao_id": "72638"}, "rotacao_atual": "soja__milho_safrinha" }
```

Optional fields: `semeadura_safrinha` (second-window sowing date), `pesos {renda, solo, agua, pragas, risco}`
(weights, 0 to 10), `rotacoes[]`, `ajustes` (prices, costs, yields), `analise_solo` (soil analysis),
`restricoes` (restrictions), `irrigacao`, `n_alternativas`, `incluir_diagnostico`.

A **rotation** is a pair (summer crop, second-window crop) with id `"<verao>__<segunda>"`.

Response: `ranking[]` and `alternativas[]` with `nota` (score, 0 to 1), `criterios{}`,
`margem{total_r_ha, incremental_r_ha}` and `card{por_que, evidencias, beneficios, lacunas, riscos, avisos}`;
`atual` (current rotation); `eliminadas[]` with `motivos[]`; `avisos[]`; `metodologia`.

### Errors

| Status | Body | When |
| --- | --- | --- |
| 422 | `{"erro": "fora_da_regiao"}` | Area outside Paraná |
| 422 | validation error | Malformed body |
| 400 | `{"erro": "entrada_invalida"}` | Restrictions eliminated every rotation, invalid adjustment, etc. |
| 504 | `{"erro": "timeout_externo"}` | Raised on `ExternalQueryError`. Failures of the NASA POWER and SoilGrids clients are handled inside those clients and do not raise it |
| 500 | `{"erro": "interno"}` | Unexpected error |

Every engine error includes `mensagem` (human-readable text).

### Example responses

Real responses are in [motor_field_shift/api/exemplos/](../motor_field_shift/api/exemplos/).
