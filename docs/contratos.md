# Contratos entre as frentes

Os contratos são o que permite as 6 frentes trabalharem em paralelo. **Quem muda um contrato avisa o grupo e
atualiza este arquivo no mesmo pull request.** Até o dado real existir, use dados de exemplo no mesmo formato.

## C1 — Dados da região demo (frente 1 → frentes 3 e 4)

`data/demo/features_decendio.parquet`: uma linha por ponto × ano × decêndio (36 por ano).

| Coluna | Tipo | Unidade | Fonte |
| --- | --- | --- | --- |
| `lat`, `lon` | float | graus | — |
| `ano` | int | — | — |
| `decendio` | int | 1–36 | — |
| `chuva_mm` | float | mm | GPM IMERG |
| `et0_mm` | float | mm | NASA POWER |
| `tmin_c`, `tmax_c` | float | °C | NASA POWER |
| `sm_raiz` | float | m³/m³ | SMAP L4 |
| `ndvi` | float | 0–1 | MODIS / HLS (com lacunas preenchidas) |

`data/demo/climatologia.parquet`: mesmas variáveis com `p10`, `p50` e `p90` por ponto × decêndio.

`data/demo/models/*.joblib`: modelos treinados (preenchimento de nuvem, classificador de uso, anomalia).

## C2 — Catálogo (frente 2 → frentes 3, 4 e 5)

- `catalog/crops.yaml`: um bloco por cultura no esquema da classe `Cultura`. **Todo número é uma faixa
  (`min`/`max`) e tem `fonte`.** Campo sem fonte não entra no motor.
- `catalog/vocabulario.yaml`: listas fechadas compartilhadas por catálogo, formulário da fazenda e frontend
  (máquinas, irrigação, mão de obra, texturas, finalidades, critérios).
- `catalog/textos.yaml`: modelos de frase em pt-BR usados nas explicações, nos motivos de confiança e nos
  encaminhamentos.

## C3 — API (frentes 3 e 4 → frente 5)

Os modelos Pydantic em `backend/domain/` são a fonte única; o OpenAPI sai em `/docs` e os tipos do frontend são
gerados com `openapi-typescript`.

| Rota | Entrada | Saída |
| --- | --- | --- |
| `GET /catalogo` | — | `list[CulturaResumo]` + `Vocabulario` |
| `GET /local/contexto?lat=&lon=` | coordenadas | `ContextoLocal` (município, UF, declividade, solo estimado, janelas ZARC) |
| `POST /planos/validar` | `{fazenda, plano}` | `list[Alerta]` |
| `POST /analises` | `RequisicaoAnalise {fazenda, plano_ultimo_ano, plano_atual, prioridades}` | `Analise` (4 estratégias com nota, faixa p10–p90, critérios, confiança, lacunas, evidências, explicação) |
| `POST /cenarios` | `RequisicaoAnalise` + `{delta_temp_c, delta_chuva_pct}` | `Analise` |
| `GET /health` | — | status, versão do catálogo e dos dados |

Um exemplo estático de resposta de `POST /analises` deve ser commitado em `docs/exemplos/analise.json` na
primeira hora, para a frente 5 começar.
