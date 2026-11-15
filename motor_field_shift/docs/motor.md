# Field Shift — Rotation engine logic

How the engine computes and ranks the rotation options. Date: 2026-11-15. Coverage: the whole of Paraná (399 municipalities); the pilot and the income backtest are Western Paraná, and the worked example is field 72638. Code in `src/field_shift/app/engine.py` (catalog, rules, scoring), supported by `climate/`, `water/`, `soil/` and `income/`.

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
2. **Stage of the summer crop (`estagio_verao`, optional).** Estimated harvest = `data_referencia` + typical days of the stage. `data_referencia` is "today" for the farmer (ISO date; default: today); sending it makes the calculation deterministic. Typical days to harvest (estimates, scale of Fehr & Caviness / Ritchie, middle of the range, medium cycle, Western Paraná; **to be validated with Embrapa**; code in `src/field_shift/crop_calendar.py`):

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
4. **Sowing of the second window.** Without `semeadura_safrinha`, it is the first date among 15/01, 01/02, 15/02, 01/03 and 15/03 on or after the estimated harvest (+ `PREP_DAYS_2ND`, today 0 days, no-till). If the farmer sends the date, it wins but cannot be before the harvest (422). If the harvest is after 15/03, it is "too late" (`semeadura_2a` null, warning): the crops that follow the sowing date are eliminated and only wheat, oat, radish and fallow remain. With no stage, no harvest date and no sowing date, the engine falls back to the catalog assumption (soybean harvested ~10/01, summer corn ~05/02) and 01/02, with a warning asking for the stage.
5. **Blocks.** `agora` = combinations with the **same summer crop** as the current rotation (what enters after this harvest). `proxima_safra` = combinations with the **other summer crop**, compared with the current one (decision for the next season). `posicao` restarts at 1 in each block; each block has `ranking`, `alternativas` (best ones without the current rotation, up to `n_alternativas`) and `eliminadas`. At the top level, `ranking`, `alternativas` and `eliminadas` are kept as compatibility aliases (`eliminadas` = union of both blocks). The response also brings `cultura_atual`, `estagio_verao`, `colheita_estimada` (`origem`: `estagio`, `informada` or `premissa`), `semeadura_2a` (`derivada`, `informada` or `premissa`) and `dias_ate_colheita`.
6. **Gain against the current rotation (`ganho_vs_atual`).** On every item except the current rotation (null if the current rotation was eliminated): `soja_seguinte_sc` (+ `_faixa`) and `soja_seguinte_rs` (bonus on the following soybean × DERAL price; catalog estimate), `renda_2a_safra` and `margem_total` (BRL/ha; data), `solo` (bare days and cover; estimate; negative days = better), `agua` and `risco_climatico` (difference of criterion; data). Every number carries its `origem` so that data and estimate are told apart. The current rotation is always evaluated for the comparison, even if it is not in `rotacoes`.

Example (field 72638, soybean in `enchimento_graos`, `data_referencia` 2026-12-01): harvest ~02/01 (32 days), sowing derived as 15/01. `agora` has 10 valid combinations with soybean (best: soybean → off-season corn + brachiaria, score 0.794; the current one, off-season corn, is 3rd, behind millet/crotalaria 0.757) and soybean in the second window eliminated. `proxima_safra` shows only the fixed-date crops after summer corn (see the known limitation in section 10). Real response: `api/exemplos/recomendacao_talhao_72638.json`.

## 3. Inputs

| Input | Default | Effect |
|---|---|---|
| Field | Polygon in Paraná, point or demo ID (72638) | Defines the climate cell, soil, terrain and municipality (PAM) |
| Current rotation (`rotacao_atual`) | **Required** | Defines the current summer crop (blocks `agora`/`proxima_safra`) and is the comparison baseline (`atual`, `ganho_vs_atual`) |
| Stage of the summer crop (`estagio_verao`) and/or expected harvest (`colheita_prevista`), reference date (`data_referencia`) | None (catalog assumption, with a warning); `data_referencia` = today | Estimated harvest, from which the sowing of the second window is derived (section 2.1) |
| Sowing date of the second crop ("safrinha") | Derived from the estimated harvest; without stage or harvest, 01/02 (options: 15/01, 01/02, 15/02, 01/03, 15/03) | Changes the frost risk and water for corn, sorghum, beans and millet/crotalaria, and applies in the calendar rules (section 5). If sent, it wins over the derived one but cannot be before the harvest |
| Weights 0–10 | income 5, soil 3, water 3, pests 3, risk 3 | Weight the 5 criteria in the final score |
| Rotations to evaluate (`rotacoes`) | All catalog combinations (22) | List of `{verao, segunda}` (closed enums): the engine evaluates and ranks only those; one eliminated by the rules comes back in `eliminadas`, with the reason. An empty, duplicated or out-of-enum list is a validation error (422) |
| Prices/costs | Reference (SEAB/DERAL and CONAB) | Provided values override the reference in the income calculation |
| Own yield (`ajustes.produtividade`) | Municipal PAM | **Income:** replaces the PAM yield in the margin (soybean, 2nd-season corn, summer corn, wheat, beans, sorghum); the bad year scales by own yield × p20/PAM average; the soybean value changes the scale S |
| Soil analysis (`analise_solo`) | SoilGrids | **Water:** the available water capacity comes from the analysis (`cad_mm_cm` directly, or Saxton & Rawls with the provided sand, clay and organic matter), uniform over 0–60 cm. The diagnosis `solo` block then cites "farmer's soil analysis" |
| Restrictions (`restricoes`) | None | **Hard rules:** excluded rotations (new id, or legacy slug = soybean in summer) and no local buyer (corn, wheat, sorghum, beans; also applies to the summer crop) eliminate the rotation. **Income:** a missing machine (corn header, one per corn harvest; intercrop seeder) does not eliminate; it adds an outsourcing cost (estimates: BRL 250/ha and BRL 80/ha) and a warning on the card. Each candidate shows `mercado_oeste_pr` (high/medium/low/not applicable; estimate to be validated) |
| Irrigation (`irrigacao`) | Rainfed | **Water:** the balance irrigates second-window corn, corn+brachiaria, wheat, sorghum and beans when Dr > p·TAW (p = 0.55; beans 0.45), refilling up to capacity, limited by the maximum daily depth, over the whole cycle; the criterion goes up. **Risk:** the water deficit stops counting for those candidates (frost still counts). **Income:** subtracts average depth × cost (BRL/mm/ha). Does not change the expected yield; cover crops and fallow are not irrigated |

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
| Off-season corn | Grain | the chosen date (15/01–15/03) | frost + water deficit | corn | PAM 2nd season; DERAL; CONAB Londrina |
| Off-season corn + brachiaria | Intercrop | the chosen date | frost + water deficit | corn | same + brachiaria (estimate) |
| Wheat | Grain | 01/05 | wheat frost | wheat | PAM; DERAL; CONAB Ponta Grossa |
| Sorghum (new) | Grain | the chosen date, window 15/01–15/03 | frost (drought tolerant) | sorghum | PAM sorghum (SIDRA 1612); estimated price (75% of DERAL corn, the CONAB minimum-price ratio); estimated cost (CONAB sorghum Rio Verde-GO) |
| Off-season beans (new) | Grain | the chosen date, window 15/01–28/02 | frost + water deficit | beans | PAM 2nd-season beans (SIDRA 1002); DERAL black beans; CONAB 2nd-season beans Francisco Beltrão-PR |
| Oat (cover/straw) | Cover | 01/05 | none | no sale | estimated cost |
| Millet/crotalaria | Cover | the chosen date | none | no sale | estimated cost |
| Forage radish (new) | Cover | 01/04 | none | no sale | estimated cost |
| Oat + radish (new) | Cover (mix) | 01/05 (oat) and 01/04 (radish) | none | no sale | estimated cost |
| Fallow | No crop | n/a | none | no sale | estimated cost |
| Off-season soybean | Grain | the chosen date | water deficit | n/a | blocked by the rules (always eliminated) |

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

Price and cost sources for every crop (including the estimates) are in `data/ref/precos_custos.json`, generated by `field_shift.income.update`. Municipal yield: `ingest/pam_extra_crops.py --regiao pr` writes `data/raw/ibge/pam_extra_pr.parquet` (399 municipalities; `pam_extra_oeste_pr.parquet` is the Oeste-only fallback), read together with the base PAM. Sorghum and beans have PAM data in few municipalities and years: without recent PAM (≥ 3 years, latest ≥ 2018), the municipality uses the average of its own IBGE mesoregion (`data/ref/mesorregioes_pr.csv`; the Western Paraná average for an Oeste municipality, all of Paraná when no municipality of the mesoregion has the crop), and the card says so. The same mesoregion average replaces the municipality when it has no PAM for soybean, 2nd-season corn and wheat.

## 5. Hard rules

They eliminate the candidate before scoring. An eliminated candidate appears in the result with the reason.

| Rule | Effect |
|---|---|
| Soybean-free period with no live soybean (ADAPAR, by region: Região 1 21/06–19/09, Região 2 02/06–31/08, Região 3 12/06–10/09) | Eliminates |
| Soybean sowing only inside the region's window (Região 1 20/09–20/01, Região 2 01/09–31/12, Região 3 11/09–10/01) | Eliminates |
| Soybean after soybean in the same agricultural year is prohibited (Ordinance SDA/MAPA 1.124/2024) | Eliminates |
| Sowing of the second crop before the harvest of the current summer crop (estimated from the stage or the expected date; without them, soybean ~10/01, summer corn ~05/02; applies to the crops that follow the chosen date) | Eliminates |
| Harvest after the last sowing date considered (15/03): too late | Eliminates the crops that follow the sowing date; wheat, oat, radish and fallow stay |
| Sowing outside the crop's window (beans 15/01–28/02, sorghum 15/01–15/03; estimate based on ZARC/IDR-PR) | Eliminates |
| Corn after corn (summer corn + off-season corn or corn + brachiaria) | **Does not eliminate**: pest criterion −0.25 and a risk text (corn leafhopper/corn stunt) |
| ZARC | Warning only; does not eliminate and does not change the score. With the ZARC table built (`ingest/zarc_pr.py`), each candidate is checked against ZARC 2025/2026 for the field's municipality and sowing date (summer crop at its assumed date, second crop at the chosen or fixed date); outside ZARC the card gets a specific warning (crop, date, reason, loss of subsidised credit/Proagro/insurance) and the item a `zarc` field. Without the table, the generic warning is kept |

In practice, soybean in the second window is **always eliminated**, even after summer corn (outside the legal soybean sowing window and the soybean-free period; after soybean, also soybean after soybean).
When the current crop is soybean harvested around 02/01, the derived sowing is 15/01 and the summer-corn candidates (in `proxima_safra`) fall under the limitation described in section 10. With sowing on 01/02 (catalog assumption), summer corn followed by off-season corn, corn + brachiaria, millet/crotalaria, sorghum or beans is also eliminated by the summer harvest; from 15/02 (beans) or 01/03 (the others) it comes back into the ranking.

**Corn after corn:** summer corn keeps a continuous host for the corn leafhopper (*Dalbulus maidis*) and corn stunt, the fall armyworm and leaf diseases. The rotation remains valid, but the pest criterion loses 0.25 points (catalog value, reference estimate to be validated) and the text goes into `card.riscos` and `card.evidencias`. Current alerts are in `/v1/contexto`.

**Regional calendar:** the three windows come from Portaria SDA/MAPA 1.579/2026 (crop 2026/2027); each of the 399 municipalities belongs to one region (annex lists), stored in `data/ref/vazio_sanitario_pr.json`. All 50 Oeste municipalities are in Região 2, so the Oeste behaviour is unchanged. Without a municipality the engine uses Região 2. The dates are per crop year: refresh the file every April (`ingest/soybean_free_period_pr.py`).

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
| Water deficit in the critical phase | Share of the 34 years with ΣETa/ΣETc < 0.55 in the crop's critical phase (FAO-56 daily balance, field soil, chosen sowing date; same balance as §6.2). Without soil data it falls back to the cell's dry spell (≥ 15 consecutive days with rain < 1 mm in Mar–Apr). Irrigated candidates do not count it | Corn, corn + brachiaria, beans, off-season soybean (sorghum, drought tolerant, does not count it) |
| Cover crops and fallow | No relevant risk | Score 1.0 |

Example, off-season corn frost on field 72638, by sowing date:

| Sowing | 15/01 | 01/02 | 15/02 | 01/03 | 15/03 |
|---|---|---|---|---|---|
| Years with frost | 6% | 12% | 26% | 47% | 76% |

**Validation:** against 7 INMET stations, the Tmin correlation is 0.94. POWER underestimates frost days by ~40%. The water-deficit threshold (0.55) was calibrated against IBGE PAM off-season corn failures and the ZARC classes; the old dry-spell count had no predictive value (`docs/validation.md` §2.4 and §3).

**How far to trust it (`docs/validation.md` §6.1):** for off-season corn the loss probability is right on average (24 % predicted vs 23 % of PAM failures in the Oeste, 2003–2025), but it does not tell which season will fail: out of sample (leave one season out, and training only on past seasons) neither the engine's flags nor richer weather models (heat at flowering, rain at harvest, establishment temperature) beat the plain failure rate. Failures also do not differ between Oeste municipalities beyond chance. The criterion therefore works as a climatological average, not as a forecast, and the API says so (`incerteza.risco_climatico.confianca` = "baixa"; other crops: "não validada").

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

- **Formula (incremental margin over summer soybean):** the baseline is the municipality's summer soybean. Incremental = rotation margin − soybean margin = (summer margin − soybean margin) + second-crop margin + bonus on the following soybean (bonus in bags/ha × soybean price; it is the sum of the second crop's bonus and the summer-corn bonus, when applicable). With soybean in summer the first term is zero (the original formula: soybean is common to all and the score only looks at what the second season adds or takes away). The scale S is the same for every candidate, so income is comparable between soybean and summer corn. **income = 0.5 + 0.5 · tanh(incremental / S)**, with S = max(municipal soybean margin, BRL 1,000/ha; constant `RENDA_ESCALA_MIN`; `engine.income_score`). Zero gives 0.5; +S gives 0.88; −S gives 0.12; it never reaches 0 or 1. Near zero it has the same slope as the earlier linear form clip(0.5 + incremental / (2·S), 0, 1); unlike it, it never saturates, so two good options are not tied at 1.0 (before, both corn options on field 72638 sat at 1.0 and income could not separate them). The BRL 1,000/ha floor prevents a low or negative soybean margin from stretching the scale.
- **Second-crop margin in the score: track record when it exists (`income.history.apply_to_income`).** For off-season corn, corn + brachiaria and wheat, the second-crop margin used in the incremental is the **mean realized margin of the last 5 seasons in the municipality** (in soybean bags/ha, × the soybean price in use), not the current-price estimate below. In the historical backtest this choice was better in 13 of 16 seasons (+1.26 soybean bags/ha/yr; 90 % season-bootstrap interval +0.60 to +2.05) and cut the margin error by 19 %, with no fitted parameter (`docs/validation.md` §6.2). The current-price estimate is kept when the farmer typed their own price, cost or yield for that crop, or a cost line other than COE (the record is built on the COE), and for crops without a cost series (sorghum, beans, covers, fallow). The API reports which one was used: `margem.base_renda` ("historico" | "preco_atual"), `margem.incremental_r_ha` (used in the score) and `margem.incremental_preco_atual_r_ha`.
- **Crop margin (current-price estimate; shown on the card and in `margem.itens`)** = expected municipal yield (IBGE PAM: linear trend of the last 10 years with data, projected to the next season and clipped to the window's min–max; plain mean with fewer than 5 years; `pam.produtividade.expected_yield`) × price (SEAB/DERAL-PR, 12-month average) − variable cost (CONAB COE). Summer corn uses the 1st-season corn PAM; sorghum and beans use the extra PAM (or the Western Paraná average, without recent municipal PAM).
- **Cost:** uses Londrina/Ponta Grossa/Francisco Beltrão, because there is no CONAB sheet for Western Paraná. First-season corn in Paraná only exists for Ponta Grossa (reference yield of 12 t/ha, well above Western Paraná): the summer-corn margin tends to be underestimated and needs validation.
- **Cover crops:** margin = −establishment cost (estimate). Without an official source (sorghum: price and cost; radish, oat + radish and other cover crops: cost), the JSON marks "estimate — to be validated".
- **Rotation margin** = summer (soybean or summer corn) + second crop + straw/N bonus on the following soybean (bags/ha × soybean price; estimate). It is what the card and the API show (`margem.total_r_ha`), together with `incremental_r_ha` and `escala_S_r_ha`; only the incremental enters the score.
- **Why COE and not COT:** the decision is marginal. With COT every margin is negative.
- The card also shows the "bad year" margin (p20 yield of the same 10 years, capped at the expected yield).
- **Track record:** for off-season corn, corn + brachiaria and wheat the card and `historico_renda` show the realized second-crop margin of each of the last 5 seasons in the municipality, in soybean bags/ha (PAM yield × Paraná realized price − CONAB Londrina cost of each season; `income/history.py`). Its mean enters the score as described above; its worst and best seasons give the income range in `incerteza` (§7.1).
- **Technical tie:** options less than 0.02 below the best score are flagged (`empate_tecnico` in the block, warning on their cards): ±20 % on single catalog estimates moves the top gap by up to ~0.02 (`docs/validation.md` §1.2).

### 6.4 Soil health

Soil = (cover + N fixation + (1 − bare days / 180)) / 3.

The three attributes come from the second crop's catalog entry. They are estimates to be validated with an agronomist/Embrapa, except the bare-soil days of fallow: 90 = off-season corn (60) + the difference measured from space around field 72638 between single- and double-crop years (~31 bare days/yr, HLS NDVI; `docs/validation.md` §5.2). It was 150 (estimate), which overstated the gap by ~3×. The summer crop does not change this criterion (the summer-corn benefit enters through the bonus on the following soybean, in income).

### 6.5 Pest break

Catalog attribute of the second crop, from 0 to 1 (estimate to be validated). Corn after corn subtracts 0.25 (minimum 0).

### 6.6 Field state informed by the farmer (optional)

Two optional inputs adjust the criteria without ever inventing data: if they are absent, nothing about them enters the analysis and the
card says "not considered". Every number below is tagged in `src/field_shift/app/field_state.py` with its source or with "no confirmed
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
  (wheat); beans and sorghum doses, lime price and the dose cap have no confirmed source. The fertilizer cost
  is the difference against the "medium" class dose, which we assume is what the CONAB cost already embeds (an assumption without
  source).
- **Organic matter in `analise_solo`** (`materia_organica_pct` or `carbono_organico_g_kg`). Before it only fed the water capacity; now it
  also gets the organic-carbon class of the Manual PR (Quadro 4, g/dm³: very low < 4, low 4–8, medium 9–14, high 15–20, very high > 20;
  MO = C × 1.72). g/kg is read as g/dm³ (no density correction; said on the card).
- **Fertility and organic-matter effects on `solo`** (`FERTILITY_EFFECTS`), same scheme as the area problems: the direction comes from a
  source we read, the size is the declared ±0.15 (acidity: half at severity 1).

  | Soil condition | Favours | Penalises | Sources |
  |---|---|---|---|
  | Acid (Al medium/high or V% low) | | corn, corn + brachiaria, wheat, beans, sorghum, off-season soybean | Manual PR via SENAR PR.0404 (low acid-tolerance class) |
  | P or K low | corn + brachiaria (up to 40 kg/ha K2O recycled to 0–5 cm), forage radish | | Resende et al. 2021 (Embrapa CT 277); Betta et al. 2008; Viola et al. 2013 |
  | Organic matter low (C ≤ 8 g/dm³, MO ≤ ~1.4 %) | corn + brachiaria, millet/crotalaria | fallow (no residue input) | Resende et al. 2021 (MO up after 9 years, not after one cycle); Bertin et al. 2005 |

  Oat + radish and millet/crotalaria on low P/K, and oat + radish on low MO, have no source and stay neutral (listed on the card). The
  unsourced acidity penalty (0.08 × severity), recycling bonus (0.06–0.10) and crotalaria bonus (0.05) were removed.
- **No saturation.** The deltas used to be added and clipped to [0, 1], so a degraded field put millet/crotalaria at 1.00 and tied it with
  corn + brachiaria. Now `estado_area.soft_add` adds them with slope 1 at zero and an exponential approach to the bound
  (Δ > 0: 1 − (1 − base)·e^(−Δ/(1 − base)); Δ < 0: base·e^(Δ/base)), with no extra parameter, for `solo` and `pragas`. Without the
  farmer's input nothing changes (the regression test keeps the same scores).
- **Recovery cost (`recuperacao_solo`, card line "Recuperar o solo com esta opção")**, on every option when the informed soil needs
  recovery (acid, P/K low or MO low): liming of the area in full (once; the margin charges one third per year), this crop's extra P/K per
  year, and the income given up against the option with the highest incremental income. For corn + brachiaria on low P/K the card adds
  the K2O credit "up to" 40 kg/ha × KCl price (Resende et al. 2021), not subtracted. With low MO the card says the gain takes years.
  Field 72638, degraded soil (poor, acid, MO 1.2 %, compaction, nematode): corn + brachiaria 0.777 (soil 0.898; recovery ≈ BRL 1,310/ha in
  year 1: liming 901 + P/K 409), millet/crotalaria 0.747 (soil 0.965; ≈ BRL 1,987/ha: liming 901 + 1,086 of income given up); before
  the change they tied at 0.753.

## 7. Final score

**Score = Σ weightᵢ × criterionᵢ / Σ weightᵢ**

- Contribution of each criterion = weightᵢ × criterionᵢ / Σ weights. It feeds the card's "why" (what weighed most).
- The criteria stay on an absolute scale, with no min-max across candidates. That way, small differences are not stretched artificially. Income is also absolute: it measures the second season's increment on the scale of the municipality's own soybean margin.
- The "why" of each alternative compares it with the current rotation: it takes the 2–3 criteria with the largest weighted difference (weight × Δcriterion / Σ weights) and cites the numbers behind them (BRL/ha of the second season, bare days, risk probability, water).

### 7.1 Uncertainty in the response

Every ranking item carries `incerteza`, so the result is not read as more precise than the data allow:

| Field | What it is |
|---|---|
| `renda.faixa_r_ha` [worst, best] | Incremental margin with the worst and the best of the last 5 realized seasons (`origem` "historico"); with the current-price estimate, only the worst (bad-year p20 yield; best = null, `origem` "ano_ruim_p20"); covers and fallow have only a cost (`origem` "custo_fixo", no range) |
| `nota_faixa` [min, max] | Score with income at those two ends and the other criteria fixed |
| `nota_por_safra` | Score repeating each of the last seasons (track-record crops only) |
| `risco_climatico` | Probability of some adverse event, the events, `confianca` ("baixa" for off-season corn: calibrated on average but not a forecast, §6.1; "não validada" for the others) and the text |
| `criterios_estimados` | Criteria that are still catalog estimates (`solo`, `pragas`) |

Each block also carries `estabilidade`: how many of the last 5 seasons each option would be first if that season's realized income repeated (other criteria fixed). Together with `empate_tecnico` (§6.3) it shows whether the first place is robust.

## 8. Worked example: field 72638

Toledo, 103.9 ha, slope 6.9%, clay 60%. Default weights. The tables below fix the sowing date (`semeadura_safrinha` 01/02 or 15/03, sent explicitly) with the current rotation `soja__milho_safrinha`, and show the `agora` block (soybean in summer); with `estagio_verao` `enchimento_graos` and no sowing date, the sowing would be derived (15/01) and the numbers move slightly. The per-stage example is in section 2.1.

**Sowing 01/02**

| Candidate | Score | Income | Soil | Water | Pests | Risk |
|---|---|---|---|---|---|---|
| Corn + brachiaria | 0.795 | 0.914 | 0.711 | 0.844 | 0.650 | 0.779 |
| Millet/crotalaria | 0.757 | 0.463 | 0.819 | 0.998 | 0.700 | 1.000 |
| Off-season corn (current) | 0.747 | 0.909 | 0.556 | 0.858 | 0.500 | 0.804 |
| Oat + radish | 0.710 | 0.458 | 0.619 | 0.994 | 0.650 | 1.000 |
| Oat | 0.700 | 0.444 | 0.626 | 1.000 | 0.600 | 1.000 |
| Forage radish | 0.691 | 0.485 | 0.519 | 0.988 | 0.600 | 1.000 |
| Sorghum | 0.624 | 0.397 | 0.565 | 0.878 | 0.550 | 0.882 |
| Beans | 0.575 | 0.474 | 0.461 | 0.849 | 0.300 | 0.856 |
| Fallow | 0.570 | 0.417 | 0.233 | 1.000 | 0.300 | 1.000 |
| Wheat | 0.524 | 0.196 | 0.504 | 0.949 | 0.600 | 0.588 |
| Off-season soybean | Eliminated | | | | | |

**Sowing 15/03** (beans eliminated: outside its window)

| Candidate | Score |
|---|---|
| Millet/crotalaria | 0.757 |
| Corn + brachiaria | 0.719 |
| Oat + radish | 0.710 |
| Oat | 0.700 |
| Forage radish | 0.691 |
| Off-season corn (current) | 0.665 |
| Fallow | 0.570 |
| Sorghum | 0.525 |
| Wheat | 0.524 |

Millet/crotalaria leads by 0.038 (no technical tie at the default weights; with income weight 6 the two are 0.012 apart and the response flags `empate_tecnico`). The corn options sown on 15/03 are also outside ZARC 2025/2026 in Toledo, so their cards carry the ZARC warning (the score does not change).

**Income calculation (Toledo, S = BRL 1,192/ha, the soybean margin; soybean BRL 120.14/bag)**

| Candidate | Basis | Incremental used (BRL/ha) | At current price (BRL/ha) | Income = 0.5 + 0.5·tanh(incr./S) | Range, worst–best season (BRL/ha) |
|---|---|---|---|---|---|
| Corn + brachiaria | track record 8.7 bags | +1,406 (8.7 × 120.14 + 360 bonus) | +1,802 | 0.914 | +60 to +2,943 |
| Off-season corn | track record 10.4 bags | +1,370 (10.4 × 120.14 + 120 bonus) | +1,762 | 0.909 | +12 to +2,907 |
| Millet/crotalaria | cost only | −90 | −90 | 0.463 | — |
| Wheat | track record −8.0 bags | −841 | −1,780 | 0.196 | −1,610 to +312 |

The track record is lower than the current-price estimate for corn (2021 was a failure: −0.9 bags) and higher for wheat. Income now separates the two corn options; with the old clipped formula both sat at 1.0. Score range (`nota_faixa`): corn + brachiaria 0.681–0.819, off-season corn 0.628–0.772. `estabilidade`: repeating each of the seasons 2021–2025, corn + brachiaria is first in 4 and millet/crotalaria in 1 (2021).

**Calculation for corn + brachiaria on 01/02**

| Criterion | Weight | Value | Weight × value |
|---|---|---|---|
| Income | 5 | 0.914 | 4.57 |
| Soil | 3 | 0.711 | 2.13 |
| Water | 3 | 0.844 | 2.53 |
| Pests | 3 | 0.650 | 1.95 |
| Risk | 3 | 0.779 | 2.34 |
| **Sum** | **17** | | **13.52** |

Score = 13.52 / 17 = **0.795** (the criteria shown are rounded). Income weighed most (4.57 / 17 = 0.27 of the score).

**Example "why" (alternative, compared with the current rotation):** "Compared with the current rotation (off-season corn): improves soil health (0.71 vs 0.56; ~30 days of bare soil vs 60) and breaks the pest cycle better (0.65 vs 0.50). Same climate risk (some adverse event in 22% of years). Biggest contributions to the score: Income (0.29) and Water (0.15)." For the current rotation: "This is the current rotation; it ranked 3rd among 10 valid options. The best alternative (off-season corn + brachiaria) scores 0.80." (The count is within the `agora` block: the 11 combinations with soybean in summer minus soybean in the second window.) Against the current rotation the second-season income gain is small (BRL 40/ha with the soybean bonus: −200 for the brachiaria + 240 of extra bonus), so soil and pests carry the difference.

**Corn sowing-date trade-off (off-season corn)**

| Sowing | Frost | Water | Risk criterion |
|---|---|---|---|
| 01/02 | 12% | 0.86 | 0.80 |
| 15/03 | 76% | 0.97 | 0.24 |

Sowing late gives more water and much more frost. That is why off-season corn drops from 0.747 to 0.665 on 15/03 and the cover crops take the top.

**Margins (PAM Toledo 2016–2025, SEAB prices, CONAB COE cost)**

| Crop | Expected yield, trend (bags/ha) | 10-year mean (bags/ha) | Price (BRL/bag) | Cost (BRL/ha) | Margin (BRL/ha) |
|---|---|---|---|---|---|
| Soybean | 50 | 53 | 120.14 | 4,824 | +1,192 |
| 2nd-season corn | 117 | 101 | 53.89 | 4,678 | +1,641 |
| Wheat | 36 | 40 | 68.44 | 4,334 | −1,900 |

The expected yield is the 10-year trend projected to the next season (§6.3). In Toledo it raises corn (2023 and 2025 above 130 bags/ha) and lowers soybean (2019 and 2022 droughts). The cost column is the CONAB sheet before the adjustment to the local yield; the margins already include it.

**Track record (off-season corn, realized margin, soybean bags/ha):** 2021: −1, 2022: +12, 2023: +11, 2024: +7, 2025: +23 (mean 10.4; enters the income score, §6.3).

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
- Historical frequency, not a forecast for a specific year. Assumes a stationary climate, and 34 years is a small sample. Out of sample, no weather model tested predicts which season off-season corn fails (`docs/validation.md` §6.1).
- The income score uses the 5-season track record for grain second crops: it carries the price, yield and cost risk of recent seasons, but a single extreme season (e.g. 2021) moves the mean by ~2 bags/ha; `incerteza` shows the range.
- POWER underestimates frost (~40%).
- The pedotransfer tends to underestimate the available water capacity in Latosols (the farmer's soil analysis solves this).
- Irrigation: the yield gain is not modeled (only water, risk and cost); net depth, no application losses.
- Soil analysis: the sample (default 0–20 cm) is taken as representative of the whole root profile.
- Machinery outsourcing, irrigation cost and market levels are estimates to be validated.
- The summer crop (soybean or summer corn) does not enter the water and climate-risk criteria; only the second window does.
- ZARC is a warning only (it does not change the score); the table covers Paraná, season 2025/2026, rainfed, and must be rebuilt every season.
- Stage durations and the catalog harvest dates are estimates, to be validated with Embrapa/an agronomist.
- **Known limitation (open decision): sowing date of the `proxima_safra` block.** The block uses the same second-window sowing date as `agora`, derived from the harvest of the *current* crop (e.g. 15/01 for soybean harvested ~02/01). Summer corn in the next season is harvested later (~05/02), so with that date summer corn followed by off-season corn, corn + brachiaria, millet/crotalaria, sorghum or beans is eliminated, and the block ends up with only wheat, oat, radish and fallow (the off-season crops all disappear). The alternative is to compute the next season's sowing with the typical summer-corn harvest, so those candidates can be evaluated; it has not been decided yet and the current behavior was left as is. Tracked in `docs/pendencias.md`.

**Next steps:** regional costs; validation with an agronomist; SMAP for the current season; PAM × climate regression in income.

## Current context (informational)

The `GET/POST /v1/contexto` endpoint (code in `src/field_shift/context/`) queries official sources about ongoing events at request time:
ENSO (NOAA CPC, with the historical frequency of dry spells and frost per ENSO phase in the field's cell), soil moisture
(NASA SMAP L4, with the climatology percentile), MJO (NOAA PSL) and pest outbreaks (IDR-PR soybean rust and ADAPAR/IDR-PR alerts
curated by hand). **None of this enters the scores**: the ranking is still computed only from the climatology (POWER 1991-2024), soil, terrain,
history and income described above. The texts attribute the information to the source ("NOAA indicates...", "IDR-PR reports...") and do not claim
a loss or a probability for the field; the per-phase history has ~10 years per phase and may be only sampling noise. Each source has a cache
and a fallback; if it fails, the block comes back as `{"disponivel": false, "motivo": ...}` and the rest continues.
