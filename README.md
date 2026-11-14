# Field Shift Brasil — NASA Space Apps 2026

Ferramenta web de apoio à decisão para **rotação de culturas** no Brasil, construída para o desafio
[Field Shift: Adapting Farms with NASA Data](https://www.spaceappschallenge.org/2026/challenges/adapting-farms-with-nasa-data/).

O agricultor informa o **plano de safra** (último ano e plano atual) e os **dados da fazenda**. A plataforma cruza
essas informações com dados da NASA (POWER, GPM IMERG, SMAP, MODIS/HLS, SRTM) e com bases brasileiras
(ZARC, MapBiomas, SoilGrids, IBGE, CONAB). O resultado é a comparação de 4 estratégias: último ano, plano atual
e duas alternativas geradas pelo sistema. Cada estratégia vem com evidências, lacunas, riscos e um semáforo de
confiança.

> A ferramenta apoia, mas **não substitui**, a orientação de um engenheiro agrônomo.

A solução **não usa LLM**. A IA é ML clássico e otimização: preenchimento de nuvem, fenologia, Random Forest,
TOPSIS/Pareto e bootstrap. As explicações são montadas por modelos de frase a partir das evidências calculadas.

## Estrutura

```text
backend/
  domain/        modelos Pydantic (Fazenda, PlanoSafra, Cultura, Analise...)   frentes 3 + 4
  engine/        serviços: validação, viabilidade, busca, simulação, ranking,   frentes 3 + 4
                 confiança
  ml/            inferência dos modelos .joblib (nuvem, fenologia, RF, anomalia) frentes 1 + 4
  explain/       explicações por modelos de frase + decomposição da nota        frente 4
  data_access/   repositórios: Parquet, catálogo YAML, cliente NASA POWER       frente 1
  api/           FastAPI: rotas, CORS, injeção de dependências                  frente 4
catalog/         crops.yaml, vocabulario.yaml, textos.yaml                      frente 2
ingest/          scripts offline (GEE, POWER, SoilGrids) + treino dos modelos   frente 1
data/demo/       dados pré-processados da região demo + models/*.joblib         frente 1
frontend/        React + Vite + TypeScript + MapLibre                           frente 5
docs/            contratos, fontes NASA, métricas dos modelos, pitch            frente 6
```

Regra de dependência: `api` → `engine` / `explain` → `domain`. O `domain` não importa nada do projeto, e o
`frontend` só conhece a API pelos tipos gerados do OpenAPI. Detalhes em cada `README.md` de pasta.

## Frentes e branches

Cada frente trabalha na própria branch, criada a partir da `main`, e entra na `main` por pull request.

| # | Frente | Branch | Pastas principais |
| --- | --- | --- | --- |
| 1 | Dados e IA de dados | `frente/dados` | `ingest/`, `data/`, `backend/data_access/`, `backend/ml/` |
| 2 | Curadoria agronômica | `frente/curadoria` | `catalog/` |
| 3 | Motor de pontuação | `frente/motor` | `backend/engine/`, `backend/domain/` |
| 4 | Confiança, explicações e API | `frente/api` | `backend/api/`, `backend/explain/`, `backend/engine/` (confiança) |
| 5 | Frontend | `frente/frontend` | `frontend/` |
| 6 | Produto, integração e pitch | `frente/produto` | `docs/`, deploy |

```bash
git checkout main && git pull
git checkout -b frente/<nome>
# ... trabalho ...
git push -u origin frente/<nome>
# abrir pull request para a main
```

Boas práticas:

- Commits pequenos e frequentes; puxe a `main` para a sua branch com regularidade (`git merge main`).
- **Contratos primeiro:** quem muda um contrato de [docs/contratos.md](docs/contratos.md) avisa o grupo e atualiza o arquivo no mesmo PR.
- Até o contrato real ficar pronto, trabalhe com **dados de exemplo (mock)** no formato do contrato.
- Nunca commite chaves, credenciais ou `.env`.

## Marcos

| Quando | Marco |
| --- | --- |
| 14/11 ~16h | Contratos C1–C3 congelados e JSON de exemplo commitado |
| 14/11 ~23h | Dados reais da região demo em Parquet; `crops.yaml` v1 |
| 15/11 ~10h | Primeira execução ponta a ponta com dados reais |
| 15/11 18h | Freeze de features: só correção de bug e pitch |
| 15/11 23:59 | Submissão |
