# Field Shift: open items

Date: 15/11/2026

This file is the living list of open items for the project (crop-rotation engine, Western Paraná). Each item has a status.

## Open decisions

- **Sowing date of the `proxima_safra` block**: the block currently uses the same second-season sowing date as the `agora` block, which eliminates summer corn and off-season crops. The alternative is to compute it with the typical summer-corn sowing date.
  Files: `src/field_shift/motor/servico.py`, `src/field_shift/calendario.py`.
  Status: pending

- **Bean price**: confirm whether the price should be the one for black beans (as it is now) or for colored beans.
  Files: `data/ref/precos_custos.json`, `src/field_shift/renda/`.
  Done (15/11/2026): black beans kept (about two thirds of the Paraná 2nd-season area, Deral via Boca, undated); the price source text now says the margin is for black beans and that colored beans pay much more. See [`fontes_validacao_pendencias.md`](fontes_validacao_pendencias.md).
  Status: done

- **Summer harvest dates**: validate the current estimates with an agronomist/Embrapa (soybean on 10/01, summer corn on 05/02).
  Files: `src/field_shift/calendario.py`.
  Evidence (15/11/2026, [`fontes_validacao_pendencias.md`](fontes_validacao_pendencias.md)): Deral statewide soybean harvest was at 14% on 03/02, 20% on 10/02 and 37% on 23/02 in 2025/26 (23% on 03/02 and 33% on 10/02 in 2025), so 10/01 is the start of the harvest, not a typical date; the Oeste is earlier than the state but no Oeste-only series was found. Soybean sown on 15/10 with a 105–125 day cycle is harvested between ~28/01 and ~17/02. Summer corn (05/02) not checked.
  Needs a decision, because it changes the default ranking: use a date from the Deral Toledo/Cascavel nucleus bulletins instead of 10/01. The farmer's stage/expected date already overrides it.
  Status: pending

- **Days per summer-corn stage**: validate with an agronomist/Embrapa the estimated length of each stage.
  Files: `src/field_shift/calendario.py`.
  Checked (15/11/2026, [`fontes_validacao_pendencias.md`](fontes_validacao_pendencias.md)): consistent with Embrapa Milho e Sorgo (flowering ~65 days after emergence; 50–60 days from R1 to the end of dry-matter accumulation), so R1 → harvest ≈ 80 days matches. Stage length depends on heat units, so it stays approximate by hybrid and year; the soybean stage days were not checked.
  Status: partly validated

- **Sorghum price and cost**: estimated values, no confirmed source; validate with an agronomist/Embrapa.
  Files: `data/ref/precos_custos.json`.
  Done in part (15/11/2026, [`fontes_validacao_pendencias.md`](fontes_validacao_pendencias.md)): the price ratio to corn went from 80% to 75% (R$ 43.11 → R$ 40.42/sc), taken from the CONAB/MAPA 2026/27 minimum prices for Sudeste and Paraná (sorghum R$ 40.19 / corn R$ 53.58); it is a minimum-price ratio, not a market one, and there is no SEAB/Cepea market series. The cost (CONAB Rio Verde-GO, R$ 2,807/ha) has no Paraná sheet: nothing new found.
  Status: pending (price better sourced, still an estimate; cost unchanged)

- **Cost of forage radish and the oat + radish mix**: estimated values, no confirmed source; validate with an agronomist/Embrapa.
  Files: `data/ref/precos_custos.json`.
  Evidence (15/11/2026, [`fontes_validacao_pendencias.md`](fontes_validacao_pendencias.md)): radish seed ads at R$ 2.50–7.00/kg and 10–12 kg/ha in a mix put the seed at ~R$ 40–105/ha, well below the R$ 275/ha estimate; the sowing operation is the unknown. Values not changed (classified ads, no operation cost). The R$ 275 and R$ 400 are probably high.
  Status: pending

- **Catalog bonuses and penalties**: the per-crop adjustments are estimates; validate with an agronomist/Embrapa.
  Not researched (15/11/2026, [`fontes_validacao_pendencias.md`](fontes_validacao_pendencias.md)): they are modelling choices; replacing them is the literature survey in `pesquisa_ganho_soja_seguinte_PARCIAL.md`, still paused.
  Status: pending

## Engine fixes

- **Unrealistic summer-corn cost**: the CONAB cost for first-season corn in Paraná only exists for Ponta Grossa and was computed for 12 t/ha, while Toledo produces about 7.6 t/ha. The result is a margin of roughly −BRL 4,600/ha in the `proxima_safra` block. Proposed fix: scale the variable cost to the local yield (cost/t × municipal yield).
  Files: `src/field_shift/renda/renda.py`, `src/field_shift/renda/atualizar.py`, `data/ref/precos_custos.json`.
  Done (15/11/2026): the CONAB sheet is split into yield-driven lines (fertilizer 3,249.90 + external transport 606.00 + storage 610.58 + CESSR 164.52 = R$ 4,631/ha) and fixed lines (seed, pesticides, machinery, labour, administration, technical assistance, interest). The yield-driven part is multiplied by local yield / reference yield (200 sc/ha); the block is stored as `escala_produtividade` in `precos_custos.json` (extracted by `atualizar.yield_scaling`). Toledo (141.5 sc/ha, factor 0.71): variable cost R$ 9,656 → R$ 8,302, summer-corn margin −R$ 2,030 → −R$ 676/ha. A bad year keeps the scaled cost (inputs are already spent); a farmer-typed cost is never scaled; the cost source text says the adjustment was applied. Tests: `tests/test_renda_escala.py`.
  Depends on an agronomist: which lines really move with yield (premise: fertilizer follows the yield target; seed and pesticides do not) and whether municipal PAM yield (~142 sc/ha) is comparable to a high-technology 12 t/ha package. The margin is still negative at the 12-month average price (R$ 53.89/sc): the summer-corn rotation is not profitable at this yield and price, which is a result, not a bug.
  Status: done

- ~~**Soybean "bad year" higher than the average**~~ — fixed: mean, CV, trend and p20 all use the same 10-year window (`YIELD_WINDOW_YEARS` in `pam/produtividade.py`); regression test `test_p20_never_above_mean`.
  Files: `src/field_shift/pam/produtividade.py`.
  Status: pending

- **Running API out of date**: the uvicorn on port 8000 started at 19:41 on 14/11, without `--reload`, and serves the old code. It needs a restart. The response changes shape and `rotacao_atual` becomes required. Docs and examples already describe the new shape; the running process was not restarted by the docs task.
  Files: `api/field_shift_api/`.
  Status: pending

## Data/infra

- **Connect the API to the whole of Paraná**: the data is already downloaded in `data/**/*_pr` (about 2.0 GB). What remains is switching the region and the paths read by the clipping, climate, soil, yield and water-balance modules.
  Files: `src/field_shift/regiao/recorte.py`, `src/field_shift/clima/lookup.py`, `src/field_shift/solo/solo.py`, `src/field_shift/pam/produtividade.py`, `src/field_shift/agua/balanco.py`.
  Status: pending

- **Slope computed on the fly**: `slope_pct.tif` (1.15 GB) could be computed on demand from the elevation instead of being stored.
  Files: `data/**/slope_pct.tif`, `ingest/mapbiomas_relevo_oeste_pr.py`.
  Status: pending

- **Delete the raw POWER JSONs**: the files in `data/raw/clima_pr/power/` (1.2 GB) can be removed.
  Files: `data/raw/clima_pr/power/`.
  Status: pending

- **Fate of `scripts/download_pr/`**: decide whether the folder stays in the repository.
  Files: `scripts/download_pr/`.
  Status: pending

- **MapBiomas Soil instead of SoilGrids**: a possible data improvement, using MapBiomas Soil (30 m) for texture and carbon.
  Files: `src/field_shift/solo/solo.py`, `ingest/solo_pam_oeste_pr.py`.
  Status: pending

## Documentation

- **Update docs and examples after the per-stage flow**: the code is done and the tests pass (`rotacao_atual` required, `estagio_verao`, `colheita_prevista`, `data_referencia`, `agora`/`proxima_safra` blocks and `ganho_vs_atual`). `api/README.md` and `docs/motor.md` were updated (inputs, outputs, stages, `data_referencia`, `agora`/`proxima_safra` blocks, `ganho_vs_atual`, open decision on the `proxima_safra` sowing date as a known limitation), and `api/exemplos/*.json` (including `opcoes.json` and the error examples) were regenerated from the real API. Main example: soybean at `enchimento_graos`, field 72638, `data_referencia` 2026-12-01.
  Files: `api/README.md`, `docs/motor.md`, `api/exemplos/*.json`.
  Status: done (15/11/2026)

- **Integrate the literature research numbers**: include the gain on the following soybean (range + source) in the documentation and in the engine, once the table is validated.
  Files: `docs/motor.md`, `docs/pesquisa_ganho_soja_seguinte_PARCIAL.md`.
  Status: pending

## Paraná-wide coverage

- **Ingest scripts of the `*_pr` data are not in the repo**: the engine now reads `data/raw/mapbiomas_pr`, `nasadem_pr`, `soilgrids_pr`, `regiao/{pr,municipios_pr}.geojson`, `clima_pr/` (raw), `processed/clima_pr/`, `processed/relevo_pr/` and `ibge/pam_pr.parquet` (399 municipalities), but `ingest/` only has the `*_oeste_pr` scripts. Confirm who generated the data, version the scripts, and document the commands.
  Files: `ingest/`, `api/README.md`.
  Done (15/11/2026): the pending note was outdated. The ingestion is versioned in `scripts/download_pr/01..06_*.sh` (added by Lucas in commit 65a69ac); each one calls `ingest/*.py --regiao pr`. Added `07_pam_extra.sh` (sorghum and beans PAM for all of Paraná) and put it in `run_all.sh`; `api/README.md` now maps every `*_pr` file to its script. Not re-run end to end here (POWER alone takes ~40 min); only `07_pam_extra` was run and checked.
  Status: done

- **SEAB/DERAL prices and costs by regional nucleus**: the values in `data/ref/precos_custos.json` are the Oeste/PR references. Outside the Oeste the response only warns (`avisos`) that they may differ; a per-nucleus table (SEAB/DERAL regional prices, CONAB sheet closest to the municipality) is missing.
  Files: `data/ref/precos_custos.json`, `src/field_shift/renda/`, `src/field_shift/motor/servico.py` (`AVISOS_FORA_DO_OESTE`).
  Assessed (15/11/2026), NOT implemented: SEAB/DERAL does publish a weekly price by regional nucleus (`prp.xls`), but only for the current week (no series), and the file has no municipality list. A snapshot of the week of 13/11/2026 is saved in `data/ref/precos_nucleos_snapshot_2026-11-13.json` only to measure the spread. Across 19 nuclei the standard deviation is 2.3% for soybean (R$ 131.82 Londrina to R$ 143.50 Guarapuava), 3.5% for corn (R$ 49.18 Irati to R$ 57.46 Pato Branco) and 3.7% for wheat (R$ 73.78 União da Vitória to R$ 87.20 Ponta Grossa); beans vary 14% but only 8 nuclei have a quote. Cascavel and Toledo (the Oeste) sit within 1.3% of the state average (soybean R$ 134.93 and R$ 134.80 against R$ 136.60). So the regional price effect is small next to the cost and yield effects, and a one-week snapshot would add noise.
  Why it stops here: applying it needs an official municipality → SEAB nucleus mapping (not found; guessing by distance to the seat city would invent a boundary) and a series longer than one week. On the cost side CONAB only publishes a few Paraná sheets (Londrina, Ponta Grossa, Francisco Beltrão; Cascavel stops in 2021), so "closest sheet" is a coarse proxy.
  To resume: get the nucleus → municipalities list from SEAB/DERAL, save the weekly `prp.xls` for 12 months (or use the monthly series by nucleus if it exists), and apply the ratio nucleus / state to the 12-month state average in `renda/`.
  Status: pending (assessed; low expected effect, ±2–4%)

- **ADAPAR calendar by region**: the soybean-free period (02/06–31/08) and sowing window (01/09–31/12) were researched for the Oeste. Elsewhere in Paraná they are kept and the response warns that the calendar may differ; check the current ADAPAR ordinance by region and the ZARC per municipality and make the rules region-dependent.
  Files: `src/field_shift/app/engine.py`, `src/field_shift/calendario.py`, `src/field_shift/motor/servico.py`.
  Done (15/11/2026): the rules are now regional. Portaria SDA/MAPA 1.579/2026 (crop 2026/2027) gives three Paraná windows: Região 1 (Sul, Leste, Campos Gerais, Litoral; 84 municipalities) void 21/06–19/09, sowing 20/09–20/01; Região 2 (Norte, Noroeste, Centro-Oeste, Oeste; 267) void 02/06–31/08, sowing 01/09–31/12; Região 3 (Sudoeste; 48) void 12/06–10/09, sowing 11/09–10/01. `ingest/vazio_sanitario_pr.py` reads the municipality lists from the portaria annex (all 399 IBGE municipalities matched, none duplicated) into `data/ref/vazio_sanitario_pr.json`; `regiao/vazio_sanitario.py` looks the region up; `engine.checar_regras` and the elimination texts use it; outside the Oeste the warning now quotes the region and dates. The 50 Oeste municipalities are all Região 2, so the Oeste is unchanged. Tests: `tests/test_vazio_sanitario.py`.
  Still open: (1) the dates must be refreshed every April (new portaria); (2) the dates were confirmed on ADAPAR's own news page because the annex table is an image in the PDF; (3) the per-municipality ZARC sowing window (credit/insurance) is still only a warning; (4) the seed-production extension (Portaria ADAPAR 024/2026) applies to the 2025/26 crop only and is not modelled.
  Status: done

- **PAM for sorghum and 2nd-season beans in all of Paraná**: `pam_extra_oeste_pr.parquet` only covers the 50 Oeste municipalities; there is no `pam_extra_pr`. Outside the Oeste these crops use the Oeste average (listed in `_regionais`, source text "Oeste do PR (média...)"). Extend `ingest/pam_culturas_extra.py` to the 399 municipalities.
  Files: `ingest/pam_culturas_extra.py`, `src/field_shift/pam/produtividade.py`, `src/field_shift/renda/renda.py`.
  Done (15/11/2026): `uv run python ingest/pam_culturas_extra.py --regiao pr` writes `data/raw/ibge/pam_extra_pr.parquet` (399 municipalities, 119,700 rows, 1974–2025); `pam/produtividade.py` reads it in preference to the Oeste-only file. With the engine's own rule (≥ 3 years and last year ≥ 2018), 2nd-season beans now have a municipal series in 273 of 399 municipalities and sorghum in 42 (sorghum has few records in the PAM); the rest keep the Oeste average and the existing `_regionais` warning. Test: `tests/test_pam_extra.py`.
  Caution: small, atypical PAM series now override the regional average (e.g. Londrina beans: 9.4 sc/ha over 3 years); consider a minimum harvested area or a sanity band against the regional average.
  Status: done

## Future features

- **Multi-year rotation plan**: the ranking evaluates one season at a time. A 2–3 year plan is missing (for example, soybean/corn → soybean/wheat → summer corn/oat).
  Files: `src/field_shift/motor/`.
  Status: pending. An untested draft (`motor/plano.py`, `POST /v1/plano`) lives only on the local branch `feat/motor-estado-area-plano-plurianual`; resume from there (needs tests, docs, new examples and the example generator).

- **Field problems reported by the farmer**: a closed-list field, for example `problemas_area: ["nematoide", "mofo_branco", "cigarrinha", "compactacao"]`, that adjusts the pest and soil criteria (white mold hurts beans; nematodes favor brachiaria and penalize beans and soybean; leafhopper weighs on corn after corn; compaction favors radish and brachiaria). Optional: if not provided, it does not enter the analysis.
  Files: `api/field_shift_api/schemas.py`, `src/field_shift/motor/servico.py`, `src/field_shift/app/estado_area.py`, `catalog/vocabulario.yaml`.
  Done: `problemas_area` (closed list validated in the API and the engine; unknown value is a 422/400) adjusts `pragas` and `solo` per crop through the explicit table `PROBLEM_EFFECTS` (additive deltas on the existing 0–1 scale). The card and `metodologia.ajustes_aplicados` say what was and was not considered.
  Sourced (15/11/2026, see [`fontes_estado_area.md`](fontes_estado_area.md)): the numeric deltas were replaced by three qualitative levels per (problem, crop), `favorece` / `neutro` / `penaliza`, with one declared magnitude (±0.15, our modelling choice, not from the literature). A cell is non-neutral only with a source we opened and read: white mold (beans, soybean, forage radish penalize: Brandão 2008, Ferro & Lobo Jr. 2010, Godoy 2017, Meyer & Bueno 2022), nematodes (beans and soybean penalize, crotalaria + millet favors: Inomoto & Asmus 2009, Mendes et al. 2012), leafhopper (corn on corn penalizes: Embrapa CT 226 and the CropLife/Embrapa guide) and compaction (corn + brachiaria, forage radish and millet + crotalaria favor: França et al. 2012, Torres et al.). The card shows the source and caveat of each applied effect.
  Plausible effect without source (neutral, flagged in the card): white mold x oat + radish mix; nematodes x corn, corn + brachiaria and forage radish (sources exist but depend on the nematode species, which the engine does not know; brachiaria and corn host *P. brachyurus* but not the others); leafhopper x a single corn crop; compaction x oat + radish mix (tested, no gain).
  Depends on an agronomist: whether a nematode-species field (e.g. `P. brachyurus`, `M. javanica`) should be added to the vocabulary so corn/brachiaria/radish can leave neutral; the magnitude ±0.15; whether nematode and white-mold evidence from Goiás and Mato Grosso transfers to Western Paraná; the 2012 trials are about *B. ruziziensis* (other brachiaria species not tested). The effect of the summer crop (soybean) hits all rotations of the block equally.
  Status: done

- **Fertility/minerals in `analise_solo`**: extend it with P, K, Ca, Mg, Al, base saturation (V%) and CEC, as optional farmer input. Uses: fertilizer and liming cost per crop, a penalty for demanding crops on poor or acidic soil, and a bonus for nutrient-cycling cover crops. If not provided, fertility does not enter the analysis, with no estimate or default value, and the card says it was not considered. Implement together with `problemas_area`.
  Files: `api/field_shift_api/schemas.py`, `src/field_shift/motor/servico.py`, `src/field_shift/app/estado_area.py`.
  Done: `analise_solo` accepts `p_mg_dm3`, `k_cmolc_dm3`, `ca_cmolc_dm3`, `mg_cmolc_dm3`, `al_cmolc_dm3`, `v_pct`, `ctc_cmolc_dm3` (any subset; `analise_solo` may now carry only fertility). Not informed: nothing is estimated and the card says "Fertilidade não considerada (não informada)". Informed: liming cost by base saturation (NC = (V2 − V1)/100 × CTC / PRNT, in t/ha, cap 6 t/ha, diluted over 3 years; needs V% and CTC, V% is derived only from Ca+Mg+K+CTC), P/K fertilizer cost above/below the average-class dose already in the CONAB cost (saving on rich soil), a penalty on `solo` for acid-sensitive crops (high Al, low V%), and a bonus on `solo` for radish/brachiaria (low P or K) and crotalaria (poor soil). `POST /v1/diagnostico` also returns a `fertilidade` block with the classes.
  Sourced (15/11/2026, see [`fontes_estado_area.md`](fontes_estado_area.md); the Manual PR itself could not be opened, its tables are confirmed through SENAR-AR/PR booklets and a UEPG thesis that reproduce them): P classes by clay band (< 250, 250–400, > 400 g/kg, with "condição a evitar"), K (5 classes), V% and Al classes; clay comes from the farmer's `argila_pct`, without it the most demanding band is used and the card says so; liming formula NC = (V2 − V1) × CEC / PRNT (cmolc/dm3, as the code already did); V2 = 60% (Manual PR class 51–70% for corn, wheat, beans, sorghum and soybean; soybean 60% and wheat 60% confirmed); reference PRNT 76.9% (CBPTT 2020, f = 1.3); corn P2O5/K2O doses by class (Manual PR 2017, expected yield < 8 t/ha, midpoints); wheat P2O5/K2O doses (CBPTT 2020, by soil value, midpoints); fertilizer prices (CNA/Cepea Campo Futuro, MT + PR average, 19/09/2025: SSP and KCl; grades 18% and 58% assumed). Acid-sensitivity factors are now equal for the five crops because the Manual groups them in one class.
  Still an estimate (no confirmed source, marked in the code and in the card): P2O5/K2O doses for beans and sorghum; agricultural limestone price (R$ 220/t; no public regional price found); the 6 t/ha cap per application; the 3-year dilution of liming (only a re-analysis interval was found); V2 for corn, beans and sorghum as a single number (only the 51–70% range is confirmed); the assumption that the CONAB cost embeds the "medium" class dose; the penalty and bonus sizes on `solo`.
  Depends on an agronomist: the expected-yield premise (< 8 t/ha for off-season corn in Western Paraná); whether to take V2 = 60% or 70% (Embrapa cites both for soybean); the "correct only when V < 50%" trigger (documented for soybean only, not applied); a regional lime and fertilizer price from a local cooperative/dealer; the Manual PR tables for soybean, beans and sorghum (open the book to replace the estimates and the CBPTT wheat tables); the 2026 fertilizer prices (the quote is from September 2025).
  Source check (15/11/2026, [`fontes_validacao_pendencias.md`](fontes_validacao_pendencias.md)): no 2026 Campo Futuro quote found and the 2026 signals are inconsistent, so the prices stay at September 2025; the R$ 220/t limestone is plausible (quarry R$ 80–90/t + freight + spreading) but has no regional series; the bean and sorghum P/K doses were not found (only trial papers).
  Status: done

- **Stale worked examples after the 10-year yield window**: the worked examples still quote the old scores and margins (0,814 / 0,757, S = R$ 1.083, incremental 1.033, renda 0,977, totals 2.116 / 2.076). Recompute them from the current `api/exemplos/` output.
  Files: `docs/motor.md` (~lines 245–295), `README.md` (root, lines 58–59), `api/README.md` (~line 466).
  Done (15/11/2026): `api/exemplos/*.json` regenerated from the real API with `scripts/generate_examples.py`; the tables of `docs/motor.md` section 8, the root README table and the `api/README.md` response excerpt were rebuilt from that output (field 72638, S = BRL 1,503; corn + brachiaria 0.764 first, current off-season corn 0.709 in 4th). Also fixed the `erro_fora_da_regiao` example: it pointed at Curitiba, which is now inside the covered area and returned 200; it now uses São Paulo (422), and `recomendacao_ponto_curitiba` shows the Região 1 calendar.
  Status: done

- **Summer corn cost reference does not match local yield**: `milho_1safra` uses the CONAB Ponta Grossa cost (R$ 9.656/ha, reference 12 t/ha ≈ 200 sc/ha) against the PAM municipal yield (~140 sc/ha in Toledo); break-even is ~179 sc/ha, so every `milho_verao__*` candidate shows a large negative margin. Options: scale the variable cost by local/reference yield, or add an explicit card warning.
  Files: `data/ref/precos_custos.json`, `src/field_shift/renda/renda.py`.
  Done (15/11/2026): same fix as "Unrealistic summer-corn cost" above (yield-driven lines scaled, card source text flags it as an estimate to validate).
  Status: done

- **Fertility cost only charged on grain second crops**: liming and extra P/K enter only when the 2nd crop is a grain (`V2 = None` for cover crops/fallow), so with fertility informed cover crops gain ~R$ 550/ha in the comparison, and the summer crop (soy vs. summer corn in `proxima_safra`) never carries it. Liming is an area-level need; decide (agronomist) whether it applies to every rotation.
  Files: `src/field_shift/app/estado_area.py`.
  Done (15/11/2026), conservative option: liming is now charged to every candidate, including covers and fallow, with the same V2 (`V2_AREA` = 60%); P/K fertilizer stays on grain crops only (no dose model for covers). With the same liming on all candidates the ~R$ 550/ha advantage of covers is gone; absolute scores drop when fertility is informed, the relative order is what matters. The card says liming is an area-level need charged to covers too. The summer crop still does not carry it, which is neutral inside a block (soybean and summer corn share the same V2). Tests: `test_liming_formula_and_reference_prnt`, `test_corn_wheat_and_unsourced_fertilizer_costs`, `test_poor_and_acid_fertility`.
  Depends on an agronomist: confirm that liming should be charged to every rotation (and not only to the crop that "needs" it), and the V2 used for covers.
  Status: done

## Research

- **Resume the literature research on the gain on the following soybean**: the survey is paused and the partial results are in [`pesquisa_ganho_soja_seguinte_PARCIAL.md`](pesquisa_ganho_soja_seguinte_PARCIAL.md), with a table of open sources and the "still to research" section. Resume from there (Embrapa Soja, IDR-PR, Fundação ABC) for off-season corn, corn+brachiaria, wheat, oat, millet/crotalaria, sorghum, beans, radish, oat+radish and summer corn, plus corn after corn, beans/white mold, brachiaria/nematodes and NDVI × yield.
  Files: `docs/pesquisa_ganho_soja_seguinte_PARCIAL.md`.
  Status: pending
