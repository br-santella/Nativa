# Rotation engine — Paraná

Crop-rotation recommendation engine for the state of Paraná (399 municipalities, IBGE 41). Costs, prices and calendar rules are the Western Paraná (Oeste, 50 municipalities, IBGE 4106) references; outside it the response carries warnings.
It is the project backend. Its API is contract C3 in [`../docs/contratos.md`](../docs/contratos.md).

Documentation (in Portuguese):

- Engine logic: [`docs/motor.md`](docs/motor.md)
- Data architecture: [`docs/arquitetura.md`](docs/arquitetura.md) · sources: [`docs/datasets.md`](docs/datasets.md)
- API (FastAPI) and usage: [`api/README.md`](api/README.md)

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
| `ingest/` | scripts that download and pre-compute the data (only the `*_oeste_pr` versions; the whole-of-Paraná `*_pr` ingests are not versioned yet, see `docs/pendencias.md`) |
| `api/` | FastAPI app, tests and real response examples |
