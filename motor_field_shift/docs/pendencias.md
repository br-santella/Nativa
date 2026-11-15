# Field Shift: open items

Date: 14/11/2026

This file is the living list of open items for the project (crop-rotation engine, Western Paraná). Each item has a status.

## Open decisions

- **Sowing date of the `proxima_safra` block**: the block currently uses the same second-season sowing date as the `agora` block, which eliminates summer corn and off-season crops. The alternative is to compute it with the typical summer-corn sowing date.
  Files: `src/field_shift/motor/servico.py`, `src/field_shift/calendario.py`.
  Status: pending

- **Bean price**: confirm whether the price should be the one for black beans (as it is now) or for colored beans.
  Files: `data/ref/precos_custos.json`, `src/field_shift/renda/`.
  Status: pending

- **Summer harvest dates**: validate the current estimates with an agronomist/Embrapa (soybean on 10/01, summer corn on 05/02).
  Files: `src/field_shift/calendario.py`.
  Status: pending

- **Days per summer-corn stage**: validate with an agronomist/Embrapa the estimated length of each stage.
  Files: `src/field_shift/calendario.py`.
  Status: pending

- **Sorghum price and cost**: estimated values, no confirmed source; validate with an agronomist/Embrapa.
  Files: `data/ref/precos_custos.json`.
  Status: pending

- **Cost of forage radish and the oat + radish mix**: estimated values, no confirmed source; validate with an agronomist/Embrapa.
  Files: `data/ref/precos_custos.json`.
  Status: pending

- **Catalog bonuses and penalties**: the per-crop adjustments are estimates; validate with an agronomist/Embrapa.
  Status: pending

## Engine fixes

- **Unrealistic summer-corn cost**: the CONAB cost for first-season corn in Paraná only exists for Ponta Grossa and was computed for 12 t/ha, while Toledo produces about 7.6 t/ha. The result is a margin of roughly −BRL 4,600/ha in the `proxima_safra` block. Proposed fix: scale the variable cost to the local yield (cost/t × municipal yield).
  Files: `src/field_shift/renda/renda.py`, `src/field_shift/renda/atualizar.py`, `data/ref/precos_custos.json`.
  Status: pending

- **Soybean "bad year" higher than the average**: the average uses 2021–2025 (49 bags/ha) and p20 uses 10 years (51 bags/ha). The year windows need to be aligned.
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

## Future features

- **Multi-year rotation plan**: the ranking evaluates one season at a time. A 2–3 year plan is missing (for example, soybean/corn → soybean/wheat → summer corn/oat).
  Files: `src/field_shift/motor/`.
  Status: pending. An untested draft (`motor/plano.py`, `POST /v1/plano`) lives only on the local branch `feat/motor-estado-area-plano-plurianual`; resume from there (needs tests, docs, new examples and the example generator).

- **Field problems reported by the farmer**: a closed-list field, for example `problemas_area: ["nematoide", "mofo_branco", "cigarrinha", "compactacao"]`, that adjusts the pest and soil criteria (white mold hurts beans; nematodes favor brachiaria and penalize beans and soybean; leafhopper weighs on corn after corn; compaction favors radish and brachiaria). Optional: if not provided, it does not enter the analysis.
  Files: `api/field_shift_api/schemas.py`, `src/field_shift/motor/servico.py`, `src/field_shift/app/estado_area.py`, `catalog/vocabulario.yaml`.
  Done: `problemas_area` (closed list validated in the API and the engine; unknown value is a 422/400) adjusts `pragas` and `solo` per crop through the explicit table `EFEITOS_PROBLEMAS` (additive deltas on the existing 0–1 scale). The card and `metodologia.ajustes_aplicados` say what was and was not considered.
  To validate with an agronomist/Embrapa: every delta in `EFEITOS_PROBLEMAS` is a catalog estimate (e.g. white mold −0.25 beans, −0.15 soybean and radish; nematodes +0.25 crotalaria/millet, +0.10 brachiaria, −0.25 beans, −0.15 soybean; leafhopper −0.05 corn and −0.15 extra on corn after corn; compaction +0.15 radish and brachiaria). Brachiaria and millet effects on nematodes depend on species/cultivar; the effect of the summer crop (soybean) hits all rotations of the block equally.
  Status: done

- **Fertility/minerals in `analise_solo`**: extend it with P, K, Ca, Mg, Al, base saturation (V%) and CEC, as optional farmer input. Uses: fertilizer and liming cost per crop, a penalty for demanding crops on poor or acidic soil, and a bonus for nutrient-cycling cover crops. If not provided, fertility does not enter the analysis, with no estimate or default value, and the card says it was not considered. Implement together with `problemas_area`.
  Files: `api/field_shift_api/schemas.py`, `src/field_shift/motor/servico.py`, `src/field_shift/app/estado_area.py`.
  Done: `analise_solo` accepts `p_mg_dm3`, `k_cmolc_dm3`, `ca_cmolc_dm3`, `mg_cmolc_dm3`, `al_cmolc_dm3`, `v_pct`, `ctc_cmolc_dm3` (any subset; `analise_solo` may now carry only fertility). Not informed: nothing is estimated and the card says "Fertilidade não considerada (não informada)". Informed: liming cost by base saturation (NC = (V2 − V1)/100 × CTC / PRNT, in t/ha, cap 6 t/ha, diluted over 3 years; needs V% and CTC, V% is derived only from Ca+Mg+K+CTC), P/K fertilizer cost above/below the average-class dose already in the CONAB cost (saving on rich soil), a penalty on `solo` for acid-sensitive crops (high Al, low V%), and a bonus on `solo` for radish/brachiaria (low P or K) and crotalaria (poor soil). `POST /v1/diagnostico` also returns a `fertilidade` block with the classes.
  To validate with an agronomist/Embrapa/IDR-PR: P classes (single scale; the Paraná manual varies by clay), K/V%/Al class limits (simplified), V2 per crop (70% corn, wheat, beans; 60% sorghum), PRNT 80%, lime price R$ 220/t, 3-year lime life, 6 t/ha cap, P2O5/K2O doses by class and prices (R$ 7.5 and 4.6/kg), crop demand and acid-sensitivity factors, and the penalty/bonus sizes. The summer crop's own liming/fertilizing is not modeled (equal across rotations of the block). The "/10" in the original liming formula only holds with CEC in mmolc/dm³; the code uses CEC in cmolc/dm³ (1 cmolc/dm³ = 1 t of CaCO3/ha in 0–20 cm).
  Status: done

## Research

- **Resume the literature research on the gain on the following soybean**: the survey is paused and the partial results are in [`pesquisa_ganho_soja_seguinte_PARCIAL.md`](pesquisa_ganho_soja_seguinte_PARCIAL.md), with a table of open sources and the "still to research" section. Resume from there (Embrapa Soja, IDR-PR, Fundação ABC) for off-season corn, corn+brachiaria, wheat, oat, millet/crotalaria, sorghum, beans, radish, oat+radish and summer corn, plus corn after corn, beans/white mold, brachiaria/nematodes and NDVI × yield.
  Files: `docs/pesquisa_ganho_soja_seguinte_PARCIAL.md`.
  Status: pending
