# Field Shift — User inputs

What the user provides, what the app fills in by itself, and what is worth providing if the user has the data. Date: 2026-11-14. Audience: product, frontend and API. API fields checked against `api/README.md` and `api/field_shift_api/schemas.py`.

## Principle

The farmer types almost nothing. The app pulls the public data and the farmer only confirms or adjusts it. Every input has a pre-filled reference value, with source and period, and the user can replace it with their own ("Use my values"). The more of their own data, the more accurate the result.

## 1. Required input: the area

Only `area` is required. Three forms (exactly one):

| Form | Field | Note |
|---|---|---|
| Polygon drawn on the map (recommended) | `area.geometry` | GeoJSON Polygon, MultiPolygon or Feature, EPSG:4326 (lon, lat) |
| Lat/lon point | `area.lat` + `area.lon` | Becomes a ~100 ha square, with a warning |
| Demo field ID | `area.talhao_id` | E.g. `"72638"` (see `GET /v1/talhoes/demo`) |

Constraints: inside Western Paraná (50 municipalities, IBGE 4106) and at most 5000 ha.

## 2. Choice inputs (they have defaults; the user clicks, does not type)

| Input | API field | Default | Effect on the result |
|---|---|---|---|
| Off-season sowing date (15/01, 01/02, 15/02, 01/03, 15/03) | `semeadura_safrinha` | 01/02 | Changes the frost risk (from 6% to 76% on field 72638) and the water at flowering |
| Priorities (income, soil, water, pests, risk; 0 to 10) | `pesos` | income 5, others 3 | Weight the 5 criteria in the final score |
| Current rotation | `rotacao_atual` | Detected by NDVI when available (currently only on field 72638); otherwise off-season corn, with a warning | Comparison baseline. Options: the catalog slugs (`GET /v1/opcoes`) |
| Number of alternatives | `n_alternativas` | 3 (the NATIVA screen uses 2) | How many alternatives are returned (1 to 6) |

Mapping of the NATIVA screen sliders (0–100%) to `pesos` (0–10):

| Slider (NATIVA) | Field |
|---|---|
| Profitability | `renda` |
| Soil health | `solo` |
| Climate resilience | `risco` |
| Water savings | `agua` (**PENDING**: our criterion measures whether water meets the demand at flowering, not water savings; align the meaning) |
| (no slider) | `pragas` stays at the default |

## 3. Filled in automatically (the user only sees and confirms)

| Data | Source | Period / resolution | Where it appears |
|---|---|---|---|
| Climate and risks (frost, dry spell, heat, water balance) | NASA POWER, validated against INMET | 1991–2024, ~50 km cell | `diagnostico.clima` |
| Soil (clay, sand, organic C, pH, available water capacity) | SoilGrids | 250 m | `diagnostico.solo` |
| Terrain (elevation, slope, Embrapa class) | NASADEM | 30 m | `diagnostico.relevo` |
| Crop history | MapBiomas | 2019–2024 | `diagnostico.historico` |
| Municipality and average yield | IBGE PAM | Last 5 years | `diagnostico.area.municipio`, `diagnostico.produtividade` |
| Price | SEAB/DERAL-PR | 12-month average | `ranking[].margem.itens[].preco` |
| Cost | CONAB COE (Londrina/Ponta Grossa) | Latest season | `ranking[].margem.itens[].custo` |
| Legal rules (soybean-free period, soybean after soybean) | ADAPAR (free period 02/06–31/08) and Ordinance SDA/MAPA 1.124/2024 | In force (check before the pitch) | `eliminadas[]`, `avisos` |

## 4. If the user has the data, it is worth providing

Ordered by impact.

| Own data | Replaces | Why it helps | API field | Status |
|---|---|---|---|---|
| Production cost per crop (BRL/ha) | CONAB for Londrina | It is what varies most between farms | `ajustes.custos` (`soja`, `milho`/`milho_2safra`, `trigo`, `aveia`, `milheto_crotalaria`, `braquiaria_consorcio`, `pousio`) | Accepted |
| Locked-in or expected price (contract, barter, cooperative quote), BRL/bag | DERAL 12-month average | Reflects what the farmer will actually receive | `ajustes.precos` (`soja`, `milho`, `trigo`) | Accepted |
| Cost line | `coe` (default) | Chooses what goes into the cost | `ajustes.linha_custo` (`coe`, `cot`, `ct`) | Accepted |
| Own yield (bags/ha per crop) | Municipal average (e.g. 70 bags/ha vs. 49 from IBGE) | The municipal average hides the farm | `ajustes.produtividade` (`soja`, `milho`/`milho_2safra`, `trigo`; bags/ha > 0). The bad year scales proportionally; the soybean value also changes the income scale S | Accepted |
| Current rotation and real history of recent years | MapBiomas (only sees the summer crop) and NDVI (only exists for the demo) | Accurate current rotation and history | `rotacao_atual` (accepted); detailed history to be implemented | Partial |
| Sowing date the farmer actually uses | Default 01/02 | Correct frost risk and water | `semeadura_safrinha` | Accepted |
| Soil analysis (clay, organic matter, pH, available water capacity) | SoilGrids and pedotransfer | Available water capacity is the largest uncertainty in the water criterion | `analise_solo` (top level): `argila_pct`, `areia_pct`, `materia_organica_pct` or `carbono_organico_g_kg`, `ph`, `cad_mm_cm` (optional), `profundidade_cm` (optional, default 20). Requires clay+sand or `cad_mm_cm`. Also valid in `POST /v1/diagnostico` | Accepted |
| Exact field polygon | Point (~100 ha square) | Climate, soil and terrain of the right field | `area.geometry` | Accepted |
| Restrictions: crops the farmer does not want or cannot plant/sell; machinery (corn header, intercrop seeder); local buyer | All candidates allowed | Only what the farmer can execute appears | `restricoes` (top level): `culturas_excluidas` (ids `<verao>__<segunda>` or legacy slugs = soybean in summer), `maquinas{plataforma_milho, semeadora_consorcio}`, `sem_comprador` (`milho`, `trigo`, `sorgo`, `feijao`, `aveia_grao`). To evaluate only some rotations, use `rotacoes` (list of `{verao, segunda}`; see `docs/motor.md`). Excluded or no buyer eliminates; machine `false` only adds a warning and an outsourcing cost. Market viability (high/medium/low/not applicable) appears in `card.mercado` | Accepted |
| Irrigation | Engine assumes rainfed | Changes the water criterion | `irrigacao` (top level): `disponivel`, `custo_r_mm_ha` (default 4.0), `lamina_max_mm_dia` (default 6). Irrigates corn, corn+brachiaria and wheat; dry spells stop counting; the margin subtracts depth × cost. Does not model a yield gain | Accepted |

## 5. How to show it on screen (suggestion for the frontend)

A "Values used" block with yield, price and cost per crop, with source and period on each. The "Use my values" button makes the fields editable, pre-filled with the reference, and recalculates the ranking.

```
Profitability — values used                            [ Use my values ✎ ]
              Yield               Price               Cost
Soybean       49 bags/ha (IBGE)   BRL 120/bag (DERAL) BRL 4,824/ha (CONAB)
Corn 2nd      103 bags/ha (IBGE)  BRL 54/bag (DERAL)  BRL 4,678/ha (CONAB)
ⓘ Public references. Replace them with your farm's values for a more accurate result.
```

## 6. Request examples (`POST /v1/recomendacao`)

Minimal (area only):

```json
{ "area": { "talhao_id": "72638" } }
```

Complete (valid in the current schema):

```json
{
  "area": {
    "geometry": {
      "type": "Polygon",
      "coordinates": [[[-53.3045, -24.9045], [-53.2955, -24.9045], [-53.2955, -24.8955], [-53.3045, -24.8955], [-53.3045, -24.9045]]]
    }
  },
  "semeadura_safrinha": "15/02",
  "pesos": { "renda": 8, "solo": 3, "agua": 3, "pragas": 5, "risco": 4 },
  "rotacao_atual": "milho_safrinha",
  "ajustes": {
    "precos": { "soja": 125.0, "milho": 58.0, "trigo": 82.0 },
    "custos": { "soja": 4500.0, "milho_2safra": 4300.0 },
    "linha_custo": "cot"
  },
  "n_alternativas": 3
}
```

## 7. Pending

- Define the meaning of "Water savings" (NATIVA slider vs. the engine's water criterion).
- Validate with an agronomist/cooperatives the estimates of the new inputs: outsourcing cost (BRL 250/ha corn harvest, BRL 80/ha intercrop sowing), irrigation cost (BRL 4/mm/ha), maximum depth (6 mm/day) and market levels per crop.
- Model the yield gain from irrigation (currently only the water criterion, the risk and the cost change).
- Evolution: futures prices (B3) and p10–p90 sensitivity.
