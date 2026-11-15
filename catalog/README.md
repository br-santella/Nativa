# catalog

Agronomic catalog in YAML.

- `crops.yaml`: soybean, corn, wheat, white oat, barley and annual ryegrass. Every numeric attribute is a
  range (`min`/`max`) with a unit and a `fonte` (source URL).
- `vocabulario.yaml`: closed lists for machinery, irrigation, labor and soil textures.
- `textos.yaml`: sentence templates in Portuguese for explanations. Its sections are empty.

Sources used: Embrapa, FAO (Ecocrop, FAO-56), ZARC (MAPA), CONAB, CEPEA, IBGE.

Use in the engine (`motor_field_shift/`), always informative (never in the score):

- `crops.yaml` is read by `field_shift.crop_sheets`: the farmer's pH is compared with each crop's `requisitos_solo.ph` on the card,
  and the sheets are served by `GET /v1/culturas/fichas`. The engine -> sheet id map is `ENGINE_TO_SHEET` in that module
  (`tests/test_crop_sheets.py` fails if an engine crop is missing from it). Free texts are extracted to the i18n catalog
  (`scripts/i18n_extract.py`), so a new or edited text needs its English in `src/field_shift/i18n/en.json`.
- `vocabulario.yaml` gives the closed list `problemas_area`.
- `textos.yaml` is not read.
