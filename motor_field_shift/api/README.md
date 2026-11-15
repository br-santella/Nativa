# Field Shift API

API HTTP (FastAPI) do motor de recomendação de **rotação de culturas** do Field Shift. Dada uma área
(talhão demo, polígono GeoJSON ou ponto lat/lon), ela devolve um **diagnóstico** (relevo, solo,
histórico de cultivo, clima, produtividade) e um **ranking de rotações** com nota de 0 a 1, margem
estimada em R$/ha e um cartão explicativo por opção. Uma rotação é um par **(cultura de verão, cultura da
2ª janela)**: verão `soja` ou `milho_verao`; 2ª janela com 11 opções (7 originais + sorgo, feijão safrinha,
nabo forrageiro e aveia + nabo).

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

A API só lê arquivos locais (exceto `/v1/contexto`, que busca na hora e grava em `data/cache_contexto/`).
Conjunto mínimo: **~280 MB** (~275 MB em `.tar.gz`; o maior item é o `slope_pct.tif`, 150 MB).

| Arquivo | Tamanho | Usado em | Gerado por |
|---|---|---|---|
| `data/raw/regiao/oeste_pr.geojson` (+ `municipios_oeste_pr.geojson`) | 0,5 MB | recorte da região (422 fora dela) | `ingest/mapbiomas_relevo_oeste_pr.py` |
| `data/raw/mapbiomas_oeste_pr/coverage_*.tif` | 35 MB | histórico de uso do solo | `ingest/mapbiomas_relevo_oeste_pr.py` |
| `data/raw/nasadem_oeste_pr/elev.tif` | 28 MB | relevo (altitude) | `ingest/mapbiomas_relevo_oeste_pr.py` ¹ |
| `data/processed/relevo_oeste_pr/slope_pct.tif` | 150 MB | relevo (declividade) | `ingest/mapbiomas_relevo_oeste_pr.py` ¹ |
| `data/processed/ftw/mapbiomas_legend_c10.json` | 4 KB | nomes das classes MapBiomas | `src/field_shift/mapbiomas/join_fields.py` |
| `data/processed/ftw/fields_tile_mapbiomas_geo.parquet` | 13 MB | talhão demo (geometria + histórico) | `src/field_shift/mapbiomas/join_fields.py` |
| `data/processed/ftw/candidatos_demo.geojson` | 32 KB | lista de talhões demo (`/v1/talhoes/demo`) | já existe; copiar de quem tem os dados |
| `data/processed/timelapse/ndvi_hls_<id>.csv` | 20 KB | rotação observada por NDVI (opcional: sem ele, usa só MapBiomas) | `ingest/timelapse_talhao.py` ¹ |
| `data/raw/clima/municipios_oeste_pr.geojson` | 0,1 MB | lookup de clima por município | `ingest/clima_oeste_pr.py` |
| `data/processed/clima/indicadores.parquet`, `indicadores_anuais.parquet` | 0,4 MB | clima e riscos por célula | `ingest/clima_oeste_pr.py` ¹ |
| `data/processed/clima/power_diario.parquet` | 15 MB | balanço hídrico diário | `ingest/clima_oeste_pr.py` ¹ |
| `data/raw/soilgrids_oeste_pr/*.tif` | 42 MB | solo (textura, CAD) | `ingest/solo_pam_oeste_pr.py` |
| `data/raw/ibge/pam_oeste_pr.parquet` | 4 MB | produtividade municipal (PAM): soja, milho (total, 1ª e 2ª safra), trigo, aveia | `ingest/solo_pam_oeste_pr.py` |
| `data/raw/ibge/pam_extra_oeste_pr.parquet` | 0,2 MB | PAM de sorgo e feijão 2ª safra (mesmo esquema; opcional: sem ele, sorgo e feijão usam rendimento sem PAM) | `ingest/pam_culturas_extra.py` |
| `data/ref/precos_custos.json` | 8 KB | preços e custos | versionado; atualizar com `uv run python -m field_shift.renda.atualizar` |
| `data/contexto/pragas_alertas.json` | 4 KB | `/v1/contexto` (pragas) | versionado, curado à mão |

¹ Exige credenciais Earthdata em `~/.netrc`.

`data/raw` e `data/processed` ficam fora do git. Numa máquina nova, rode as ingestões acima ou copie
esse conjunto mínimo de quem já tem os dados. Fora do Oeste do PR, o clima cai no NASA POWER ao vivo
(cache em `data/raw/power/`).

## Endpoints

| Método | Rota | Descrição |
|---|---|---|
| GET | `/health` | Estado do serviço e se os dados carregaram |
| GET | `/v1/opcoes` | Culturas de verão e da 2ª janela, combinações (rotações), semeaduras, critérios, pesos padrão, referências de renda, região, talhões demo |
| GET | `/v1/talhoes/demo` | Lista de talhões de demonstração |
| POST | `/v1/diagnostico` | Diagnóstico completo da área |
| POST | `/v1/recomendacao` | Ranking de rotações (e, opcionalmente, o diagnóstico) |
| GET | `/v1/clima` | Atalho: só o bloco `clima` do diagnóstico para um ponto |
| GET, POST | `/v1/contexto` | Situação atual (informativa): ENSO, umidade do solo SMAP, MJO, pragas em surto. Não altera ranking nem nota |

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

Sem entradas. `/opcoes` devolve:

- `culturas_verao[]` e `culturas_segunda[]`: `id`, `nome`, `tipo` (`grão`, `cobertura` ou `pousio`) e `descricao_curta`. São os enums fechados de `rotacoes`.
- `combinacoes[]`: todos os pares (22), com `id` (`"<verao>__<segunda>"`, ex.: `soja__milho_safrinha`), `id_legado` (slug antigo, só nas 7 originais),
  `nome`, `verao`, `segunda`, `valida` (false se o par é sempre eliminado, como soja na 2ª janela), `semeaduras_validas[]` (datas de semeadura da
  2ª cultura em que o par passa nas regras de calendário) e `motivo_se_invalida`.
- `rotacoes[]` (os mesmos 22 ids com nome e descrição curta), `semeaduras`, `semeadura_padrao`, `criterios`, `pesos_padrao`,
  `renda_referencia` (preços, custos e `fontes[]`, com `estimativa` marcada), `regiao`, `talhoes_demo`.

`/talhoes/demo` devolve só a lista `talhoes_demo`.

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
| `solo` | Atributos do SoilGrids (textura, carbono etc.) ou, se enviada `analise_solo`, da análise do produtor (`fonte`) |
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
| `rotacoes` | lista de `{"verao": <enum>, "segunda": <enum>}` | não | todas as combinações do catálogo | Se vier, o motor avalia e ranqueia **só essas**. Enums fechados (ver `/v1/opcoes`); lista não vazia e sem duplicatas, senão 422. Combinação eliminada pelas regras volta em `eliminadas` com motivo (não é erro). A nota de uma rotação não depende das outras avaliadas |
| `rotacao_atual` | id `"<verao>__<segunda>"` ou slug antigo | não | detectada/`soja__milho_safrinha` | Rotação usada hoje, para comparação (`atual`). Slug antigo = soja no verão (`milho_safrinha` = `soja__milho_safrinha`) |
| `ajustes.precos` | `{soja, milho, trigo, feijao, sorgo}` em R$/saca (>= 0) | não | referência | Preços próprios (`milho` vale para o verão e o safrinha) |
| `ajustes.custos` | `{cultura: R$/ha}`, chaves: `soja`, `milho` (alias de `milho_2safra`), `milho_2safra`, `milho_verao` (alias de `milho_1safra`), `milho_1safra`, `trigo`, `feijao` (alias de `feijao_2safra`), `feijao_2safra`, `sorgo`, `aveia`, `milheto_crotalaria`, `braquiaria_consorcio`, `pousio`, `nabo_forrageiro`, `aveia_nabo`; valores >= 0 | não | referência | Custos próprios (chave desconhecida é rejeitada) |
| `ajustes.linha_custo` | `coe`, `cot` ou `ct` | não | do serviço | Custo operacional efetivo, operacional total ou custo total |
| `ajustes.produtividade` | `{soja, milho, milho_2safra, milho_verao, trigo, feijao, sorgo}` em sc/ha (> 0; `milho` é alias de `milho_2safra`; `milho_verao` = milho 1ª safra) | não | PAM do município | Produtividade própria: substitui o rendimento PAM na margem; o ano ruim escala proporcionalmente (próprio × p20/média da PAM); a soja informada também muda a escala S. Fonte nos itens: "informado pelo produtor" |
| `analise_solo` | `{argila_pct, areia_pct, materia_organica_pct` ou `carbono_organico_g_kg, ph, cad_mm_cm, profundidade_cm}` | não | SoilGrids | Análise de solo do produtor. Exige argila+areia (soma <= 100) ou `cad_mm_cm`. Faixas: percentuais 0 a 100, pH 3 a 9, CAD 0,3 a 3 mm/cm. Com `cad_mm_cm`, a CAD é usada direto; senão, Saxton & Rawls com os valores informados (sem MO na análise, usa a do SoilGrids, com aviso). `profundidade_cm` (padrão 20) só descreve a amostra, tomada como representativa do perfil. Substitui o SoilGrids no `solo` e no balanço hídrico; `solo.fonte` = "análise de solo do produtor" |
| `restricoes.culturas_excluidas` | lista de ids `"<verao>__<segunda>"` ou slugs antigos (= soja no verão) | não | nenhuma | Vão para `eliminadas` com o motivo "Excluída pelo produtor." |
| `restricoes.maquinas` | `{plataforma_milho, semeadora_consorcio}` (bool) | não | tem tudo | Milho verão, milho safrinha e milho+braquiária exigem plataforma de milho (um custo por colheita); milho+braquiária exige também semeadora de consórcio. `false` NÃO elimina: aviso no card e custo extra de terceirização na margem (R$ 250/ha por colheita e R$ 80/ha, estimativas a validar) |
| `restricoes.sem_comprador` | lista de `milho`, `trigo`, `sorgo`, `feijao`, `aveia_grao` | não | nenhuma | Elimina as rotações que dependem da venda (milho: verão, safrinha e consórcio; trigo; sorgo; feijão). `aveia_grao` é aceito, mas sem efeito: a aveia é tratada como cobertura, sem venda |
| `irrigacao` | `{disponivel (obrigatório), custo_r_mm_ha (padrão 4,0), lamina_max_mm_dia (padrão 6)}` | não | sequeiro | Irriga milho, milho+braquiária, trigo, sorgo e feijão da 2ª janela (não cobertura, pousio nem o verão) quando a depleção passa de p (0,55; feijão 0,45), até a capacidade, limitado pela lâmina diária. Água sobe, veranico não conta no risco (a geada continua), a margem desconta lâmina × custo. O ganho de produtividade não é modelado |
| `n_alternativas` | inteiro 1 a 6 | não | `3` | Quantas alternativas devolver |
| `incluir_diagnostico` | bool | não | `true` | Inclui o bloco `diagnostico` |

**Rotação, ids e catálogo.** `verao`: `soja`, `milho_verao`. `segunda`: `milho_safrinha`, `milho_braquiaria`, `trigo`, `aveia`,
`milheto_crotalaria`, `pousio`, `soja_safrinha`, `sorgo`, `feijao_safrinha`, `nabo_forrageiro`, `aveia_nabo`. O id é
`"<verao>__<segunda>"` (ex.: `soja__milho_safrinha`, `milho_verao__aveia_nabo`). Os slugs antigos seguem aceitos em `rotacao_atual` e
`restricoes.culturas_excluidas` e valem para soja no verão (`milho_safrinha` = `soja__milho_safrinha`; só os 7 originais); nas respostas o
`id` é sempre o novo e `id_legado` traz o slug antigo (nulo nas rotações novas). `rotacao_detectada.rotacao` (em `/diagnostico`) continua
devolvendo o slug antigo.

**Regras de calendário e legais** (eliminam a rotação, com motivo legível em `eliminadas`):

- Soja na 2ª janela é sempre eliminada: soja só pode ser semeada de 01/09 a 31/12, há vazio sanitário de 02/06 a 31/08 e, depois de soja, é soja sobre soja
  (proibida). Vale inclusive depois de `milho_verao`.
- A 2ª cultura que segue a data de semeadura escolhida (milho safrinha, milho+braquiária, sorgo, feijão, milheto/crotalária) só pode ser semeada
  depois da colheita do verão: soja ~10/01, milho verão ~05/02 (estimativas, validar). Por isso, com `semeadura_safrinha` 01/02 ou antes,
  milho verão seguido dessas culturas é eliminado. Trigo, aveia, nabo e pousio têm data fixa e não dependem da colheita.
- Feijão safrinha só aceita semeadura de 15/01 a 28/02, e sorgo de 15/01 a 15/03 (estimativas de referência com base no ZARC/IDR-PR, validar).
- **Milho sobre milho** (`milho_verao` + `milho_safrinha` ou `milho_braquiaria`) **não é eliminado**: o critério `pragas` perde 0,25 ponto
  (cigarrinha-do-milho/enfezamento, lagarta-do-cartucho; estimativa), e o texto entra em `card.riscos` e `card.evidencias`.
- **Milho verão no lugar da soja** soma 3 sc/ha de bônus na soja seguinte (quebra de ciclo de doença e nematoide, mais palhada; estimativa de
  referência a validar), além do bônus de palhada/N da 2ª cultura.

**Renda do verão.** A margem da rotação é verão + 2ª cultura + bônus. A nota usa o incremental sobre a soja de verão do município:
`incremental = margem da rotação − margem da soja`, `renda = clip(0,5 + incremental / (2·S), 0, 1)`, com S = max(margem da soja, R$ 1.000/ha).
Com soja no verão a fórmula é a de sempre; milho verão entra com PAM de milho 1ª safra × preço DERAL do milho − custo CONAB do milho 1ª safra
(Ponta Grossa-PR, a única planilha PR atual; usa produtividade de referência de 12 t/ha, acima da do Oeste, então a margem do milho verão tende a ser subestimada).
O verão não entra nos critérios de água e risco climático (só a 2ª janela).

Saída:

| Campo | Descrição |
|---|---|
| `entrada` | Eco da entrada efetivamente usada (pesos, ajustes, semeadura, `rotacao_atual` como id novo e, se enviados, `rotacoes`, `analise_solo`, `restricoes`, `irrigacao` com padrões preenchidos) |
| `diagnostico` | Igual ao de `/v1/diagnostico` (se `incluir_diagnostico`) |
| `ranking[]` | `posicao`, `id` (`"<verao>__<segunda>"`), `id_legado`, `verao{id,nome}`, `segunda{id,nome}`, `rotacao`, `nota` (0 a 1), `atual`, `criterios{renda,solo,agua,pragas,risco}`, `contribuicoes{}`, `margem{total_r_ha, incremental_r_ha, escala_S_r_ha, itens[{cultura, rendimento_sc_ha, preco, custo, margem_r_ha, fonte}], ano_ruim_r_ha}`, `card{por_que, evidencias, beneficios, lacunas, riscos, avisos, mercado{nivel, texto, estimativa}}`, `irrigacao{lamina_media_mm_ano, custo_r_ha}` (só nas candidatas irrigadas) |
| `atual` | Item da rotação atual (quando informada). Se ela for eliminada por regra dura (soja na 2ª janela, milho verão antes da colheita etc.), vem com `posicao` e `nota` nulos, `eliminada: true` e `motivos[]`, e não aparece em `ranking`/`alternativas`. Com `rotacoes` que não a inclui, vem com `avaliada: false` (e `null` se ela nem foi informada nem detectada). Sem `rotacao_atual`, o motor detecta: só o talhão 72638 tem detecção por NDVI; nos demais assume `soja__milho_safrinha` com aviso |
| `alternativas[]` | Itens alternativos à rotação atual |
| `eliminadas[]` | Rotações vetadas por regra dura, calendário ou restrição: `id`, `id_legado`, `verao`, `segunda`, `rotacao`, `motivos[]` |
| `avisos[]` | Alertas gerais |
| `metodologia` | `formula`, `criterios{}`, `versao` e, se houver ajustes, `ajustes_aplicados[]` (uma frase por ajuste) |

Os números saem arredondados (`nota`, `criterios` e `contribuicoes` com 3 casas; R$ sem casas; probabilidades com 3 casas); o ranking usa a nota sem arredondar. `card.por_que` compara cada alternativa com a rotação atual (até 3 critérios de maior diferença ponderada, com números); no item da atual diz a posição e a melhor alternativa.

Campos extras úteis: `margem.bonus_proxima_soja_r_ha` e `margem.linha_custo`; `clima.textos`; `rotacao_detectada.picos_por_ano_agricola`; `relevo.texto`; `solo.texto`, `p30`, `prof`, `cad_mm_cm`, `cad_mm_0_30`, `cad_mm_0_60`, `classe_textura`, `cad_metodo`; `produtividade{municipio, cod_ibge, fonte, culturas, texto, rendimento_usado}`; `/v1/opcoes` traz `renda_referencia.fontes[]` (`item`, `fonte`, `periodo`/`estimativa`, `url`). Se o MapBiomas dos últimos 3 anos não indicar lavoura, entra um aviso.

Exemplo com dados próprios (resposta real em `api/exemplos/recomendacao_dados_proprios.json`):

```json
{
  "area": {"talhao_id": "72638"},
  "ajustes": {"produtividade": {"soja": 65, "milho": 110, "trigo": 50}},
  "analise_solo": {"argila_pct": 65, "areia_pct": 10, "materia_organica_pct": 3.5, "ph": 5.4, "cad_mm_cm": 1.4},
  "restricoes": {"culturas_excluidas": ["trigo"],
                 "maquinas": {"plataforma_milho": true, "semeadora_consorcio": false},
                 "sem_comprador": ["aveia_grao"]},
  "irrigacao": {"disponivel": true}
}
```

`POST /v1/diagnostico` também aceita `analise_solo`. Se as restrições eliminarem todas as rotações avaliadas por padrão (sem `rotacoes`), a resposta é 400
(`entrada_invalida`); com `rotacoes`, a resposta é 200 com `ranking` vazio e tudo em `eliminadas`.

#### Rotações passadas pelo usuário (`rotacoes`)

Requisição (resposta real em `api/exemplos/recomendacao_rotacoes.json`; com semeadura 01/03, o milho verão já foi colhido):

```json
{
  "area": {"talhao_id": "72638"},
  "semeadura_safrinha": "01/03",
  "rotacao_atual": "soja__milho_safrinha",
  "rotacoes": [
    {"verao": "soja", "segunda": "milho_safrinha"},
    {"verao": "soja", "segunda": "sorgo"},
    {"verao": "milho_verao", "segunda": "aveia_nabo"},
    {"verao": "milho_verao", "segunda": "milho_safrinha"},
    {"verao": "milho_verao", "segunda": "soja_safrinha"}
  ]
}
```

Resposta (resumida): 4 rotações no ranking e a soja na 2ª janela em `eliminadas`, sem erro.

```json
{
  "ranking": [
    {"posicao": 1, "id": "soja__milho_safrinha", "id_legado": "milho_safrinha", "nota": 0.715, "atual": true},
    {"posicao": 2, "id": "soja__sorgo", "id_legado": null, "nota": 0.596, "atual": false},
    {"posicao": 3, "id": "milho_verao__aveia_nabo", "id_legado": null, "nota": 0.576, "atual": false},
    {"posicao": 4, "id": "milho_verao__milho_safrinha", "id_legado": null, "nota": 0.389, "atual": false,
     "criterios": {"pragas": 0.25},
     "card": {"riscos": ["... Milho sobre milho (milho verão + milho safrinha): mantém hospedeiro contínuo da cigarrinha-do-milho (Dalbulus maidis) e do enfezamento ..."]}}
  ],
  "eliminadas": [
    {"id": "milho_verao__soja_safrinha", "rotacao": "Milho verão → soja safrinha",
     "motivos": ["Soja na 2ª janela (semeadura em 01/03) fica fora da janela legal de semeadura da soja (01/09–31/12).",
                 "Há soja viva durante o vazio sanitário do Oeste do PR (02/06–31/08)."]}
  ]
}
```

Lista vazia, combinações duplicadas, valor fora do enum ou campos extras em `rotacoes` respondem **422** de validação.

### `GET /v1/clima`

Query: `lat` (obrigatório), `lon` (obrigatório), `semeadura_safrinha` (padrão `01/02`).
Saída: o bloco `clima` descrito acima.

### `GET /v1/contexto` e `POST /v1/contexto`

Camada de **situação atual**: consulta fontes oficiais sobre eventos em curso e devolve como contexto. **Não prevê nada e não muda
ranking nem nota** (a recomendação não depende dela e nunca falha por causa dela). `GET`: query `talhao_id` **ou** `lat`+`lon`,
`semeadura_safrinha` (padrão `01/02`). `POST`: corpo `{"area": {...}, "semeadura_safrinha": "01/02"}` (aceita também `geometry`;
usa o centroide). Mesmos erros da recomendação (400, 422 `fora_da_regiao`). Demora: chamada fria até ~40 s (SMAP); com cache, instantânea.

Cada fonte vem em um bloco próprio com `disponivel`, `consultado_em` (UTC) e `fonte` (`nome`, `url`). Se uma fonte falha, só aquele
bloco vira `{"disponivel": false, "motivo": "..."}` e o resto continua. Blocos:

| Bloco | Fonte | Cache | Conteúdo |
|---|---|---|---|
| `enso` | NOAA CPC (página do ENSO Diagnostic Discussion + tabela ONI) | 24 h | `status_alerta`, `fase_atual`, `oni_ultimo`, `boletim.sinopse_original_en` (percentuais citados pela NOAA), `texto`; `historico_por_fase` (anos 1991-2024 classificados pelo ONI do DJF; por fase: `n_anos`, `anos_com_evento`, `frequencia` de veranico no safrinha, geada no safrinha na semeadura escolhida e geada no trigo, mais `frequencia_media_geral`) e `frases_historico` |
| `smap` | NASA SMAP L4 (SPL4SMGP v8), pixel de ~9 km, via Earthdata (`~/.netrc`) | 24 h | `atual` (umidade da zona de raízes e da superfície, `sm_rootzone_pctl` = percentil na climatologia SMAP), `classe` (abaixo/normal/acima), `ha_7_dias`, `tendencia_7d_percentil`. Latência do produto: 2 a 3 dias |
| `mjo` | NOAA PSL, índice ROMI (OLR) | 6 h | fase RMM (1-8, só se amplitude >= 1), amplitude, frase curta sem previsão |
| `pragas.ferrugem_soja` | IDR-PR, WFS público do GeoServer do Estado (automático) | 24 h | coletores com/sem esporos no município, na mesorregião Oeste e num raio de 100 km, na safra atual |
| `pragas.alertas_curados` | `data/contexto/pragas_alertas.json` (curado à mão: cigarrinha-do-milho e outros alertas ADAPAR/IDR-PR) | lido a cada chamada | alertas vigentes por região, com texto atribuído à fonte; `como_consultar` com links (CigarrinhaWeb, ADAPAR) |
| `alertas_inmet` | INMET | n/d | **não implementado** (feed inacessível daqui; `disponivel: false` com o motivo) |

O cache fica em `data/cache_contexto/` (fora do git). Exemplo real: `api/exemplos/contexto_talhao_72638.json`.

```bash
curl -s 'localhost:8000/v1/contexto?talhao_id=72638&semeadura_safrinha=01/02'
```

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
    "rotacao_atual": "soja__milho_safrinha",
    "ajustes": {},
    "n_alternativas": 3
  },
  "ranking": [
    {
      "posicao": 1,
      "id": "soja__milho_braquiaria",
      "id_legado": "milho_braquiaria",
      "verao": {"id": "soja", "nome": "Soja"},
      "segunda": {"id": "milho_braquiaria", "nome": "Milho safrinha + braquiária"},
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
    [2, "soja__milho_safrinha", 0.757],
    [3, "soja__milheto_crotalaria", 0.756],
    [4, "soja__aveia_nabo", 0.709]
  ],
  "eliminadas": [
    {
      "id": "soja__soja_safrinha",
      "id_legado": "soja_safrinha",
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
| 400 | `entrada_invalida` | O motor rejeitou a entrada (geometria inválida, talhão inexistente, área acima de 5000 ha, restrições que eliminam todas as rotações etc.) |
| 422 | n/d (`detail[]`) | Chave desconhecida em `ajustes.custos`/`precos`/`produtividade`, valor negativo, `analise_solo` fora das faixas (areia + argila > 100, pH, CAD) ou incompleta, `irrigacao` sem `disponivel` etc. também são barrados na validação |
| 422 | `fora_da_regiao` | A área está fora do Oeste do PR |
| 422 | n/d (formato padrão do FastAPI, `detail[]`) | Corpo/parâmetros inválidos: semeadura fora do enum, peso fora de 0 a 10, rotação desconhecida, `rotacoes` vazia, duplicada ou com valor fora do enum, `n_alternativas` fora de 1 a 6, área com zero ou mais de uma forma |
| 500 | `interno` | Falha inesperada (o detalhe fica só no log do servidor) |

Erros do motor têm o formato `{"erro": "...", "mensagem": "..."}`.

## Limitações

- O clima vem do NASA POWER, em grade de ~50 km: talhões vizinhos compartilham a mesma célula.
- Produtividade, margens, efeitos agronômicos e rotação detectada são **estimativas** a validar.
- Preços e custos de referência vêm da CONAB (Londrina para soja e milho safrinha, Ponta Grossa para trigo e milho verão, Francisco Beltrão para feijão) e SEAB/DERAL; use `ajustes` para os valores reais.
- Sem fonte oficial, os valores são estimativas marcadas como "estimativa — validar" em `data/ref/precos_custos.json`: preço do sorgo (80% do milho DERAL),
  custo do sorgo (planilha CONAB de Rio Verde-GO, não há do PR) e custo de nabo forrageiro, aveia + nabo, aveia, milheto/crotalária, braquiária e pousio.
  Também são estimativas: Kc e fase crítica das culturas novas, janelas de semeadura, datas de colheita do verão, bônus de rotação e penalidade de milho sobre milho.
- Área máxima por requisição: 5000 ha.
- Entradas de dados próprios: custos de terceirização, custo/lâmina da irrigação e níveis de mercado por cultura são estimativas a validar. A irrigação não eleva o rendimento esperado. A análise de solo (padrão 0 a 20 cm) é tomada como representativa de todo o perfil de raiz.
- Exemplo completo: `api/exemplos/recomendacao_dados_proprios.json` (talhão 72638 com produtividade, análise de solo, restrições e irrigação).
- Cobertura apenas do Oeste do PR; o ZARC continua sendo a referência para crédito rural.
- Endpoints são síncronos e a primeira chamada pode ser lenta (carga de rasters e dados).
