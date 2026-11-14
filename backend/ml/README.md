# ml — frentes 1 + 4

Inferência dos modelos treinados offline em `ingest/notebooks/` e salvos em `data/demo/models/*.joblib`.

| Classe | Técnica | Onde roda |
| --- | --- | --- |
| `PreenchedorNuvem` | regressão harmônica / Savitzky-Golay | ingestão |
| `DetectorFenologia` | picos e limiares na série de NDVI | ingestão |
| `ClassificadorUso` | Random Forest com rótulos do MapBiomas | ingestão |
| `DetectorAnomalia` | Isolation Forest / z-score | API |

Registre as métricas de validação de cada modelo em `docs/metricas_modelos.md`.
