# Team contracts

Contracts let the workstreams work in parallel. **If you change a contract, tell the team and update this
file in the same pull request.** Until real data exists, use the examples in the same shape.

The MVP backend is the engine API in `motor_field_shift/`. The full reference (every field, rule and
example) is in [motor_field_shift/api/README.md](../motor_field_shift/api/README.md) and in Swagger at
`http://localhost:8000/docs`. This file summarizes what each part can rely on.

> Field names, routes and error codes are in Portuguese because they come from the engine's code.

## C1 — Engine local data (data → engine and API)

The engine only reads local files in `motor_field_shift/data/`. The exceptions are `/v1/contexto` and the
fallbacks, which query external sources at request time and write a cache.

- `data/raw/` and `data/processed/` (~280 MB) are **not in git**. The list of files, their sizes and the
  script that generates each one is in the "Dados necessários" section of the API README.
- `data/ref/precos_custos.json` and `data/contexto/pragas_alertas.json` are versioned.
- The live fallbacks (NASA POWER and SoilGrids 2.0) only run **inside** Western Paraná, when a local file
  does not cover the area. Areas outside the region are rejected before any fallback runs.

## C2 — Catalog (curation → engine, API and frontend)

- `catalog/crops.yaml`: one block per crop. **Every number is a range (`min`/`max`) with a unit and a
  `fonte` (source).**
- `catalog/vocabulario.yaml`: closed lists shared by the catalog, the farm form and the frontend
  (machinery, irrigation, labor, soil textures).

Pending: the engine still uses its own catalog (`/v1/opcoes`) and does not read `catalog/`. Until they are
unified, **the valid ids for the API are the ones in `/v1/opcoes`**.

## C3 — API (backend → frontend)

Base URL: `http://localhost:8000`. CORS is open. No authentication. All routes are stateless: the frontend
keeps the farm data (in localStorage) and sends it with every request.

| Method | Route | Used by the frontend for |
| --- | --- | --- |
| GET | `/health` | Checking that the API is up and the data loaded (`ok` / `degradado`) |
| GET | `/v1/opcoes` | Building the selectors: summer and second-window crops, valid combinations, sowing dates, criteria, default weights, income references, demo fields |
| GET | `/v1/talhoes/demo` | List of demo fields |
| POST | `/v1/diagnostico` | Farm, history and climate screens: terrain, soil, MapBiomas history, detected rotation, climate and risks, yields |
| POST | `/v1/recomendacao` | Rotation screen: ranking, current rotation, alternatives, eliminated rotations, cards |
| GET | `/v1/clima` | Climate block only, for a point |
| GET, POST | `/v1/contexto` | Current conditions (ENSO, SMAP, MJO, pests). Informational only: does not change the score |

### Area (shared by `/diagnostico` and `/recomendacao`)

Exactly one form: `{"talhao_id": "72638"}`, `{"lat": -24.95, "lon": -53.45}` or
`{"geometry": <GeoJSON Polygon/MultiPolygon/Feature>}` (EPSG:4326, max. 5000 ha).

### `POST /v1/recomendacao`: the essentials

Minimal request:

```json
{ "area": {"talhao_id": "72638"}, "rotacao_atual": "soja__milho_safrinha" }
```

Optional: `semeadura_safrinha` (second-window sowing date), `pesos {renda, solo, agua, pragas, risco}`
(weights, 0 to 10), `rotacoes[]`, `ajustes` (prices, costs, yields), `analise_solo` (soil analysis),
`restricoes` (restrictions), `irrigacao`, `n_alternativas`, `incluir_diagnostico`.

A **rotation** is a pair (summer crop, second-window crop) with id `"<verao>__<segunda>"`.

Response: `ranking[]` and `alternativas[]` with `nota` (score, 0 to 1), `criterios{}`,
`margem{total_r_ha, incremental_r_ha}` and `card{por_que, evidencias, beneficios, lacunas, riscos, avisos}`;
`atual` (current rotation); `eliminadas[]` with `motivos[]`; `avisos[]`; `metodologia`.

### Errors

| Status | Body | When |
| --- | --- | --- |
| 422 | `{"erro": "fora_da_regiao"}` | Area outside Western Paraná |
| 422 | validation error | Malformed body |
| 400 | `{"erro": "entrada_invalida"}` | Restrictions eliminated every rotation, invalid adjustment, etc. |
| 504 | `{"erro": "timeout_externo"}` | Reserved for an external source timing out. **Not returned yet:** today these failures come back as 500 |
| 500 | `{"erro": "interno"}` | Unexpected error |

Every engine error also carries `mensagem` (human-readable text).

### Examples for working without data

Real responses are in [motor_field_shift/api/exemplos/](../motor_field_shift/api/exemplos/). Use them as
frontend mocks while the local data is not available.

## Open contract items

- **Confidence traffic light** (🔴 refer to a professional, 🟡 indicative, 🟢 well supported): not in the
  response yet. Proposal: a `confianca{nivel, motivos[]}` field on every ranking item and on `atual`.
- **Region:** decide whether the demo stays in Western Paraná or the region lock is removed. Removing it
  means changing the area check in `servico.py`, the early return in `engine.enriquecer()`, and wiring the
  unused `clima/lookup.py:fallback_power()`.
- **Catalog:** unify `catalog/crops.yaml` and the engine's internal catalog.
