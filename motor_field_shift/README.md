# Rotation engine — Western Paraná

Crop-rotation recommendation engine focused on Western Paraná (50 municipalities, IBGE 4106).
It is the **MVP backend**: its API is contract C3 in [`../docs/contratos.md`](../docs/contratos.md).

- Engine logic: [`docs/motor.md`](docs/motor.md)
- Data architecture: [`docs/arquitetura.md`](docs/arquitetura.md) · sources: [`docs/datasets.md`](docs/datasets.md)
- API (FastAPI) and how to use it: [`api/README.md`](api/README.md)

These linked docs are still in Portuguese.

## How to run

```bash
cd motor_field_shift
uv sync
# generate the data (not versioned): see "Dados necessários" in api/README.md
uv run uvicorn field_shift_api.main:app --app-dir api --reload   # http://localhost:8000/docs
uv run pytest                                                    # unit tests
```

## What's inside

| Folder | Contents |
| --- | --- |
| `src/field_shift/motor/` | service layer: `diagnosticar()`, `recomendar()` |
| `src/field_shift/app/` | hard rules, criteria, weighted score, cards (`engine.py`) + Streamlit app (`mvp.py`) |
| `src/field_shift/{clima,regiao,solo,agua,pam,renda}/` | NASA POWER, MapBiomas/NASADEM, SoilGrids, FAO-56 water balance, IBGE PAM, prices/costs |
| `ingest/` | scripts that download and pre-compute the region's data |
| `api/` | FastAPI app, tests and real response examples |
