# catalog

Agronomic catalog in YAML.

- `crops.yaml`: soybean, corn, wheat, white oat, barley and annual ryegrass. Every numeric attribute is a
  range (`min`/`max`) with a unit and a `fonte` (source URL).
- `vocabulario.yaml`: closed lists for machinery, irrigation, labor and soil textures.
- `textos.yaml`: sentence templates in Portuguese for explanations. Its sections are empty.

Sources used: Embrapa, FAO (Ecocrop, FAO-56), ZARC (MAPA), CONAB, CEPEA, IBGE.

The engine in `motor_field_shift/` does not read these files.
