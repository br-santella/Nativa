# Backend (Python)

API FastAPI sem estado e motor de análise em Python puro. Camadas e regras de importação:

| Camada | Pode importar | Não pode importar |
| --- | --- | --- |
| `domain` | pydantic e biblioteca padrão | qualquer outra camada |
| `engine` | `domain`, `ml`, interfaces de repositório (Protocol) | `api`, `explain`, FastAPI, leitura direta de arquivo |
| `data_access` | `domain`, pandas/duckdb, httpx | `engine`, `api` |
| `ml` e `explain` | `domain`; scikit-learn e joblib (`ml`); `textos.yaml` (`explain`) | `api` |
| `api` | todas as anteriores (monta tudo) | — |

Rodar os testes: `pytest backend/engine/tests`.
