# Contratos entre as partes

Os contratos permitem que as frentes trabalhem em paralelo. **Quem muda um contrato avisa o grupo e atualiza
este arquivo no mesmo pull request.** Até o dado real existir, use os exemplos no mesmo formato.

O backend do MVP é a API do motor em `motor_field_shift/`. A referência completa (todos os campos, regras e
exemplos) está em [motor_field_shift/api/README.md](../motor_field_shift/api/README.md) e no Swagger em
`http://localhost:8000/docs`. Este arquivo resume o que cada parte pode assumir.

## C1 — Dados locais do motor (frente 1 → frentes 3 e 4)

O motor só lê arquivos locais em `motor_field_shift/data/` (exceto `/v1/contexto` e os fallbacks, que consultam
fontes externas na hora e gravam cache).

- `data/raw/` e `data/processed/` (~280 MB) ficam **fora do git**. Lista dos arquivos, tamanho e script que gera
  cada um: seção "Dados necessários" do README da API.
- `data/ref/precos_custos.json` e `data/contexto/pragas_alertas.json` são versionados.
- Fora do Oeste do PR, clima e solo usam fallback ao vivo (NASA POWER e SoilGrids 2.0).

## C2 — Catálogo (frente 2 → frentes 3, 4 e 5)

- `catalog/crops.yaml`: um bloco por cultura. **Todo número é uma faixa (`min`/`max`) com unidade e `fonte`.**
- `catalog/vocabulario.yaml`: listas fechadas compartilhadas por catálogo, formulário da fazenda e frontend
  (máquinas, irrigação, mão de obra, texturas).

Pendente: o motor ainda usa catálogo próprio (`/v1/opcoes`) e não lê `catalog/`. Até a unificação, **os ids
válidos para a API são os de `/v1/opcoes`**.

## C3 — API (backend → frontend)

Base: `http://localhost:8000`. CORS aberto. Sem autenticação. Todas as rotas são stateless: o frontend guarda
os dados da fazenda (localStorage) e os envia em cada requisição.

| Método | Rota | Uso no frontend |
| --- | --- | --- |
| GET | `/health` | Verificar se a API está no ar e se os dados carregaram (`ok` / `degradado`) |
| GET | `/v1/opcoes` | Montar os seletores: culturas de verão e da 2ª janela, combinações válidas, semeaduras, critérios, pesos padrão, referências de renda, talhões demo |
| GET | `/v1/talhoes/demo` | Lista de talhões de demonstração |
| POST | `/v1/diagnostico` | Telas de fazenda, histórico e clima: relevo, solo, histórico MapBiomas, rotação detectada, clima e riscos, produtividade |
| POST | `/v1/recomendacao` | Tela de rotação: ranking, rotação atual, alternativas, eliminadas, cards |
| GET | `/v1/clima` | Só o bloco de clima para um ponto |
| GET, POST | `/v1/contexto` | Situação atual (ENSO, SMAP, MJO, pragas). Informativo, não altera a nota |

### Área (comum a `/diagnostico` e `/recomendacao`)

Exatamente uma forma: `{"talhao_id": "72638"}`, `{"lat": -24.95, "lon": -53.45}` ou
`{"geometry": <GeoJSON Polygon/MultiPolygon/Feature>}` (EPSG:4326, máx. 5000 ha).

### `POST /v1/recomendacao`: o essencial

Entrada mínima:

```json
{ "area": {"talhao_id": "72638"}, "rotacao_atual": "soja__milho_safrinha" }
```

Opcionais: `semeadura_safrinha`, `pesos {renda, solo, agua, pragas, risco}` (0 a 10), `rotacoes[]`, `ajustes`
(preços, custos, produtividade), `analise_solo`, `restricoes`, `irrigacao`, `n_alternativas`,
`incluir_diagnostico`.

Uma **rotação** é um par (cultura de verão, cultura da 2ª janela) com id `"<verao>__<segunda>"`.

Saída: `ranking[]` e `alternativas[]` com `nota` (0 a 1), `criterios{}`, `margem{total_r_ha, incremental_r_ha}`
e `card{por_que, evidencias, beneficios, lacunas, riscos, avisos}`; `atual`; `eliminadas[]` com `motivos[]`;
`avisos[]`; `metodologia`.

### Erros

| Status | Corpo | Quando |
| --- | --- | --- |
| 422 | `{"erro": "fora_da_regiao"}` | Área fora do Oeste do PR |
| 422 | erro de validação | Corpo inválido |
| 400 | `{"erro": "entrada_invalida"}` | Restrições eliminaram todas as rotações, ajuste inválido etc. |
| 504 | `{"erro": "timeout_externo"}` | Fallback NASA POWER ou SoilGrids não respondeu |
| 500 | `{"erro": "interno"}` | Erro inesperado |

Todos os erros do motor trazem também `mensagem` (texto legível).

### Exemplos para desenvolver sem dados

Respostas reais em [motor_field_shift/api/exemplos/](../motor_field_shift/api/exemplos/): use-as como mock no
frontend enquanto os dados locais não estiverem disponíveis.

## Pendências de contrato

- **Semáforo de confiança** (🔴 encaminhar a profissional, 🟡 indicativo, 🟢 bem sustentado): ainda não existe
  na resposta. Proposta: campo `confianca{nivel, motivos[]}` em cada item do ranking e no `atual`.
- **Região:** decidir se a demo fica no Oeste do PR ou se a trava sai (os fallbacks já cobrem solo e clima).
- **Catálogo:** unificar `catalog/crops.yaml` e o catálogo interno do motor.
