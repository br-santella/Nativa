# Rotation engine — Paraná

Crop-rotation recommendation engine for the state of Paraná (399 municipalities, IBGE 41). Costs, prices and calendar rules are the Western Paraná (Oeste, 50 municipalities, IBGE 4106) references; outside it the response carries warnings.
It is the project backend. Its API is contract C3 in [`../docs/contratos.md`](../docs/contratos.md).

Documentation (in English, except `docs/calculo_por_fator.md` and `docs/precisao_do_motor.md`, in Portuguese):

- Engine logic: [`docs/motor.md`](docs/motor.md) · validation: [`docs/validation.md`](docs/validation.md)
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
| `src/field_shift/core/` | service layer: `options()`, `diagnose()`, `recommend()`, `warm_up()` |
| `src/field_shift/app/` | hard rules, criteria, weighted score, cards (`engine.py`) + Streamlit app (`mvp.py`) |
| `src/field_shift/{climate,region,soil,water,pam,income}/` | NASA POWER, MapBiomas/NASADEM, SoilGrids, FAO-56 water balance, IBGE PAM, prices/costs |
| `ingest/` | scripts that download and pre-compute the data (`--regiao oeste_pr|pr`); `scripts/download_pr/run_all.sh` runs the whole-of-Paraná ingestion |
| `src/field_shift/i18n/` | English translation of the API responses (catalog `en.json`; pt-BR is the default) |
| `api/` | FastAPI app, tests and real response examples |
