# Gain on the following soybean by second-window crop (`bonus_sc`)

> Status: **done for the MVP** (15/11/2026); the values in §0 are in the engine catalog (`SECOND`/`SUMMER` in `src/field_shift/app/engine.py`, fields `bonus_sc`, `bonus_sc_faixa`, `bonus_fonte`). Only numbers from sources that were opened and read are used. Started 14/11 (partial), finished 15/11 with the Palotina 2022/23 trial (Western PR).
> Conversion used: 1 bag (sc) = 60 kg. Difference in kg/ha ÷ 60 = bags/ha.

## Important note on the comparison baseline

In the Embrapa trials in Paraná, the baseline is almost always the **soybean/off-season corn (2nd season) succession**, not fallow. Only two of the papers read use fallow as the baseline (Yokoyama et al. 2022 and the abstract Ramos et al. 2025, both from the same trial in Londrina). In that trial, soybean after off-season corn yielded **the same or less** than soybean after fallow in 2 of 3 seasons. That is why the "baseline" column in the table below says what each number was measured against. If the engine keeps using fallow = 0, it is reasonable to treat off-season corn ≈ 0 and add the gains measured "vs off-season corn" directly.

## 0. Values adopted in the engine (baseline = fallow, bags/ha)

Off-season corn ≈ fallow (§2), so gains measured "vs off-season corn" were added to the corn value (+1). The range is what the trials showed, used for the worst/best case in `ganho_vs_atual.soja_seguinte_sc_faixa` and shown on the card.

| Crop | Before | Now | Range | Main evidence |
|---|---|---|---|---|
| Off-season corn | 1 | **1** | −3 to +3.5 | Londrina 2016–2025 (≈ fallow on average), Palotina 2022/23 (+1.4, ns) |
| Corn + brachiaria | 3 | **5** | +1 to +9 | Doc. 459 Cafelândia (+6.9 over corn, 3 seasons); Palotina (+0.9 over corn, ns) |
| Wheat | 1 | **3** | 0 to +6.5 | Docs. 459/476, Garbelini 2022, Palotina (−0.6 to +5.5 over corn) |
| Oat | 2 | **3** | +1 to +8 | Doc. 459 (+6.9 over corn, 1 trial); Palotina winter mix (+1.1) |
| Millet + crotalaria | 3 | **2** | 0 to +5 | no trial of the mix in Western PR; Londrina millet+crotalaria and sole crotalaria: no effect (lowered) |
| Grain sorghum | 1 | **1** | −2 to +2 | Palotina: soybean after sorghum = after corn |
| Off-season beans | 0 | **−1** | −8 to +1.5 | cowpea proxy, Doc. 476 (nematodes, soil fungi) |
| Forage radish | 2 | **2** | 0 to +4 | no isolated trial; Palotina winter mix +1.1 over corn |
| Oat + radish | 2.5 | **2.5** | +1 to +6 | Palotina mix (+1.1) and Doc. 459 oat (+6.9) |
| Fallow | 0 | 0 | — | baseline |
| Summer corn (extra, in place of soybean) | 3 | **3** | 0 to +4.5 | Garbelini 2022 (system with radish, effects not separated) |

**Palotina 2022/23** (Pivetta et al. 2026, Embrapa, very clayey eutroferric Red Latosol, Western PR, 1 season; soybean kg/ha): fallow 3,087; fallow/wheat 3,134; millet/wheat 3,233; sorghum 3,127; sole corn 3,169; corn + ruziziensis 3,221; corn + winter mix 3,234; sole ruziziensis 3,593; ruziziensis + crotalarias 3,758 (only the two brachiaria covers differ statistically from fallow). Source: PIVETTA, L. A. et al. Efeito da diversificação de culturas na produtividade da soja na região Oeste do Paraná. In: 40ª Reunião de Pesquisa de Soja, Londrina, 2026, p. 72–76. https://www.alice.cnptia.embrapa.br/alice/bitstream/doc/1188274/1/p-72-ETC-7-RPSoja-2026-2.pdf

**Millet + crotalaria, Londrina** (Embrapa Soja, R.156): five treatments (sole C. spectabilis, sole C. ochroleuca, millet, millet + each crotalaria); "soybean yield was not significantly affected by the treatments" (low-yield year, mean 1.71 Mg/ha). https://www.alice.cnptia.embrapa.br/alice/bitstream/doc/1018473/1/R.156INSERCAODASCROTALARIASEDOMILHETOEMSISTEMASDE.PDF

**7-year Londrina trial (not opened, snippet only):** Charnobay et al. 2025 (Applied Soil Ecology 209, 106040): ruzigrass 4,119 vs fallow 3,525 kg/ha/yr (+9.9 bags); Balbinot Junior et al. 2023 (IJPP 18): ruzigrass 4,354, wheat 4,304, corn with N 4,058, corn without N 3,942, fallow 3,843. Consistent with the values adopted (corn slightly above fallow, wheat and brachiaria clearly above), but not used as a number until the full text is read.

**What this does not validate.** The PAM has no preceding-crop field, so the bonus cannot be checked against observed municipal yields; these are trial results (few sites, few seasons). The range on the card states that.

## 1. Table (open sources only)

| Crop after soybean | Baseline | Range bags/ha (per season) | Suggested central value | Confidence | Source(s) |
|---|---|---|---|---|---|
| Off-season corn | fallow | −4.2 to +6.8 (2-season average: −3.1 to −1.4) | **0** (currently: +1) | low-medium (1 trial, Londrina) | Yokoyama et al. 2022; Ramos et al. 2025 |
| Off-season corn + brachiaria ruziziensis | off-season corn | +5.3 to +8.1 (3-season average: +6.9) | **+5** (currently: +3) | medium (1 trial in Western PR + Londrina in the same direction) | Debiasi et al. 2023 (Doc. 459) |
| (sole ruziziensis as cover, reference) | fallow | +0.4 to +11.7; +5.4 in the 8th season | (reference) | medium | Yokoyama et al. 2022; Ramos et al. 2025 |
| Wheat | off-season corn | −2.4 to +10.4 (trial averages: +0.7; +2.0; +5.5) | **+3** (currently: +1) | medium (3 trials in PR) | Doc. 459; Doc. 476; Garbelini et al. 2022 |
| Wheat | fallow | +1.4 to +12.4 | (reference) | medium | Yokoyama et al. 2022; Ramos et al. 2025 |
| Oat (black/white) | off-season corn | +3.6 to +12.8 (3-season average: +6.9); corn + black oat in the 3rd season: +5.6 average | **+4** (currently: +2) | low-medium (1 trial) | Doc. 459 (MP3 and MP6) |
| Millet + crotalaria | fallow/corn | no effect (Londrina, R.156); millet/wheat +1.1 over corn (Palotina) | **+2** (was +3) | low | R.156; Palotina 2022/23; Yokoyama 2022 |
| Off-season grain sorghum | off-season corn | −0.7 (ns) | **= corn (+1)** | low (1 season) | Palotina 2022/23 |
| Off-season beans | off-season corn (proxy: cowpea) | −8.8 to +0.8 (cowpea) | **≤ 0**; −2 if the proxy is used | low (different species) | Doc. 476 (MP4 cowpea) |
| Forage radish alone | — | **pending** | pending | — | only appears within the rotated system of Garbelini 2022 |
| Oat + radish mix | — | **pending** | pending | — | same |
| Fallow | — | 0 (baseline) | 0 | — | — |
| Summer corn instead of soybean for 1 year | off-season corn (succession) | 0 to +4.5 (complete rotated system, not isolated) | pending (the current +3 is plausible, but has no isolated source) | low | Garbelini et al. 2022 |

## 2. Evidence by crop

**Off-season corn (vs fallow).** Trial in Londrina (dystroferric Red Latosol, no-till for 15 years, Cfa climate), the same plots since 2016. Soybean after corn without N / corn with 80 kg of N / fallow:
- 2016/17: 4,223 / 4,345 / 4,476 kg/ha, difference not significant;
- 2017/18: 4,346 / 4,430 / 4,467 kg/ha, no significant difference between corn and fallow (Yokoyama et al. 2022);
- 2024/25 (8th season, a water-deficit year): corn 3,493, fallow 3,083 kg/ha (+6.8 bags), but corn ("ab") does not differ from fallow ("b") (Ramos et al. 2025).

Conclusion: off-season corn brings no consistent gain over fallow. Whether the effect is immediate or cumulative remains undefined.

**Corn + brachiaria ruziziensis.** Doc. 459 (Embrapa Soja), Copacol Research Center, Cafelândia/PR (Western PR, Cfa, very clayey Latosol), 3 seasons (2020/21 to 2022/23). Soybean in MP4 (corn + ruziziensis) vs MP1 (off-season corn):
- 2020/21: 5,447 vs 5,012 kg/ha;
- 2021/22, drought: 1,413 vs 925 kg/ha (+53%);
- 2022/23: 4,468 vs 4,153 kg/ha;
- cumulative: 11,328 vs 10,090 kg/ha (+12.3%).

The effect already appears in the 1st year and is larger in a dry year, because the straw and roots improve water retention. The +53% comes from an extreme year and should not be used as an average. In Londrina, sole ruziziensis only beat fallow in the 2nd year (5,171 vs 4,467 kg/ha in 2017/18; zero difference in 2016/17). The authors call this a "cumulative effect" (Yokoyama 2022).

**Wheat.**
- Doc. 459, Western PR, vs off-season corn: +284, +85 and +623 kg/ha (cumulative 11,082 vs 10,090).
- Doc. 476 (northern PR, 2021/22 to 2023/24): +86 (ns), +417 (sig.) and −142 (ns) kg/ha.
- Garbelini et al. 2022 (Londrina, 8 seasons, 2009–2017): wheat-soybean 3,940 vs corn-soybean 3,900 kg/ha, no significant difference.
- Vs fallow (Londrina): +84 (ns) and +580 kg/ha (Yokoyama 2022); +743 kg/ha, significant (Ramos 2025).

Doc. 459 cites Balbinot Junior et al. (2024): 7 years in Londrina, soybean after wheat about 10% above soybean after off-season corn. That paper has not been opened yet. The evidence converges on a positive gain, but moderate and variable between seasons.

**Oat.** Only Doc. 459. MP3 had white oat for grain in 2020/21 and black oat as cover in 2021/22 and 2022/23. Soybean: 5,230 / 1,174 / 4,920 vs 5,012 / 925 / 4,153 kg/ha for MP1 (cumulative +12.3%). MP6 (off-season corn followed by black oat in the 3rd season) had a cumulative 11,096 kg/ha.

**Beans (proxy: cowpea).** Doc. 476: soybean after cowpea–wheat yielded 3,292 / 3,474 / 2,250 kg/ha, against 3,817 / 3,784 / 2,202 after off-season corn. That is a 14–17% drop relative to the best treatments in the first two seasons. The authors' hypothesis: multiplication of nematodes (Meloidogyne, Rotylenchulus reniformis, Pratylenchus brachyurus) and soil fungi (Macrophomina, Sclerotium rolfsii). There is no data on common beans (Phaseolus) or on white mold.

**Grain millet (partial proxy for millet + crotalaria).** Doc. 476, MP5 (grain millet, then wheat, then soybean) vs off-season corn: −184 (ns), +471 (sig.) and +97 (ns) kg/ha.

**Sole Crotalaria spectabilis (vs fallow, Londrina).** −155 (ns) and +172 kg/ha (ns) (Yokoyama 2022). There is no direct data on the millet + crotalaria mix.

**Summer corn / diversified rotation.** Garbelini et al. 2022: no-till trial since 1985, Embrapa Soja, Londrina, two 4-year cycles (2009–2017). System I has summer corn every 3–4 years plus radish, oat and wheat in winter. Average soybean: about 4,170 kg/ha, +230 kg/ha over wheat-soybean and +270 kg/ha over corn-soybean (+6%). Systems II and III, also diversified, did not differ significantly (about 4,010–4,070 kg/ha, values read from the figure via OCR). The authors attribute the gain to the radish and to replacing soybean with summer corn, but do not separate the two effects.

## 3. References read (open access)

1. DEBIASI, H.; BALBINOT JUNIOR, A. A.; FRANCHINI, J. C.; TONINI, V.; ROY, J. M. T.; MUHL, A. *Modelos de produção intensificados para diversificação da matriz produtiva para além da sucessão milho 2ª safra/soja nas regiões centro-oeste e oeste do Paraná.* Londrina: Embrapa Soja, 2023 (Documentos 459). Type: 3-season experiment, Cafelândia/PR (Copacol). https://www.infoteca.cnptia.embrapa.br/infoteca/bitstream/doc/1160227/1/DOC-459.pdf
2. DEBIASI, H. et al. *Diversificação da sucessão milho segunda safra/soja por meio de modelos de produção intensificados envolvendo cultivo de trigo associado a culturas graníferas na janela outonal no norte paranaense.* Londrina: Embrapa Soja, 2025 (Documentos 476). Type: 3-season experiment, 2021/22 to 2023/24, northern PR. https://www.infoteca.cnptia.embrapa.br/infoteca/bitstream/doc/1178322/1/DOC-476-.pdf
3. GARBELINI, L. G.; DEBIASI, H.; BALBINOT JUNIOR, A. A.; FRANCHINI, J. C.; COELHO, A. E.; TELLES, T. S. Diversified crop rotations increase the yield and economic efficiency of grain production systems. *European Journal of Agronomy*, v. 137, 126528, 2022. Type: long-term trial (no-till since 1985), Embrapa Soja, Londrina, 8 seasons (2009–2017). PDF: https://www.alice.cnptia.embrapa.br/alice/bitstream/doc/1151570/1/Diversified-crop-rotations-increase-the-yield-and-economic-efficiency-of-grain-production-systems-Elsevier-Enhanced-Reader-ocred.pdf
4. YOKOYAMA, A. H.; ZUCARELI, C.; COELHO, A. E.; NOGUEIRA, M. A.; FRANCHINI, J. C.; DEBIASI, H.; BALBINOT JUNIOR, A. A. Precrops and N-fertilizer impacts on soybean performance in tropical regions of Brazil. *Acta Scientiarum. Agronomy*, v. 44, e54650, 2022. DOI 10.4025/actasciagron.v44i1.54650. Type: 2-season experiment (2016/17 and 2017/18), Londrina, fallow baseline. https://www.redalyc.org/journal/3030/303071489032/303071489032.pdf
5. RAMOS, A. M.; OLIVEIRA, S. M.; TIRELLI, L. A.; FRANCHINI, J. C.; DEBIASI, H.; OLIVEIRA, M. A.; BALBINOT JUNIOR, A. A. Culturas de outono/inverno e escarificação do solo influenciando a produtividade e as concentrações de proteína e óleo em grãos de soja. In: 44ª Reunião de Pesquisa de Soja da Região Sul, Passo Fundo, 2025, p. 299–303. Type: extended abstract, 8th season (2024/25) of the Londrina trial started in 2016. https://www.alice.cnptia.embrapa.br/alice/bitstream/doc/1183511/1/p-299-Atas-e-Resumos-2025-completo-6-1-2.pdf

## 4. What is MISSING (to resume)

**Sources identified but not opened (full text inaccessible or not read):**
- BALBINOT JUNIOR, A. A. et al. Effects of N-fertilization and off-season crops on soybean yield and grain protein and oil concentrations in a tropical climate. *Int. J. Plant Production* 18, 2023. DOI 10.1007/s42106-023-00273-0. This is the **7-year trial in Londrina**, with a fallow baseline. The search snippet shows soybean after ruziziensis 4,354, wheat 4,304, corn with N 4,058, corn without N 3,942 and fallow 3,843 kg/ha. **Not verified:** Springer blocked access. It is the key source for off-season corn vs fallow. Try the PDF via Embrapa Alice or ResearchGate.
- BALBINOT JUNIOR, A. A. et al. Soybean yield, seed protein and oil concentration, and soil fertility affected by off-season crops. *Eur. J. Agron.* 153, 127039, 2024. DOI 10.1016/j.eja.2023.127039. Probably the same 7-year trial in Londrina (wheat about 10% above corn, according to Doc. 459).
- CHARNOBAY, A. C. R. et al. *Applied Soil Ecology* 209, 106040, 2025. DOI 10.1016/j.apsoil.2025.106040. Snippet: ruziziensis 4,119 vs fallow 3,525 kg/ha/year. Not verified.
- BALBINOT JUNIOR et al. 2023 (Revista Brasileira de Engenharia Agrícola e Ambiental): corn + ruziziensis, +232 kg/ha on the following soybean. Not opened.
- Sapucay, Coelho et al. 2023 (Australian J. Crop Sci.): intercropping with no effect on soybean. Not opened. It is important counter-evidence.
- Embrapa Soja, Documentos 314 (Maringá, brachiaria 56 bags vs off-season corn 45 bags in 2007/08). Not opened.
- Embrapa "Rotação de culturas" page (data from RS: soybean +20.3% in the 1st year and +10.5% in the 2nd after corn). Not opened.
- Exact location of Doc. 476 (municipality in northern PR). Not confirmed.

**Crops without data:** grain sorghum; forage radish alone; oat + radish mix; millet + crotalaria mix; common beans (Phaseolus) before soybean; summer corn isolated from the radish effect.

**Questions not yet researched:**
- Corn after corn (summer + off-season), leafhopper (Dalbulus maidis) and corn stunt.
- Beans before soybean and the increase in white mold (Sclerotinia sclerotiorum), with the effect on yield.
- Brachiaria and nematodes (Pratylenchus brachyurus, Heterodera glycines): effect on the population and on soybean.
- International meta-analyses (cover crops and rotation with soybean), for example in Field Crops Research.
- Fundação ABC, IDR-Paraná/IAPAR, Coodetec, Fundação MT, Embrapa Agropecuária Oeste: not consulted.
- Remote sensing (NDVI × yield) to measure the effect of the preceding crop, useful for validation with HLS.

## 5. Recommendation for the API (done: `bonus_sc_faixa` and `bonus_fonte` per crop, shown on the card and in `ganho_vs_atual`)

- Return `ganho_sc_ha: {min, central, max}`, `base_comparacao` ("pousio" or "milho_safrinha"), `confianca`, `fontes: [doi/url]` and `efeito` ("imediato" or "cumulativo").
- Relevant changes already supported:
  - off-season corn: from +1 to **0**;
  - corn + brachiaria: from +3 to about **+5**;
  - wheat: from +1 to about **+3**;
  - oat: from +2 to about **+4**;
  - beans: from 0 to **≤ 0** (nematode risk, cowpea proxy).
- Keep as "no source" until resumed: millet + crotalaria, sorghum, radish, oat + radish and the summer-corn extra.
