# Field Shift API

API HTTP (FastAPI) do motor de recomendação de **rotação de culturas** do Field Shift. Dada uma área
(talhão demo, polígono GeoJSON ou ponto lat/lon), ela devolve um **diagnóstico** (relevo, solo,
histórico de cultivo, clima, produtividade) e um **ranking de rotações** para a safrinha/entressafra,
com nota de 0 a 1, margem estimada em R$/ha e um cartão explicativo por opção.

**Escopo:** Oeste do Paraná (50 municípios, código IBGE 4106). Qualquer área fora dele retorna
**422** com `{"erro": "fora_da_regiao"}`.

## Como rodar

```bash
uv sync
uv run uvicorn field_shift_api.main:app --app-dir api --reload
```

- Swagger (com exemplos preenchidos): <http://127.0.0.1:8000/docs>
- ReDoc: <http://127.0.0.1:8000/redoc>
- OpenAPI JSON: <http://127.0.0.1:8000/openapi.json>

No startup a API chama `servico.aquecer()` (pré-carrega os dados). Se faltar dado, ela sobe mesmo
assim e `GET /health` responde `"status": "degradado"` com o motivo em `detalhe`.

Testes: `uv run pytest` (serviço falso) e `uv run pytest -m integracao` (serviço real e dados em `data/`).

### Dados necessários em `data/`

| Caminho | Gerado por |
|---|---|
| `data/raw/clima/*` e `data/processed/clima/*` | `ingest/clima_oeste_pr.py` |
| `data/raw/regiao/*` | `ingest/mapbiomas_relevo_oeste_pr.py` |
| `data/raw/mapbiomas_oeste_pr/*` | `ingest/mapbiomas_relevo_oeste_pr.py` |
| `data/raw/nasadem_oeste_pr/*` e `data/processed/relevo_oeste_pr/*` | `ingest/mapbiomas_relevo_oeste_pr.py` |
| `data/raw/soilgrids_oeste_pr/*` | `ingest/solo_pam_oeste_pr.py` |
| `data/raw/ibge/pam_oeste_pr.parquet` | `ingest/solo_pam_oeste_pr.py` |
| `data/ref/precos_custos.json` | `uv run python -m field_shift.renda.atualizar` |

`data/raw` e `data/processed` ficam fora do git: cada máquina precisa rodar as ingestões
(as de clima/NASADEM exigem credenciais Earthdata em `~/.netrc`).

## Endpoints

| Método | Rota | Descrição |
|---|---|---|
| GET | `/health` | Estado do serviço e se os dados carregaram |
| GET | `/v1/opcoes` | Rotações, semeaduras, critérios, pesos padrão, referências de renda, região, talhões demo |
| GET | `/v1/talhoes/demo` | Lista de talhões de demonstração |
| POST | `/v1/diagnostico` | Diagnóstico completo da área |
| POST | `/v1/recomendacao` | Ranking de rotações (e, opcionalmente, o diagnóstico) |
| GET | `/v1/clima` | Atalho: só o bloco `clima` do diagnóstico para um ponto |

### Objeto `area` (comum a `/diagnostico` e `/recomendacao`)

Informe **exatamente uma** das três formas.

| Campo | Tipo | Obrigatório | Padrão | Descrição |
|---|---|---|---|---|
| `geometry` | objeto GeoJSON | uma das formas | n/d | Polygon, MultiPolygon ou Feature, EPSG:4326 (lon, lat). Máx. 5000 ha |
| `lat` + `lon` | número | uma das formas | n/d | Ponto; vira um quadrado de 1000 m x 1000 m (~100 ha, UTM 22S). Informe os dois |
| `talhao_id` | string | uma das formas | n/d | Id de talhão demo (ex.: `"72638"`) |

### `GET /health`

Saída: `status` (`ok`/`degradado`), `dados_carregados` (bool), `versao`, `detalhe` (motivo, se degradado).

### `GET /v1/opcoes` e `GET /v1/talhoes/demo`

Sem entradas. `/opcoes` devolve `rotacoes` (slug para nome), `semeaduras`, `semeadura_padrao`,
`criterios`, `pesos_padrao`, `renda_referencia`, `regiao`, `talhoes_demo`. `/talhoes/demo` devolve só a lista `talhoes_demo`.

### `POST /v1/diagnostico`

| Campo | Tipo | Obrigatório | Padrão | Descrição |
|---|---|---|---|---|
| `area` | objeto | sim | n/d | Ver acima |
| `semeadura_safrinha` | enum `15/01`, `01/02`, `15/02`, `01/03`, `15/03` | não | `01/02` | Data de semeadura da safrinha |

Saída:

| Campo | Descrição |
|---|---|
| `area` | `origem`, `talhao_id`, `area_ha`, `centroide{lat,lon}`, `municipio{cod_ibge,nome}`, `geometry` |
| `relevo` | Declividade e derivados (NASADEM) |
| `solo` | Atributos do SoilGrids (textura, carbono etc.) |
| `historico[]` | Uso do solo ano a ano (MapBiomas): `ano`, `classe`, `nome_classe`, `fracao_dominante`. O MapBiomas regional só foi baixado para **2019-2024**: anos sem dado simplesmente não aparecem na lista (não há itens nulos) |
| `rotacao_detectada` | `rotacao`, `fonte` e `dias_solo_descoberto` inferidos do histórico |
| `clima` | `fonte`, `celula`, `semeadura_safrinha`, `riscos` (geada safrinha/trigo, veranico, `n_anos`, `periodo`), `geada_por_semeadura[]` (probabilidade por data), `diagnostico` (início das chuvas, calor para soja, balanço P-ET0, chuva intensa) |
| `produtividade` | Produtividade de referência por cultura (IBGE PAM) |
| `avisos[]` | Alertas de qualidade/escopo do dado |

### `POST /v1/recomendacao`

| Campo | Tipo | Obrigatório | Padrão | Descrição |
|---|---|---|---|---|
| `area` | objeto | sim | n/d | Ver acima |
| `semeadura_safrinha` | enum (idem acima) | não | `01/02` | Data de semeadura da safrinha |
| `pesos` | objeto `renda, solo, agua, pragas, risco` (0 a 10 cada) | não | renda 5, demais 3 | Importância de cada critério; omitidos usam o padrão; se todos forem 0, o motor usa pesos iguais |
| `rotacao_atual` | enum de slugs | não | nenhuma | Rotação usada hoje, para comparação (`atual`) |
| `ajustes.precos` | `{soja, milho, trigo}` em R$/saca (>= 0) | não | referência | Preços próprios |
| `ajustes.custos` | `{cultura: R$/ha}`, chaves: `soja`, `milho` (alias de `milho_2safra`), `milho_2safra`, `trigo`, `aveia`, `milheto_crotalaria`, `braquiaria_consorcio`, `pousio`; valores >= 0 | não | referência | Custos próprios (chave desconhecida é rejeitada) |
| `ajustes.linha_custo` | `coe`, `cot` ou `ct` | não | do serviço | Custo operacional efetivo, operacional total ou custo total |
| `n_alternativas` | inteiro 1 a 6 | não | `3` | Quantas alternativas devolver |
| `incluir_diagnostico` | bool | não | `true` | Inclui o bloco `diagnostico` |

Slugs: `milho_safrinha`, `milho_braquiaria`, `trigo`, `aveia`, `milheto_crotalaria`, `pousio`, `soja_safrinha`.

Saída:

| Campo | Descrição |
|---|---|
| `entrada` | Eco da entrada efetivamente usada (pesos, preços, semeadura) |
| `diagnostico` | Igual ao de `/v1/diagnostico` (se `incluir_diagnostico`) |
| `ranking[]` | `posicao`, `id`, `rotacao`, `nota` (0 a 1), `atual`, `criterios{renda,solo,agua,pragas,risco}`, `contribuicoes{}`, `margem{total_r_ha, incremental_r_ha, escala_S_r_ha, itens[{cultura, rendimento_sc_ha, preco, custo, margem_r_ha, fonte}], ano_ruim_r_ha}`, `card{por_que, evidencias, beneficios, lacunas, riscos, avisos}` |
| `atual` | Item da rotação atual (quando informada). Se ela for eliminada por regra dura (só `soja_safrinha`), vem com `posicao` e `nota` nulos, `eliminada: true` e `motivos[]`, e não aparece em `ranking`/`alternativas`. Sem `rotacao_atual`, o motor detecta: só o talhão 72638 tem detecção por NDVI; nos demais assume `milho_safrinha` com aviso |
| `alternativas[]` | Itens alternativos à rotação atual |
| `eliminadas[]` | Rotações vetadas por regra dura: `id`, `rotacao`, `motivos[]` |
| `avisos[]` | Alertas gerais |
| `metodologia` | `formula`, `criterios{}` e `versao` |

Os números saem arredondados (`nota`, `criterios` e `contribuicoes` com 3 casas; R$ sem casas; probabilidades com 3 casas); o ranking usa a nota sem arredondar. `card.por_que` compara cada alternativa com a rotação atual (até 3 critérios de maior diferença ponderada, com números); no item da atual diz a posição e a melhor alternativa.

Campos extras úteis: `margem.bonus_proxima_soja_r_ha` e `margem.linha_custo`; `clima.textos`; `rotacao_detectada.picos_por_ano_agricola`; `relevo.texto`; `solo.texto`, `p30`, `prof`, `cad_mm_cm`, `cad_mm_0_30`, `cad_mm_0_60`, `classe_textura`, `cad_metodo`; `produtividade{municipio, cod_ibge, fonte, culturas, texto, rendimento_usado}`; `/v1/opcoes` traz `renda_referencia.fontes[]` (`item`, `fonte`, `periodo`/`estimativa`, `url`). Se o MapBiomas dos últimos 3 anos não indicar lavoura, entra um aviso.

### `GET /v1/clima`

Query: `lat` (obrigatório), `lon` (obrigatório), `semeadura_safrinha` (padrão `01/02`).
Saída: o bloco `clima` descrito acima.

## Como a nota é calculada

A nota de cada rotação (escala 0 a 1, com todos os critérios em escala absoluta 0 a 1) é a **média ponderada** dos 5 critérios pelos `pesos`:
`nota = soma(peso_i x criterio_i) / soma(peso_i)`. O campo `contribuicoes` mostra quanto cada
critério pesou, e `metodologia.formula` traz a fórmula exata da versão em execução. Pesos padrão: renda 5, demais 3. A lógica detalhada do motor está em [`docs/motor.md`](../docs/motor.md).

| Critério | Origem |
|---|---|
| `renda` | Margem **incremental** da 2ª safra (R$/ha) = rendimento (IBGE PAM do município) x preço - custo (SEAB/DERAL, CONAB) da 2ª cultura (cobertura/pousio: - custo) + bônus de palhada/N na soja seguinte; a soja, comum a todas, fica de fora. Nota = `clip(0,5 + incremental / (2·S), 0, 1)`, com S = max(margem da soja do município, R$ 1.000/ha): incremental +S = 1,0; zero = 0,5; -S = 0. `margem.total_r_ha` (soja + incremental), `incremental_r_ha` e `escala_S_r_ha` aparecem no ranking; `ano_ruim_r_ha` mostra o cenário adverso |
| `solo` | SoilGrids (textura, matéria orgânica), efeito da cobertura/palhada e da braquiária/leguminosa; relevo (NASADEM) para erosão |
| `agua` | NASA POWER: balanço precipitação - ET0, início das chuvas, veranico na safrinha |
| `pragas` | Histórico de cultivo (MapBiomas) e quebra de ciclo de pragas/doenças pela rotação |
| `risco` | NASA POWER: probabilidade de geada (por data de semeadura) e veranico, calor para soja |

**Regras duras (eliminam a opção, sem nota):** vazio sanitário da soja (02/06 a 31/08), janela de
plantio da soja (01/09 a 31/12) e proibição de soja sobre soja. As opções vetadas aparecem em
`eliminadas[]` com os motivos.

**O que é estimativa:** produtividade (média municipal do PAM, não do talhão), margens e preços
(referências regionais; use `ajustes` com os valores reais), efeitos agronômicos de solo e pragas
e a rotação detectada pelo histórico de satélite. Devem ser validados com o agrônomo; o ZARC
continua sendo a referência para crédito rural.

## Exemplos

### Talhão demo

```bash
curl -s localhost:8000/v1/recomendacao -H 'content-type: application/json' \
  -d '{"area": {"talhao_id": "72638"}, "semeadura_safrinha": "01/02"}'
```

```python
import httpx
r = httpx.post("http://localhost:8000/v1/recomendacao",
               json={"area": {"talhao_id": "72638"}}, timeout=120)
r.raise_for_status()
for item in r.json()["ranking"]:
    print(item["posicao"], item["rotacao"], item["nota"])
```

### Polígono GeoJSON

```bash
curl -s localhost:8000/v1/recomendacao -H 'content-type: application/json' -d '{
  "area": {"geometry": {"type": "Polygon", "coordinates": [[[-53.46,-24.96],[-53.45,-24.96],[-53.45,-24.95],[-53.46,-24.95],[-53.46,-24.96]]]}},
  "semeadura_safrinha": "15/02"}'
```

```python
poligono = {"type": "Polygon", "coordinates": [[[-53.46, -24.96], [-53.45, -24.96],
            [-53.45, -24.95], [-53.46, -24.95], [-53.46, -24.96]]]}
r = httpx.post("http://localhost:8000/v1/recomendacao",
               json={"area": {"geometry": poligono}, "semeadura_safrinha": "15/02"}, timeout=120)
```

### Ponto lat/lon

```bash
curl -s localhost:8000/v1/recomendacao -H 'content-type: application/json' \
  -d '{"area": {"lat": -24.95, "lon": -53.45}}'
curl -s 'localhost:8000/v1/clima?lat=-24.95&lon=-53.45&semeadura_safrinha=01/03'
```

```python
r = httpx.post("http://localhost:8000/v1/recomendacao",
               json={"area": {"lat": -24.95, "lon": -53.45}}, timeout=120)
clima = httpx.get("http://localhost:8000/v1/clima",
                  params={"lat": -24.95, "lon": -53.45}).json()
```

### Pesos personalizados

```bash
curl -s localhost:8000/v1/recomendacao -H 'content-type: application/json' -d '{
  "area": {"talhao_id": "72638"},
  "pesos": {"renda": 9, "solo": 2, "agua": 3, "pragas": 4, "risco": 6},
  "rotacao_atual": "milho_safrinha", "n_alternativas": 4}'
```

```python
corpo = {"area": {"talhao_id": "72638"},
         "pesos": {"renda": 9, "solo": 2, "agua": 3, "pragas": 4, "risco": 6},
         "rotacao_atual": "milho_safrinha"}
r = httpx.post("http://localhost:8000/v1/recomendacao", json=corpo, timeout=120)
```

### Preços próprios

```bash
curl -s localhost:8000/v1/recomendacao -H 'content-type: application/json' -d '{
  "area": {"talhao_id": "72638"},
  "ajustes": {"precos": {"soja": 125, "milho": 58, "trigo": 82}, "linha_custo": "cot"}}'
```

```python
corpo = {"area": {"talhao_id": "72638"},
         "ajustes": {"precos": {"soja": 125, "milho": 58, "trigo": 82},
                     "custos": {"milho": 3200}, "linha_custo": "cot"}}
r = httpx.post("http://localhost:8000/v1/recomendacao", json=corpo, timeout=120)
```

### Exemplo de resposta

Trecho real de `POST /v1/recomendacao` para o talhão 72638 (resumido: só o 1º do ranking, 1 item por lista; resposta completa em `api/exemplos/recomendacao_talhao_72638.json`; demais respostas reais na mesma pasta):

```json
{
  "entrada": {
    "semeadura_safrinha": "01/02",
    "pesos": {
      "renda": 5.0,
      "solo": 3.0,
      "agua": 3.0,
      "pragas": 3.0,
      "risco": 3.0
    },
    "rotacao_atual": "milho_safrinha",
    "ajustes": {},
    "n_alternativas": 3
  },
  "ranking": [
    {
      "posicao": 1,
      "id": "milho_braquiaria",
      "rotacao": "Soja → milho safrinha + braquiária",
      "nota": 0.814,
      "atual": false,
      "criterios": {
        "renda": 0.977,
        "solo": 0.711,
        "agua": 0.844,
        "pragas": 0.65,
        "risco": 0.779
      },
      "contribuicoes": {
        "renda": 0.287,
        "solo": 0.125,
        "agua": 0.149,
        "pragas": 0.115,
        "risco": 0.137
      },
      "margem": {
        "total_r_ha": 2116.0,
        "incremental_r_ha": 1033.0,
        "escala_S_r_ha": 1083.0,
        "itens": [
          {
            "cultura": "Soja",
            "rendimento_sc_ha": 49.2,
            "preco": 120.14,
            "custo": 4824.0,
            "margem_r_ha": 1083.0,
            "fonte": "rendimento IBGE PAM (Toledo, 2021–2025); preço SEAB/DERAL-PR, média PR nov/25 a out/26; custo CONAB Londrina-PR, safra 2026/27 (est. mar/2026), custo variável (≈COE)"
          },
          {
            "cultura": "Milho 2ª safra",
            "rendimento_sc_ha": 103.0,
            "preco": 53.89,
            "custo": 4678.0,
            "margem_r_ha": 873.0,
            "fonte": "rendimento IBGE PAM (Toledo, 2021–2025); preço SEAB/DERAL-PR, média PR nov/25 a out/26; custo CONAB Londrina-PR, 2ª safra 2026 (est. mar/2026), custo variável (≈COE)"
          },
          {
            "cultura": "Braquiária em consórcio",
            "rendimento_sc_ha": null,
            "preco": null,
            "custo": 200.0,
            "margem_r_ha": -200.0,
            "fonte": "custo estimativa de referência, validar (sem venda)"
          }
        ],
        "ano_ruim_r_ha": 1478.0,
        "bonus_proxima_soja_r_ha": 360.0,
        "linha_custo": "coe"
      },
      "card": {
        "por_que": "Em relação à atual (milho safrinha): melhora a saúde do solo (0,71 contra 0,56; ~30 dias de solo descoberto contra 60), quebra melhor o ciclo de pragas (0,65 contra 0,50) e soma R$ 1.033/ha contra R$ 993/ha na 2ª safra (+4%). Risco climático igual (algum evento adverso em 22% dos anos). Maiores contribuições para a nota: Renda (0,29) e Água (0,15).",
        "evidencias": [
          "Dias de solo descoberto/ano (catálogo): ~30 dias."
        ],
        "beneficios": [
          "Boa cobertura/palha: protege o solo e reduz erosão."
        ],
        "lacunas": [
          "CAD por pedotransferência (Saxton & Rawls), pode errar em latossolos tropicais; fertilidade do solo não usada."
        ],
        "riscos": [
          "Fora do ZARC pode comprometer crédito/seguro (não elimina a candidata)."
        ],
        "avisos": []
      }
    }
  ],
  "ranking_demais": [
    [
      2,
      "milho_safrinha",
      0.757
    ],
    [
      3,
      "milheto_crotalaria",
      0.756
    ],
    [
      4,
      "aveia",
      0.698
    ],
    [
      5,
      "pousio",
      0.547
    ],
    [
      6,
      "trigo",
      0.466
    ]
  ],
  "eliminadas": [
    {
      "id": "soja_safrinha",
      "rotacao": "Soja → soja safrinha",
      "motivos": [
        "Soja sobre soja no mesmo ano agrícola é proibida (Portaria SDA/MAPA 1.124/2024).",
        "Há soja viva durante o vazio sanitário do Oeste do PR (02/06–31/08)."
      ]
    }
  ],
  "avisos": []
}
```

## Erros e códigos HTTP

| Código | `erro` | Quando |
|---|---|---|
| 200 | n/d | Sucesso |
| 400 | `entrada_invalida` | O motor rejeitou a entrada (geometria inválida, talhão inexistente, área acima de 5000 ha etc.) |
| 422 | n/d (`detail[]`) | Chave desconhecida em `ajustes.custos`/`precos`, valor negativo etc. também são barrados na validação |
| 422 | `fora_da_regiao` | A área está fora do Oeste do PR |
| 422 | n/d (formato padrão do FastAPI, `detail[]`) | Corpo/parâmetros inválidos: semeadura fora do enum, peso fora de 0 a 10, rotação desconhecida, `n_alternativas` fora de 1 a 6, área com zero ou mais de uma forma |
| 500 | `interno` | Falha inesperada (o detalhe fica só no log do servidor) |

Erros do motor têm o formato `{"erro": "...", "mensagem": "..."}`.

## Limitações

- O clima vem do NASA POWER, em grade de ~50 km: talhões vizinhos compartilham a mesma célula.
- Produtividade, margens, efeitos agronômicos e rotação detectada são **estimativas** a validar.
- Preços e custos de referência vêm da CONAB (praça de Londrina) e SEAB/DERAL; use `ajustes` para os valores reais.
- Área máxima por requisição: 5000 ha.
- Cobertura apenas do Oeste do PR; o ZARC continua sendo a referência para crédito rural.
- Endpoints são síncronos e a primeira chamada pode ser lenta (carga de rasters e dados).
