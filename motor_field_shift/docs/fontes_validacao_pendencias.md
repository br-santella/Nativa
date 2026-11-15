# Source check of the estimated values (15/11/2026)

What was looked up for each value that `docs/pendencias.md` listed as "validate with an agronomist/Embrapa", what changed in the
engine, and what is still an estimate.

**How reliable this is:** every item below comes from web-search result summaries; the original pages were **not opened and read**
(unlike `fontes_estado_area.md`, where only sources we opened count). Treat each line as a lead to confirm, not as a confirmed source.
Nothing here replaces an agronomist.

## Changed in the engine

| Value | Before | Now | Basis |
|---|---|---|---|
| Sorghum price (R$/sc) | 80% of DERAL corn = R$ 43.11 | **75% = R$ 40.42** | Ratio of the CONAB/MAPA minimum prices of the 2026/27 crop for Sudeste and Paraná: sorghum R$ 40.19 / corn R$ 53.58 = 75.0% ([A Crítica, price table](https://acritica.net/agro/governo-reajusta-precos-minimos-agricolas-safra-2026-2027/)). It is a minimum-price ratio, not a market one: still an estimate. There is no SEAB/DERAL or Cepea market series for grain sorghum in Paraná. |
| Bean price type | black beans, "validate the type" | black beans kept; the source text now says why | Black beans are about two thirds of the Paraná 2nd-season bean area ([Boca, citing Deral; undated](https://boca.com.br/agronegocio/feijao-do-parana-tem-queda-na-producao-para-a-segunda-safra)). Colored beans cost much more (Apucarana, week of 13/11/2026: colored R$ 360, black R$ 320; `data/ref/precos_nucleos_snapshot_2026-11-13.json`), so the margin is for black beans. |

## Checked, value kept (evidence collected)

| Value | Current | What the search found | Verdict |
|---|---|---|---|
| Days per summer-corn stage (`crop_calendar.py`) | 110 / 80 / 60 / 40 / 15 days to harvest | Embrapa Milho e Sorgo: a normal-cycle hybrid flowers ~65 days after emergence; dry matter stops flowing to the grain 50–60 days after R1 ([Embrapa Circular 76](https://www.infoteca.cnptia.embrapa.br/bitstream/doc/490408/1/Circ76.pdf), plus extension material). Stage length depends on heat units, not fixed days. | **Consistent** (R1 → harvest ≈ 80 days). Still approximate by hybrid and year. Soybean stage days not checked. |
| Nabo forrageiro cost R$ 275/ha | estimate (range 200–350) | Seed ads: R$ 2.50–7.00/kg (R$ 7.00 in Assis Chateaubriand-PR); a supplier gives 10–12 kg/ha in a mix ([MF Rural](https://www.mfrural.com.br/busca/semente-nabo)). Seed alone is ~R$ 40–105/ha at 15 kg/ha. | **Probably high.** The seed part is well below what the estimate implies; the sowing operation is the unknown. Classified ads, several years old, no operation cost. Not changed: no source for the operation part. |
| Aveia + nabo R$ 400/ha | estimate (350–450) | Black oat seed ads: R$ 1.80–3.50/kg; no pure-oat sowing rate found. | **Not confirmed**, same limitation. |
| Limestone R$ 220/t (applied) | estimate | Quarry-gate ads in Paraná from R$ 80–90/t ([MF Rural](https://www.mfrural.com.br/busca/calcarios-calcario/estado/parana)); freight "up to R$ 100/t in the interior" in a 2011 state document ([AEN](https://arquivo2011.aen.pr.gov.br/sites/default/arquivos_restritos/files/documento/migrados/2809_calcario_e.doc)); spreading not found. | **Plausible** (R$ 80–90 + R$ 40–100 freight + spreading ≈ R$ 150–230/t) but no regional price series. Kept. |
| Fertilizer prices (SSP R$ 2,104.7/t, KCl R$ 2,898.8/t, 19/09/2025) | Campo Futuro, MT+PR average | No 2026 Campo Futuro quote found. One article says KCl ~20 soybean bags/t in early September 2026, "best ratio in three years" ([Agroadvance](https://agroadvance.com.br/blog-safra-26-27-produtividade-ou-reduzir-custo/)); another says SSP traded at R$ 450–470/t, which does not match our R$ 2,104/t and is not a Campo Futuro figure (unit or product unclear). | **Not updated.** The 2025 quote is the last sourced one; the 2026 signals are inconsistent. |
| P2O5/K2O doses for beans | estimate (Manual PR classes scaled) | Only trial papers (a Ponta Grossa trial used 20-60-30 N-P2O5-K2O, from the 1994 RS/SC manual, which is not a current recommendation). The Manual PR / Embrapa Arroz e Feijão tables did not show up. | **Not confirmed.** Needs the Manual PR (opened). |
| P2O5/K2O doses for sorghum | estimate | Embrapa trial doses (0/50/100 kg P2O5; 60 + 60 K2O); no class table found. | **Not confirmed.** Needs *Cultivo do Sorgo* (Embrapa Milho e Sorgo) or the Manual PR. |

## Evidence that questions a current value (not changed)

**Soybean harvest date 10/01 (`crop_calendar.py`, used when the farmer gives no stage or expected date).** Deral harvest progress for Paraná as a whole:

| Date | 2025/26 | 2025 (same date) | 2024 |
|---|---|---|---|
| 03/02 | 14% | 23% | |
| 10/02 | 20% | 33% | |
| 23/02 | 37% | | 52% (equivalent date) |

Sources: [Notícias Agrícolas 37%](https://www.noticiasagricolas.com.br/noticias/soja/415980-colheita-de-soja-do-parana-avanca-para-37-da-area-mas-mantem-atraso-aponta-deral.html), [Reuters/Investing 20%](https://br.investing.com/news/commodities-news/colheita-de-soja-do-parana-atinge-20-da-area-aponta-deral-1830457), [Deral bulletin week 09/2026](https://www.agricultura.pr.gov.br/sites/default/arquivos_restritos/files/documento/2026-02/boletim_semana_09_2026.pdf).

So 10/01 is the **start** of the harvest, not a typical date: the statewide median falls in mid/late February (2025/26 was a late year; a normal one had a third harvested on 10/02). The Oeste harvests earlier than the state average, but no Oeste-only series was found. With the default 10/01 the engine lets off-season corn be sown on 15/01–01/02 in rotations where a typical field would not be harvested yet. The summer-corn date (05/02) was not checked.
Recommendation (needs a decision, it moves the default ranking): ask the farmer for the stage/expected harvest (already supported) and, for the default, use a date from the Deral nucleus bulletins for Toledo/Cascavel instead of 10/01. Also, sowing soybean on 15/10 with a 105–125 day cycle gives a harvest between roughly 28/01 and 17/02, not 10/01 (our arithmetic, not a source).

## Not researched here

- **Catalog bonuses and penalties** (`bonus_sc`, criteria deltas, ±0.15 of `problemas_area`): these are modelling choices. The way to replace them is the literature survey already started in `pesquisa_ganho_soja_seguinte.md`, which is still paused.
- **Sorghum cost** (R$ 2,807/ha, CONAB Rio Verde-GO): no Paraná sheet exists; nothing new found.
