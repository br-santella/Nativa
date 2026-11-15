# Field Shift — Rotation engine logic

How the engine computes and ranks the rotation options. Date: 2026-11-15. Pilot: rotations (summer + second window) in Western Paraná; the worked example is field 72638. Code in `src/field_shift/app/engine.py` (catalog, rules, scoring), supported by `clima/`, `agua/`, `solo/` and `renda/`.

Units: 1 bag (sc) = 60 kg. Monetary values are in BRL.

## 1. Overview

The engine recommends through **rules + explainable scoring**, not end-to-end ML. There is no "rotation X was good on field Y" label to train a model on, and every score points to data the farmer can check.

The output is always the **current rotation + the best alternatives** (3 by default), each with the why, evidence, benefits, gaps and risks, and how each one improves (or worsens) production against the current rotation (`ganho_vs_atual`).
A rotation is a pair **(summer crop, second-window crop)**, with a stable id `"<verao>__<segunda>"` (e.g. `soja__milho_safrinha`).

The flow is **per stage**: the farmer says the current rotation (required) and where the summer crop is today; the engine estimates the harvest, derives the second-window sowing and answers two questions in two blocks (section 2.1): what goes in **now** (`agora`) and what to change **next season** (`proxima_safra`).

## 2. Flow

```
INPUT                         DIAGNOSIS                     DECISION
polygon / point / demo ID     climate (POWER, 50 km cell)   hard rules
current rotation (required)─► soil (SoilGrids)           ─► (eliminate, with reason)
summer stage / harvest date   terrain (NASADEM)                 │
farmer weights                history (MapBiomas, NDVI)         ▼
prices/costs (optional)       yield (IBGE PAM)              5 criteria, 0–1 scale
                                                                │
estimated harvest ─► sowing of the 2nd window                   ▼
                                                      weighted score ─► ranking ─► cards
                                                      (blocks `agora` and `proxima_safra`, with `ganho_vs_atual`)
```

### 2.1 Per-stage flow: stages, harvest and blocks

1. **Current rotation (`rotacao_atual`, required).** Its summer crop (`soja` or `milho_verao`) is the "current crop". It defines the two blocks.
2. **Stage of the summer crop (`estagio_verao`, optional).** Estimated harvest = `data_referencia` + typical days of the stage. `data_referencia` is "today" for the farmer (ISO date; default: today); sending it makes the calculation deterministic. Typical days to harvest (estimates, scale of Fehr & Caviness / Ritchie, middle of the range, medium cycle, Western Paraná; **to be validated with Embrapa**; code in `src/field_shift/calendario.py`):

| Stage | Soybean | Summer corn |
|---|---|---|
| `vegetativo` | 90 d | 110 d |
| `floracao` (R1–R2) | 65 d | n/a |
| `formacao_vagens` (R3–R4) | 48 d | n/a |
| `enchimento_graos` (R5–R6) | 32 d | n/a |
| `pendoamento` (VT–R1) | n/a | 80 d |
| `grao_leitoso` (R2–R3) | n/a | 60 d |
| `grao_farinaceo` (R4–R5) | n/a | 40 d |
| `maturacao` (R7–R8 soybean; R6 corn) | 10 d | 15 d |
| `colhida` | 0 | 0 |

   A stage of the other crop (e.g. a corn stage when the current crop is soybean) or an unknown one is a validation error (422).
3. **Expected harvest date (`colheita_prevista`, `dd/mm`, optional).** Overrides the stage (next occurrence on or after `data_referencia`; a warning says which one was used if both come).
4. **Sowing of the second window.** Without `semeadura_safrinha`, it is the first date among 15/01, 01/02, 15/02, 01/03 and 15/03 on or after the estimated harvest (+ `DIAS_PREPARO_2A`, today 0 days, no-till). If the farmer sends the date, it wins but cannot be before the harvest (422). If the harvest is after 15/03, it is "too late" (`semeadura_2a` null, warning): the crops that follow the sowing date are eliminated and only wheat, oat, radish and fallow remain. With no stage, no harvest date and no sowing date, the engine falls back to the catalog assumption (soybean harvested ~10/01, summer corn ~05/02) and 01/02, with a warning asking for the stage.
5. **Blocks.** `agora` = combinations with the **same summer crop** as the current rotation (what enters after this harvest). `proxima_safra` = combinations with the **other summer crop**, compared with the current one (decision for the next season). `posicao` restarts at 1 in each block; each block has `ranking`, `alternativas` (best ones without the current rotation, up to `n_alternativas`) and `eliminadas`. At the top level, `ranking`, `alternativas` and `eliminadas` are kept as compatibility aliases (`eliminadas` = union of both blocks). The response also brings `cultura_atual`, `estagio_verao`, `colheita_estimada` (`origem`: `estagio`, `informada` or `premissa`), `semeadura_2a` (`derivada`, `informada` or `premissa`) and `dias_ate_colheita`.
6. **Gain against the current rotation (`ganho_vs_atual`).** On every item except the current rotation (null if the current rotation was eliminated): `soja_seguinte_sc` (+ `_faixa`) and `soja_seguinte_rs` (bonus on the following soybean × DERAL price; catalog estimate), `renda_2a_safra` and `margem_total` (BRL/ha; data), `solo` (bare days and cover; estimate; negative days = better), `agua` and `risco_climatico` (difference of criterion; data). Every number carries its `origem` so that data and estimate are told apart. The current rotation is always evaluated for the comparison, even if it is not in `rotacoes`.

Example (field 72638, soybean in `enchimento_graos`, `data_referencia` 2026-12-01): harvest ~02/01 (32 days), sowing derived as 15/01. `agora` has 10 valid combinations with soybean (best: soybean → off-season corn + brachiaria, score 0.817; the current one, off-season corn, is 2nd) and soybean in the second window eliminated. `proxima_safra` shows only the fixed-date crops after summer corn (see the known limitation in section 10). Real response: `api/exemplos/recomendacao_talhao_72638.json`.

## 3. Inputs

| Input | Default | Effect |
|---|---|---|
| Field | Polygon in Western Paraná, point or demo ID (72638) | Defines the climate cell, soil, terrain and municipality (PAM) |
| Current rotation (`rotacao_atual`) | **Required** | Defines the current summer crop (blocks `agora`/`proxima_safra`) and is the comparison baseline (`atual`, `ganho_vs_atual`) |
| Stage of the summer crop (`estagio_verao`) and/or expected harvest (`colheita_prevista`), reference date (`data_referencia`) | None (catalog assumption, with a warning); `data_referencia` = today | Estimated harvest, from which the sowing of the second window is derived (section 2.1) |
| Sowing date of the second crop ("safrinha") | Derived from the estimated harvest; without stage or harvest, 01/02 (options: 15/01, 01/02, 15/02, 01/03, 15/03) | Changes the frost risk and water for corn, sorghum, beans and millet/crotalaria, and applies in the calendar rules (section 5). If sent, it wins over the derived one but cannot be before the harvest |
| Weights 0–10 | income 5, soil 3, water 3, pests 3, risk 3 | Weight the 5 criteria in the final score |
| Rotations to evaluate (`rotacoes`) | All catalog combinations (22) | List of `{verao, segunda}` (closed enums): the engine evaluates and ranks only those; one eliminated by the rules comes back in `eliminadas`, with the reason. An empty, duplicated or out-of-enum list is a validation error (422) |
| Prices/costs | Reference (SEAB/DERAL and CONAB) | Provided values override the reference in the income calculation |
| Own yield (`ajustes.produtividade`) | Municipal PAM | **Income:** replaces the PAM yield in the margin (soybean, 2nd-season corn, summer corn, wheat, beans, sorghum); the bad year scales by own yield × p20/PAM average; the soybean value changes the scale S |
| Soil analysis (`analise_solo`) | SoilGrids | **Water:** the available water capacity comes from the analysis (`cad_mm_cm` directly, or Saxton & Rawls with the provided sand, clay and organic matter), uniform over 0–60 cm. The diagnosis `solo` block then cites "farmer's soil analysis" |
| Restrictions (`restricoes`) | None | **Hard rules:** excluded rotations (new id, or legacy slug = soybean in summer) and no local buyer (corn, wheat, sorghum, beans; also applies to the summer crop) eliminate the rotation. **Income:** a missing machine (corn header, one per corn harvest; intercrop seeder) does not eliminate; it adds an outsourcing cost (estimates: BRL 250/ha and BRL 80/ha) and a warning on the card. Each candidate shows `mercado_oeste_pr` (high/medium/low/not applicable; estimate to be validated) |
| Irrigation (`irrigacao`) | Rainfed | **Water:** the balance irrigates second-window corn, corn+brachiaria, wheat, sorghum and beans when Dr > p·TAW (p = 0.55; beans 0.45), refilling up to capacity, limited by the maximum daily depth, over the whole cycle; the criterion goes up. **Risk:** dry spells stop counting for those candidates (frost still counts). **Income:** subtracts average depth × cost (BRL/mm/ha). Does not change the expected yield; cover crops and fallow are not irrigated |

## 4. Candidates: summer + second window

Each candidate is a pair (summer crop, second-window crop) in the same agricultural year: 2 × 11 = 22 combinations.

**Summer:** `soja` and `milho_verao`.

| Summer | Estimated harvest (catalog assumption, used when no stage or harvest date is sent) | Bonus on the following soybean | Income |
|---|---|---|---|
| Soybean | ~10/01 (early soybean; the assumption the engine already had) | 0 | PAM soybean × DERAL price − CONAB soybean cost |
| Summer corn | ~05/02 (sowing 15/09–15/10, medium cycle) | +3 bags/ha (breaks the disease and nematode cycle, plus straw) | PAM 1st-season corn (SIDRA 839) × DERAL corn price − CONAB 1st-season corn cost |

**Second window:**

| Crop | Type | Sowing | Climate risk | Sale | Source of yield, price and cost |
|---|---|---|---|---|---|
| Off-season corn | Grain | the chosen date (15/01–15/03) | frost + dry spell | corn | PAM 2nd season; DERAL; CONAB Londrina |
| Off-season corn + brachiaria | Intercrop | the chosen date | frost + dry spell | corn | same + brachiaria (estimate) |
| Wheat | Grain | 01/05 | wheat frost | wheat | PAM; DERAL; CONAB Ponta Grossa |
| Sorghum (new) | Grain | the chosen date, window 15/01–15/03 | frost (drought tolerant) | sorghum | PAM sorghum (SIDRA 1612); estimated price (80% of DERAL corn); estimated cost (CONAB sorghum Rio Verde-GO) |
| Off-season beans (new) | Grain | the chosen date, window 15/01–28/02 | frost + dry spell | beans | PAM 2nd-season beans (SIDRA 1002); DERAL black beans; CONAB 2nd-season beans Francisco Beltrão-PR |
| Oat (cover/straw) | Cover | 01/05 | none | no sale | estimated cost |
| Millet/crotalaria | Cover | the chosen date | none | no sale | estimated cost |
| Forage radish (new) | Cover | 01/04 | none | no sale | estimated cost |
| Oat + radish (new) | Cover (mix) | 01/05 (oat) and 01/04 (radish) | none | no sale | estimated cost |
| Fallow | No crop | n/a | none | no sale | estimated cost |
| Off-season soybean | Grain | the chosen date | dry spell | n/a | blocked by the rules (always eliminated) |

Only grain crops and cover crops that use grain machinery, the same sales channel and fit the calendar are included. Sunflower, canola and dual-purpose wheat are left out.
Off-season corn, corn + brachiaria and summer corn require a corn header (outsourcing cost per harvest if the farmer does not have one).

Catalog values for the new crops (all **reference estimates, to be validated with an agronomist/Embrapa**):

| Crop | Soil: cover / N / bare days | Pests | Soybean bonus (bags/ha) | Mean Kc |
|---|---|---|---|---|
| Sorghum | 0.70 / 0.3 / 55 | 0.55 | 1 | 0.77 |
| Off-season beans | 0.40 / 0.4 / 75 | 0.30 (host of white mold, which attacks soybean) | 0 | 0.84 |
| Forage radish | 0.65 / 0.1 / 35 | 0.60 | 2 | 0.90 |
| Oat + radish | 0.85 / 0.2 / 35 | 0.65 | 2.5 | 0.85 |

Water balance of the new crops (FAO-56, Allen et al., 1998, tables 11, 12 and 22; root depth and critical phase estimated):

| Crop | Kc (ini / mid / end) | Stages (d) | p | Root | Critical phase (days after sowing) |
|---|---|---|---|---|---|
| Sorghum | 0.30 / 1.05 / 0.55 (table 12: mid 1.00–1.10) | 20/35/40/30 | 0.55 | 0.8 m | booting to grain fill (+50 to +90) |
| Beans | 0.40 / 1.15 / 0.35 | 20/30/40/20 | 0.45 | 0.6 m | flowering and pods (+30 to +65) |
| Forage radish | 0.50 / 1.10 / 0.95 (approximated by FAO's "turnip"; forage radish is not in the table) | 15/25/35/20 | 0.55 | 0.5 m | establishment (first 30 d) |
| Oat + radish | average of the oat and radish models | | | | establishment |

Price and cost sources for every crop (including the estimates) are in `data/ref/precos_custos.json`, generated by `field_shift.renda.atualizar`. Municipal yield: `ingest/pam_culturas_extra.py` writes `data/raw/ibge/pam_extra_oeste_pr.parquet`, read together with the base PAM. Sorghum and beans have PAM data in few municipalities and years: without recent PAM (≥ 3 years, latest ≥ 2018), the municipality uses the Western Paraná average, and the card says so.

## 5. Hard rules

They eliminate the candidate before scoring. An eliminated candidate appears in the result with the reason.

| Rule | Effect |
|---|---|
| Soybean-free period 02/06–31/08 with no live soybean (ADAPAR) | Eliminates |
| Soybean sowing only from 01/09 to 31/12 | Eliminates |
| Soybean after soybean in the same agricultural year is prohibited (Ordinance SDA/MAPA 1.124/2024) | Eliminates |
| Sowing of the second crop before the harvest of the current summer crop (estimated from the stage or the expected date; without them, soybean ~10/01, summer corn ~05/02; applies to the crops that follow the chosen date) | Eliminates |
| Harvest after the last sowing date considered (15/03): too late | Eliminates the crops that follow the sowing date; wheat, oat, radish and fallow stay |
| Sowing outside the crop's window (beans 15/01–28/02, sorghum 15/01–15/03; estimate based on ZARC/IDR-PR) | Eliminates |
| Corn after corn (summer corn + off-season corn or corn + brachiaria) | **Does not eliminate**: pest criterion −0.25 and a risk text (corn leafhopper/corn stunt) |
| ZARC | Credit/insurance warning only; does not eliminate |

In practice, soybean in the second window is **always eliminated**, even after summer corn (outside the legal soybean sowing window and the soybean-free period; after soybean, also soybean after soybean).
When the current crop is soybean harvested around 02/01, the derived sowing is 15/01 and the summer-corn candidates (in `proxima_safra`) fall under the limitation described in section 10. With sowing on 01/02 (catalog assumption), summer corn followed by off-season corn, corn + brachiaria, millet/crotalaria, sorghum or beans is also eliminated by the summer harvest; from 15/02 (beans) or 01/03 (the others) it comes back into the ranking.

**Corn after corn:** summer corn keeps a continuous host for the corn leafhopper (*Dalbulus maidis*) and corn stunt, the fall armyworm and leaf diseases. The rotation remains valid, but the pest criterion loses 0.25 points (catalog value, reference estimate to be validated) and the text goes into `card.riscos` and `card.evidencias`. Current alerts are in `/v1/contexto`.

**Note:** check the ordinances and dates with ADAPAR/MAPA before the pitch.

## 6. The 5 criteria

All on an absolute 0 to 1 scale (higher = better).

### 6.1 Climate risk

- **Formula:** risk = Π(1 − pᵢ) over the candidate's risks. Assumes independent events. No relevant risk = 1.0.
- **pᵢ:** years with the event / 34 (seasons 1991–2024).
- **Data:** daily NASA POWER for the ~50 km cell that contains the field (pre-computed).
- **Agricultural year convention:** Y = Jul/Y to Jun/Y+1. Off-season and wheat fall in Y+1.

| Event | Definition | Candidates |
|---|---|---|
| Off-season frost | T2M_MIN ≤ 3 °C between sowing+60 and sowing+120 days (flowering/grain fill) | Corn, corn + brachiaria |
| Wheat frost | T2M_MIN ≤ 3 °C from 15/08 to 30/09 | Wheat |
| Off-season frost (sorghum, beans) | same window as corn, as an approximation | Sorghum, beans |
| Off-season dry spell | ≥ 15 consecutive days with rain < 1 mm in Mar–Apr | Corn, corn + brachiaria, beans (sorghum, drought tolerant, does not count dry spells) |
| Cover crops and fallow | No relevant risk | Score 1.0 |

Example, off-season corn frost on field 72638, by sowing date:

| Sowing | 15/01 | 01/02 | 15/02 | 01/03 | 15/03 |
|---|---|---|---|---|---|
| Years with frost | 6% | 12% | 26% | 47% | 76% |

**Validation:** against 7 INMET stations, the Tmin correlation is 0.94. POWER underestimates frost days by ~40%.

### 6.2 Water

- **Formula:** mean over the 34 years of ΣETa/ΣETc in the critical phase.
- **Method:** daily FAO-56 water balance (bucket model), with daily POWER rain and Penman-Monteith ET0.
- **Soil:** available water capacity of the polygon from SoilGrids, with the Saxton & Rawls (2006) pedotransfer. Tends to underestimate it in Latosols.
- **Parameters:** root 0.6 to 0.8 m, Kc per stage (FAO-56), p = 0.55, Ks from depletion.

| Candidate | Critical phase |
|---|---|
| Corn (with or without brachiaria) | Sowing+55 to +95 days |
| Wheat | Heading/grain fill (sowing on 01/05) |
| Sorghum | Booting to grain fill (+50 to +90 days) |
| Beans | Flowering and pod formation (+30 to +65 days) |
| Cover crops (oat, millet/crotalaria, radish, oat + radish) | Establishment (30 days) |
| Fallow | No demand: 1.0 |

**Fallback without soil:** mean over the years of min(1, P / (Kc · ET0)) for the cycle.

### 6.3 Income

- **Formula (incremental margin over summer soybean):** the baseline is the municipality's summer soybean. Incremental = rotation margin − soybean margin = (summer margin − soybean margin) + second-crop margin + bonus on the following soybean (bonus in bags/ha × soybean price; it is the sum of the second crop's bonus and the summer-corn bonus, when applicable). With soybean in summer the first term is zero (the original formula: soybean is common to all and the score only looks at what the second season adds or takes away). The scale S is the same for every candidate, so income is comparable between soybean and summer corn. **income = clip(0.5 + incremental / (2·S), 0, 1)**, with S = max(municipal soybean margin, BRL 1,000/ha; constant `RENDA_ESCALA_MIN`). Incremental = +S gives 1.0; zero gives 0.5; −S gives 0. The BRL 1,000/ha floor prevents a low or negative soybean margin from stretching the scale.
- **Crop margin** = municipal yield (IBGE PAM, 5-year average) × price (SEAB/DERAL-PR, 12-month average) − variable cost (CONAB COE). Summer corn uses the 1st-season corn PAM; sorghum and beans use the extra PAM (or the Western Paraná average, without recent municipal PAM).
- **Cost:** uses Londrina/Ponta Grossa/Francisco Beltrão, because there is no CONAB sheet for Western Paraná. First-season corn in Paraná only exists for Ponta Grossa (reference yield of 12 t/ha, well above Western Paraná): the summer-corn margin tends to be underestimated and needs validation.
- **Cover crops:** margin = −establishment cost (estimate). Without an official source (sorghum: price and cost; radish, oat + radish and other cover crops: cost), the JSON marks "estimate — to be validated".
- **Rotation margin** = summer (soybean or summer corn) + second crop + straw/N bonus on the following soybean (bags/ha × soybean price; estimate). It is what the card and the API show (`margem.total_r_ha`), together with `incremental_r_ha` and `escala_S_r_ha`; only the incremental enters the score.
- **Why COE and not COT:** the decision is marginal. With COT every margin is negative.
- The card also shows the "bad year" margin (p20 yield).

### 6.4 Soil health

Soil = (cover + N fixation + (1 − bare days / 180)) / 3.

The three attributes come from the second crop's catalog entry. They are estimates to be validated with an agronomist/Embrapa. The summer crop does not change this criterion (the summer-corn benefit enters through the bonus on the following soybean, in income).

### 6.5 Pest break

Catalog attribute of the second crop, from 0 to 1 (estimate to be validated). Corn after corn subtracts 0.25 (minimum 0).

### 6.6 Field state informed by the farmer (optional)

Two optional inputs adjust the criteria without ever inventing data: if they are absent, nothing about them enters the analysis and the
card says "not considered". Every number below is tagged in `src/field_shift/app/estado_area.py` with its source or with "no confirmed
source"; the sources, with URL and the excerpt each number came from, are in [`fontes_estado_area.md`](fontes_estado_area.md).

- **`problemas_area`** (`nematoide`, `mofo_branco`, `cigarrinha`, `compactacao`). Each (problem, crop) pair has a qualitative level,
  `favorece`, `neutro` or `penaliza`, that moves `pragas` (or `solo`, for compaction) by one declared magnitude (+0.15 / −0.15). The
  direction (host or non-host, suppresses or favours) comes from Embrapa and academic sources we read; the magnitude is our
  modelling choice, not from the literature. A pair without a source we read is **neutral** and is listed in the card as "efeito sem
  fonte confirmada" and in `pendencias.md`. Caveats are carried to the card (for example, nematode effects depend on the species,
  so brachiaria and corn stay neutral).
- **Fertility in `analise_solo`** (P, K, Ca, Mg, Al, V%, CEC). Classes follow the Manual de Adubação e Calagem do Paraná: P depends on
  the clay band of the farmer's own `argila_pct` (without it, the most demanding band), K, V% and Al have their own tables. Liming uses
  the base-saturation method of the Manual, with a reference PRNT of 76.9% (CBPTT 2020) and V2 = 60% (the Manual groups corn, wheat,
  beans, sorghum and soybean in the same 51–70% class). P/K doses come from the Manual (corn, expected yield < 8 t/ha) and from CBPTT 2020
  (wheat); beans and sorghum doses, lime price, the dose cap and the penalty/bonus sizes have no confirmed source. The fertilizer cost
  is the difference against the "medium" class dose, which we assume is what the CONAB cost already embeds (an assumption without
  source).

## 7. Final score

**Score = Σ weightᵢ × criterionᵢ / Σ weightᵢ**

- Contribution of each criterion = weightᵢ × criterionᵢ / Σ weights. It feeds the card's "why" (what weighed most).
- The criteria stay on an absolute scale, with no min-max across candidates. That way, small differences are not stretched artificially. Income is also absolute: it measures the second season's increment on the scale of the municipality's own soybean margin.
- The "why" of each alternative compares it with the current rotation: it takes the 2–3 criteria with the largest weighted difference (weight × Δcriterion / Σ weights) and cites the numbers behind them (BRL/ha of the second season, bare days, risk probability, water).

## 8. Worked example: field 72638

Toledo, 103.9 ha, slope 6.9%, clay 60%. Default weights. The tables below fix the sowing date (`semeadura_safrinha` 01/02 or 15/03, sent explicitly) with the current rotation `soja__milho_safrinha`, and show the `agora` block (soybean in summer); with `estagio_verao` `enchimento_graos` and no sowing date, the sowing would be derived (15/01) and the numbers move slightly. The per-stage example is in section 2.1.

**Sowing 01/02**

| Candidate | Score | Income | Soil | Water | Pests | Risk |
|---|---|---|---|---|---|---|
| Corn + brachiaria | 0.814 | 0.977 | 0.711 | 0.844 | 0.650 | 0.779 |
| Off-season corn (current) | 0.757 | 0.958 | 0.556 | 0.859 | 0.500 | 0.779 |
| Millet/crotalaria | 0.756 | 0.459 | 0.819 | 0.998 | 0.700 | 1.000 |
| Oat | 0.698 | 0.438 | 0.626 | 1.000 | 0.600 | 1.000 |
| Fallow | 0.547 | 0.408 | 0.122 | 1.000 | 0.300 | 1.000 |
| Wheat | 0.466 | 0.000 | 0.504 | 0.949 | 0.600 | 0.588 |
| Off-season soybean | Eliminated | | | | | |

**Sowing 15/03**

| Candidate | Score |
|---|---|
| Millet/crotalaria | 0.756 |
| Corn + brachiaria | 0.733 |
| Oat | 0.698 |
| Off-season corn (current) | 0.675 |
| Fallow | 0.547 |
| Wheat | 0.466 |

**Income calculation (Toledo, S = BRL 1,083/ha, the soybean margin)**

| Candidate | Incremental (BRL/ha) | 0.5 + incremental / (2·S) | Income |
|---|---|---|---|
| Corn + brachiaria | +1,033 (873 − 200 + 360 bonus) | 0.5 + 1,033 / 2,166 | 0.977 |
| Off-season corn | +993 | 0.5 + 993 / 2,166 | 0.958 |
| Millet/crotalaria | −90 | 0.5 − 90 / 2,166 | 0.459 |
| Wheat | −1,704 | 0.5 − 1,704 / 2,166 → clipped at 0 | 0.000 |

**Calculation for corn + brachiaria on 01/02**

| Criterion | Weight | Value | Weight × value |
|---|---|---|---|
| Income | 5 | 0.98 | 4.89 |
| Soil | 3 | 0.71 | 2.13 |
| Water | 3 | 0.84 | 2.53 |
| Pests | 3 | 0.65 | 1.95 |
| Risk | 3 | 0.78 | 2.34 |
| **Sum** | **17** | | **13.84** |

Score = 13.84 / 17 = **0.814**. Income weighed most (4.89 / 17 = 0.29 of the score).

**Example "why" (alternative, compared with the current rotation):** "Compared with the current rotation (off-season corn): improves soil health (0.71 vs 0.56; ~30 days of bare soil vs 60), breaks the pest cycle better (0.65 vs 0.50) and adds BRL 1,033/ha vs BRL 993/ha in the second season (+4%). Same climate risk (...)." For the current rotation: "This is the current rotation; it ranked 2nd among 10 valid options. The best alternative (off-season corn + brachiaria) scores 0.82." (The count is within the `agora` block: the 11 combinations with soybean in summer minus soybean in the second window.)

**Corn sowing-date trade-off**

| Sowing | Frost | Water |
|---|---|---|
| 01/02 | 12% | 0.86 (7 of 34 years below 70%) |
| 15/03 | 76% | 0.96 |

Sowing late gives more water and much more frost. That is why off-season corn drops from 0.757 to 0.675 on 15/03 and the cover crops take the top.

**Margins (PAM Toledo 2021–2025, SEAB prices, CONAB COE cost)**

| Crop | Yield (bags/ha) | Price (BRL/bag) | Cost (BRL/ha) | Margin (BRL/ha) |
|---|---|---|---|---|
| Soybean | 49 | 120.14 | 4,824 | +1,083 |
| 2nd-season corn | 103 | 53.89 | 4,678 | +873 |
| Wheat | 37 | 68.44 | 4,334 | −1,824 |

**PAM × climate evidence:** in years with frost in the window, off-season corn in Western Paraná yielded ~6.5% below trend (effective n ≈ 23 years).

## 9. Real data × estimate

| Comes from data | Source |
|---|---|
| Rain, temperature, ET0 (34 years) | NASA POWER |
| Soil available water capacity | SoilGrids |
| Land-use history | MapBiomas |
| Slope | NASADEM |
| Municipal yield | IBGE PAM |
| Prices | SEAB/DERAL-PR |
| Costs | CONAB (from outside the region, see below) |

| Adjustable assumption | Note |
|---|---|
| Kc per stage and root depth | FAO-56 values, not measured on the field |
| p = 0.55 and wheat/oat sown on 01/05 | Fixed; validate with ZARC |
| Straw/N bonus on the following soybean | bags/ha per candidate (0 to 3) |
| Cover crop cost | Estimate |
| Soil attributes (cover, N, bare days) and pests | Catalog estimates |
| Summer harvest dates, bean and sorghum sowing windows, summer-corn bonus (+3 bags/ha) and corn-after-corn penalty (−0.25) | Reference estimates; validate with ZARC/Embrapa/agronomist |
| Kc, p and critical phase for sorghum, beans and radish | FAO-56 (radish approximated by "turnip"); root depth and critical phase estimated |
| Sorghum price and cost; cost of radish, oat + radish and other cover crops | "estimate — to be validated" in `precos_custos.json` |
| CONAB costs | Londrina/Ponta Grossa/Francisco Beltrão, not Western Paraná; summer corn for Ponta Grossa (12 t/ha) |

## 10. Limitations and next steps

**Limitations**

- ~50 km grid: fields in the same cell get the same climate.
- Historical frequency, not a forecast for a specific year. Assumes a stationary climate, and 34 years is a small sample.
- POWER underestimates frost (~40%).
- The pedotransfer tends to underestimate the available water capacity in Latosols (the farmer's soil analysis solves this).
- Irrigation: the yield gain is not modeled (only water, risk and cost); net depth, no application losses.
- Soil analysis: the sample (default 0–20 cm) is taken as representative of the whole root profile.
- Machinery outsourcing, irrigation cost and market levels are estimates to be validated.
- The summer crop (soybean or summer corn) does not enter the water and climate-risk criteria; only the second window does.
- ZARC is not implemented yet.
- Stage durations and the catalog harvest dates are estimates, to be validated with Embrapa/an agronomist.
- **Known limitation (open decision): sowing date of the `proxima_safra` block.** The block uses the same second-window sowing date as `agora`, derived from the harvest of the *current* crop (e.g. 15/01 for soybean harvested ~02/01). Summer corn in the next season is harvested later (~05/02), so with that date summer corn followed by off-season corn, corn + brachiaria, millet/crotalaria, sorghum or beans is eliminated, and the block ends up with only wheat, oat, radish and fallow (the off-season crops all disappear). The alternative is to compute the next season's sowing with the typical summer-corn harvest, so those candidates can be evaluated; it has not been decided yet and the current behavior was left as is. Tracked in `docs/pendencias.md`.

**Next steps:** ZARC; regional costs; validation with an agronomist; SMAP for the current season; PAM × climate regression in income.

## Current context (informational)

The `GET/POST /v1/contexto` endpoint (code in `src/field_shift/contexto/`) queries official sources about ongoing events at request time:
ENSO (NOAA CPC, with the historical frequency of dry spells and frost per ENSO phase in the field's cell), soil moisture
(NASA SMAP L4, with the climatology percentile), MJO (NOAA PSL) and pest outbreaks (IDR-PR soybean rust and ADAPAR/IDR-PR alerts
curated by hand). **None of this enters the scores**: the ranking is still computed only from the climatology (POWER 1991-2024), soil, terrain,
history and income described above. The texts attribute the information to the source ("NOAA indicates...", "IDR-PR reports...") and do not claim
a loss or a probability for the field; the per-phase history has ~10 years per phase and may be only sampling noise. Each source has a cache
and a fallback; if it fails, the block comes back as `{"disponivel": false, "motivo": ...}` and the rest continues.
