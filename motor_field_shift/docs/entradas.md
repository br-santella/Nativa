# Field Shift — Entradas do usuário

O que o usuário informa, o que o app preenche sozinho e o que vale informar se ele tiver o dado. Campos da API conferidos em `api/README.md` e `api/field_shift_api/schemas.py`.

## Princípio

O produtor digita quase nada. O app puxa os dados públicos e ele só confirma ou ajusta. Toda entrada tem um valor de referência já preenchido, com fonte e período, e o usuário pode trocar pelo dele ("Usar meus valores"). Quanto mais dado próprio, mais preciso o resultado.

## 1. Entrada obrigatória: a área

Só `area` é obrigatória. Três formas (exatamente uma):

| Forma | Campo | Observação |
|---|---|---|
| Polígono desenhado no mapa (recomendado) | `area.geometry` | GeoJSON Polygon, MultiPolygon ou Feature, EPSG:4326 (lon, lat) |
| Ponto lat/lon | `area.lat` + `area.lon` | Vira um quadrado de ~100 ha, com aviso |
| ID de talhão demo | `area.talhao_id` | Ex.: `"72638"` (ver `GET /v1/talhoes/demo`) |

Restrições: dentro do Oeste do PR (50 municípios, IBGE 4106) e no máximo 5000 ha.

## 2. Entradas de escolha (têm padrão; o usuário clica, não digita)

| Entrada | Campo da API | Padrão | Efeito no resultado |
|---|---|---|---|
| Data de semeadura do safrinha (15/01, 01/02, 15/02, 01/03, 15/03) | `semeadura_safrinha` | 01/02 | Muda o risco de geada (de 6% a 76% no talhão 72638) e a água na floração |
| Prioridades (renda, solo, água, pragas, risco; 0 a 10) | `pesos` | renda 5, demais 3 | Pesam os 5 critérios na nota final |
| Rotação atual | `rotacao_atual` | Detectada por NDVI quando existe (hoje só no talhão 72638); senão, milho safrinha, com aviso | Referência de comparação. Opções: os slugs do catálogo (`GET /v1/opcoes`) |
| Número de alternativas | `n_alternativas` | 3 (a tela do Nativa usa 2) | Quantas alternativas voltam (1 a 6) |

Mapeamento dos sliders da tela do Nativa (0–100%) para `pesos` (0–10):

| Slider (Nativa) | Campo |
|---|---|
| Rentabilidade | `renda` |
| Saúde do solo | `solo` |
| Resiliência climática | `risco` |
| Economia de água | `agua` (o critério mede se a água atende a demanda da cultura na floração) |
| (sem slider) | `pragas` fica no padrão |

## 3. Preenchido automaticamente (o usuário só vê e confirma)

| Dado | Fonte | Período / resolução | Onde aparece |
|---|---|---|---|
| Clima e riscos (geada, veranico, calor, balanço hídrico) | NASA POWER, validado com INMET | 1991–2024, célula ~50 km | `diagnostico.clima` |
| Solo (argila, areia, C orgânico, pH, CAD) | SoilGrids | 250 m | `diagnostico.solo` |
| Relevo (altitude, declividade, classe Embrapa) | NASADEM | 30 m | `diagnostico.relevo` |
| Histórico de culturas | MapBiomas | 2019–2024 | `diagnostico.historico` |
| Município e produtividade média | IBGE PAM | Últimos 5 anos | `diagnostico.area.municipio`, `diagnostico.produtividade` |
| Preço | SEAB/DERAL-PR | Média de 12 meses | `ranking[].margem.itens[].preco` |
| Custo | CONAB COE (Londrina/Ponta Grossa) | Última safra | `ranking[].margem.itens[].custo` |
| Regras legais (vazio sanitário, soja sobre soja) | ADAPAR (vazio 02/06–31/08) e Portaria SDA/MAPA 1.124/2024 | Vigente | `eliminadas[]`, `avisos` |

## 4. Se o usuário tiver o dado, vale informar

Ordenado por impacto.

| Dado próprio | Substitui | Por que melhora | Campo da API |
|---|---|---|---|
| Custo de produção por cultura (R$/ha) | CONAB de Londrina | É o que mais varia entre fazendas | `ajustes.custos` (`soja`, `milho`/`milho_2safra`, `trigo`, `aveia`, `milheto_crotalaria`, `braquiaria_consorcio`, `pousio`) |
| Preço travado ou esperado (contrato, barter, cotação da cooperativa), R$/sc | Média de 12 meses do DERAL | Reflete o que ele realmente vai receber | `ajustes.precos` (`soja`, `milho`, `trigo`) |
| Linha de custo | `coe` (padrão) | Escolhe o que entra no custo | `ajustes.linha_custo` (`coe`, `cot`, `ct`) |
| Produtividade própria (sc/ha por cultura) | Média do município (ex.: 70 sc/ha contra 49 do IBGE) | A média municipal esconde a fazenda | `ajustes.produtividade` (`soja`, `milho`/`milho_2safra`, `trigo`; sc/ha > 0). O ano ruim escala proporcionalmente; a soja informada também muda a escala S da renda |
| Rotação atual e histórico real dos últimos anos | MapBiomas (só vê a cultura de verão) e NDVI (só existe no demo) | Rotação atual e histórico fiéis | `rotacao_atual`. O histórico detalhado dos últimos anos não é aceito |
| Data de semeadura que ele realmente usa | Padrão 01/02 | Risco de geada e água corretos | `semeadura_safrinha` |
| Análise de solo (argila, MO, pH, CAD) | SoilGrids e pedotransferência | CAD é a maior incerteza do critério água | `analise_solo` (topo): `argila_pct`, `areia_pct`, `materia_organica_pct` ou `carbono_organico_g_kg`, `ph`, `cad_mm_cm` (opcional), `profundidade_cm` (opcional, padrão 20). Exige argila+areia ou `cad_mm_cm`. Vale também em `POST /v1/diagnostico` |
| Polígono exato do talhão | Ponto (quadrado de ~100 ha) | Clima, solo e relevo do talhão certo | `area.geometry` |
| Restrições: culturas que não quer ou não tem como plantar/vender; máquinas (plataforma de milho, semeadora de consórcio); comprador local | Todas as candidatas liberadas | Só aparece o que ele consegue executar | `restricoes` (topo): `culturas_excluidas` (ids `<verao>__<segunda>` ou slugs antigos = soja no verão), `maquinas{plataforma_milho, semeadora_consorcio}`, `sem_comprador` (`milho`, `trigo`, `sorgo`, `feijao`, `aveia_grao`). Para avaliar só algumas rotações, use `rotacoes` (lista de `{verao, segunda}`; ver `docs/motor.md`). Excluída ou sem comprador elimina; máquina `false` só gera aviso e custo extra de terceirização. A viabilidade de mercado (alto/médio/baixo/não se aplica) aparece em `card.mercado` |
| Irrigação | Motor assume sequeiro | Muda o critério água | `irrigacao` (topo): `disponivel`, `custo_r_mm_ha` (padrão 4,0), `lamina_max_mm_dia` (padrão 6). Irriga milho, milho+braquiária e trigo; o veranico deixa de contar; a margem desconta lâmina × custo. Não modela ganho de produtividade |

## 5. Exemplos de requisição (`POST /v1/recomendacao`)

Mínimo (só a área):

```json
{ "area": { "talhao_id": "72638" } }
```

Completo (válido no schema atual):

```json
{
  "area": {
    "geometry": {
      "type": "Polygon",
      "coordinates": [[[-53.3045, -24.9045], [-53.2955, -24.9045], [-53.2955, -24.8955], [-53.3045, -24.8955], [-53.3045, -24.9045]]]
    }
  },
  "semeadura_safrinha": "15/02",
  "pesos": { "renda": 8, "solo": 3, "agua": 3, "pragas": 5, "risco": 4 },
  "rotacao_atual": "milho_safrinha",
  "ajustes": {
    "precos": { "soja": 125.0, "milho": 58.0, "trigo": 82.0 },
    "custos": { "soja": 4500.0, "milho_2safra": 4300.0 },
    "linha_custo": "cot"
  },
  "n_alternativas": 3
}
```
