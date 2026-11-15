# catalog

English agronomic reference catalog and explanation templates.

- `crops.yaml`: six species profiles. Every numeric attribute is a range (`min`/`max`) with `unit` and `source`.
- `sistemas.yaml`: all 13 engine systems, with crop components, engine seasons and curation status.
- `vocabulario.yaml`: English vocabulary for machinery, irrigation, labor, textures, purposes and statuses.
  Engine criterion and season IDs remain unchanged.
- `textos.yaml`: 17 English templates in `criteria`, `triggers` and `referrals`, with `locale: en`.
- `labels.yaml`: English display names for preserved criterion and season IDs.
- `validate.py` and `test_validate.py`: contract validation and regression checks.

Sources used: Embrapa, FAO (Ecocrop, FAO-56), ZARC (MAPA), CONAB, CEPEA, IBGE.

## Compatibility and schema migration

Field names, descriptive values, vocabulary and templates are in English. Filenames and crop/system IDs
remain stable. For example, `milho_verao` displays as **First-season maize** and `milho_safrinha` as
**Second-season maize (safrinha)**. API criteria remain `renda`, `solo`, `agua`, `pragas`, `risco`.
Translate display names, never API identifiers.

This branch migrates YAML keys: `culturas` → `crops`, `nome` → `name`, `fonte` → `source`,
`unidade` → `unit`, `observacao` → `note`, `requisitos_solo` → `soil_requirements`, and
`ciclo_dias` → `cycle_days`. Controlled vocabulary values also change (e.g. `graos` → `grain`).
Future readers must use this schema. Catalog machinery and irrigation values are not the API request schema.

The engine in `motor_field_shift/` does not read these files. No ranking, scoring, API payload or frontend
behavior changes here. `/v1/opcoes` remains authoritative for accepted system IDs. Catalog loading and
template rendering require a separate integration change.

## Species and cultivation systems

`crops.milho` is the general species profile; `systems.milho_verao` and `systems.milho_safrinha`
describe distinct systems. `components` lists existing species profiles only. Mapping an engine option
does not authorize planting it or prove that its agronomic data is complete.

Systems with missing component profiles or mismatched uses are marked `curation_pending` and describe
the gaps in `pending_research`. In particular, `aveia_branca` is a grain profile and is not silently
assigned to the `aveia` cover-crop option. `pousio` is fallow, not a species.

`general_reference` and `context_dependent_reference` describe evidence scope, not confidence scores
or completeness guarantees. Review field notes and pending research even for a mapped species.
Missing fields or explicit `null` values mean missing evidence, never zero or no requirement.
Do not automatically inherit species nitrogen rates into systems or combine intercropping components
as if their requirements were independent. No generic merge/loader is implemented in this branch.

## Maize references

- Cycle: **125–180 days**, a general grain-maize reference from sowing to harvest in FAO Chapter 3,
  Table 6. This replaces the previously unsubstantiated 100–150-day attribution. It does not establish
  a seasonal difference or a local cultivar prediction.
  https://www.fao.org/4/s2022e/s2022e07.htm
- Water: **400–700 mm/cycle** for medium-cycle dry-grain maize in Embrapa's irrigation manual, page 1.
  https://ainfo.cnptia.embrapa.br/digital/bitstream/item/27341/1/Irrigacao-Manejo.pdf
- Second-season water: **400–600 mm** in the **120-day cultivar scenario** in Embrapa Documentos 273,
  pages 7 and 10. Do not extrapolate to the entire cycle range above or treat consumption as required irrigation.
  https://www.infoteca.cnptia.embrapa.br/infoteca/bitstream/doc/1156268/1/Ecofisiologia-do-milho-segunda-safra-para-alta-produtividade.pdf
- First-season planting: August–September is described as usual in Southern Brazil.
  https://www.embrapa.br/web/agencia-de-informacao-tecnologica/cultivos/milho/producao/plantio/espacamento-e-densidade
- Second-season planting: January–March is a general reference, with earlier sowing advised in colder areas.
  https://www.embrapa.br/web/agencia-de-informacao-tecnologica/cultivos/milho/producao/sistemas-diferenciais-de-cultivo/milho-safrinha

The AGEITEC planting pages returned HTTP 403 on direct access during research; search-index excerpts
were available. The FAO table and the irrigation/second-season PDFs were accessed through web retrieval.

Planting windows use `start`/`end` in **DD/MM** format, not numeric ranges. Month boundaries encode
the months described by the sources. `use: informational` means they are not approved ZARC ten-day
periods, engine sowing options or exclusion thresholds. Check ZARC by municipality, soil, cultivar group
and season before a planting decision.

The **45–60 kg N/ha** topdressing reference is now confined to second-season maize after soybean within
its source context. A matching first-season rate remains a research gap, rather than an invented value.
Nitrogen demand per tonne of grain is not fertilizer application per hectare. Experimental fertilizer
treatments, such as those in the white-oat profile, are not recommended application ranges.

## Explanation templates

Select a template only when its corresponding evidence is available. Fill named placeholders with validated
values and format crop names, dates, currency and units in English. A `{source}` value should identify the
actual source of that claim; do not automatically cite agronomic literature for a computed score.
Never invent missing values, render unresolved placeholders or insert raw values as unescaped HTML.
Missing-data and referral messages do not fabricate citations. These templates do not translate current
engine responses until a renderer is connected.

## Validation

Requires Python 3.12+ and PyYAML (`python -m pip install PyYAML`). From the repository root:

```bash
python catalog/validate.py
python -m unittest discover -s catalog -p 'test_*.py'
```

Validation rejects duplicate YAML keys, invalid numeric ranges, missing units/sources, malformed dates,
unknown vocabulary and crop references, mismatched engine IDs/seasons and invalid template placeholders.
It compares engine constants through the Python AST without loading geospatial dependencies or datasets.
It does not fetch source URLs, confirm scientific accuracy or guarantee natural-language translation quality.

Next: validate local system-specific references, curate missing species/consortia, then implement catalog
loading and template rendering with the backend team.