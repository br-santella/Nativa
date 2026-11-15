# Field Shift Brasil — NASA Space Apps 2026

Ferramenta web de apoio à decisão para **rotação de culturas** no Brasil, construída para o desafio
[Field Shift: Adapting Farms with NASA Data](https://www.spaceappschallenge.org/2026/challenges/adapting-farms-with-nasa-data/).

O agricultor informa a área (talhão, polígono ou ponto), a rotação que usa hoje e, se tiver, dados próprios
(análise de solo, produtividade, preços, máquinas, irrigação). O motor cruza isso com dados da NASA
(POWER, NASADEM, SMAP) e com bases brasileiras (MapBiomas, SoilGrids, IBGE PAM, CONAB, SEAB/DERAL) e devolve
um **diagnóstico** da área e um **ranking de rotações**. Cada rotação vem com nota, margem estimada,
evidências, lacunas e riscos.

> A ferramenta apoia, mas **não substitui**, a orientação de um engenheiro agrônomo.

A solução **não usa LLM**. A IA é ML clássico, regras e otimização. As explicações são montadas a partir das
evidências calculadas.

## Estrutura

```text
motor_field_shift/   backend: motor de recomendação + API FastAPI (Python, uv)
  api/               rotas, schemas, testes e exemplos reais de resposta
  src/field_shift/   motor (regras, nota, cards) e módulos de dados: clima, solo, regiao, agua, pam, renda, contexto
  ingest/, scripts/  download e pré-processamento dos dados da região
  data/              dados locais (raw/ e processed/ fora do git)
frontend/            interface NATIVA (React + Vite + TypeScript)
catalog/             crops.yaml e vocabulario.yaml: catálogo agronômico com fontes
docs/                contratos entre as partes, material do pitch
```

Escopo atual do motor: **Oeste do Paraná** (50 municípios). Áreas fora dele retornam 422 `fora_da_regiao`.

Não há login nem banco de dados de usuário no MVP: os dados da fazenda ficam no navegador e vão em cada
requisição. A API só calcula (stateless).

## Como rodar

```bash
# backend (http://localhost:8000/docs)
cd motor_field_shift
uv sync
uv run uvicorn field_shift_api.main:app --app-dir api --reload

# frontend (http://localhost:5173)
cd frontend
npm ci
npm run dev
```

O backend precisa dos dados de `motor_field_shift/data/` (~280 MB, fora do git); a lista está em
[motor_field_shift/api/README.md](motor_field_shift/api/README.md). Sem eles a API sobe, mas `/health` responde
`degradado`.

## Frentes

| # | Frente | Pastas principais |
| --- | --- | --- |
| 1 | Dados | `motor_field_shift/ingest/`, `scripts/`, `data/`, `src/field_shift/{clima,solo,regiao,agua,pam,renda,contexto}/` |
| 2 | Curadoria agronômica | `catalog/` |
| 3 | Motor de pontuação | `motor_field_shift/src/field_shift/{motor,app}/` |
| 4 | Confiança, explicações e API | `motor_field_shift/api/`, cards e avisos do motor |
| 5 | Frontend | `frontend/` |
| 6 | Produto, integração e pitch | `docs/`, deploy |

## Fluxo de trabalho

Cada tarefa tem uma branch curta criada a partir da `main` e entra por pull request.

```bash
git checkout main && git pull
git checkout -b feat/<tema>        # ou fix/<tema>, chore/<tema>
# ... trabalho ...
git push -u origin feat/<tema>
# abrir pull request para a main
```

Boas práticas:

- Não commite direto na `main`.
- Commits pequenos e frequentes; puxe a `main` para a sua branch com regularidade (`git merge main`).
- **Contratos primeiro:** quem muda um contrato de [docs/contratos.md](docs/contratos.md) avisa o grupo e
  atualiza o arquivo no mesmo PR.
- Nunca commite chaves, credenciais, `.env` ou `.netrc`.

## Marcos

| Quando | Marco |
| --- | --- |
| 15/11 ~10h | Frontend consumindo a API do motor com dados reais |
| 15/11 18h | Freeze de features: só correção de bug e pitch |
| 15/11 23:59 | Submissão |
