# Motor de rotação — Oeste do PR (protótipo)

Protótipo autocontido do motor de recomendação de rotação de culturas, focado no Oeste do Paraná
(50 municípios, IBGE 4106). Ainda **não** está integrado à estrutura `backend/` nem aos contratos de
`docs/contratos.md`; fica nesta pasta para o time decidir o que aproveitar.

- Lógica do motor: [`docs/motor.md`](docs/motor.md)
- Arquitetura de dados: [`docs/arquitetura.md`](docs/arquitetura.md) · fontes: [`docs/datasets.md`](docs/datasets.md)
- API (FastAPI) e como usar: [`api/README.md`](api/README.md)

## Como rodar

```bash
cd motor_field_shift
uv sync
# gerar os dados (não versionados): ver "Dados necessários" em api/README.md
uv run uvicorn field_shift_api.main:app --app-dir api --reload   # http://localhost:8000/docs
uv run pytest                                                    # testes unitários
```

## O que tem

| Pasta | Conteúdo |
| --- | --- |
| `src/field_shift/motor/` | camada de serviço: `diagnosticar()`, `recomendar()` |
| `src/field_shift/app/` | regras duras, critérios, nota ponderada, cards (`engine.py`) + app Streamlit (`mvp.py`) |
| `src/field_shift/{clima,regiao,solo,agua,pam,renda}/` | NASA POWER, MapBiomas/NASADEM, SoilGrids, balanço hídrico FAO-56, IBGE PAM, preços/custos |
| `ingest/` | scripts que baixam e pré-calculam os dados da região |
| `api/` | API FastAPI, testes e exemplos de resposta reais |
