# Field Shift — Arquitetura de dados e do app

Como os dados e o app são estruturados: o que é pré-calculado, o que é lido sob demanda e como os módulos se encaixam. Data: 2026-11-14. Piloto: soja → milho safrinha no Oeste do PR.

## 1. Princípio

Pré-calcular só o que é pesado de calcular. O que é só ler um pedaço de mapa é lido sob demanda.

## 2. Estratégia por dado

| Dado | Estratégia | Por quê |
|---|---|---|
| Clima (indicadores NASA POWER) | Pré-calculado, numa tabela por célula da grade (~0,5° × 0,625°) e por município | Cada indicador processa 35 anos de dados diários (1991–2025): ao vivo seriam segundos; pré-calculado é uma consulta de milissegundos. O Brasil inteiro dá ~3–4 mil células e poucas dezenas de MB |
| MapBiomas | Sob demanda, por leitura em janela de COG | Lê só o retângulo do polígono (~1 s). Hoje via source.coop (o bucket oficial dá 403); num app real, espelhar no próprio bucket |
| NASADEM (elevação/declividade) | Sob demanda, por COG; declividade calculada no recorte | Leitura de janela é barata e o cálculo da declividade só roda sobre o recorte |
| SoilGrids | Sob demanda, pela API | Consulta externa leve, sem necessidade de armazenar |
| SMAP (umidade atual) | Job diário por região; o app só lê o mais recente | O dado muda uma vez por dia e é igual para todos os usuários da região |
| NDVI / HLS (rotação detectada, solo descoberto) | Tarefa assíncrona (1–3 min) + cache por talhão | Processamento demorado demais para a requisição; o cache evita repeti-lo |
| Regras legais / ZARC | Tabela local | Dado pequeno e estático |
| FTW (limites de talhão) | Fora do fluxo por enquanto: o polígono vem do cliente (desenho no mapa/CAR) | O FTW fica só no tile da demo (talhão 72638) |

**Nota:** no hackathon, MapBiomas e NASADEM foram baixados recortados para o Oeste do PR inteiro, para funcionar offline durante o pitch. No app real eles viram leitura sob demanda.

## 3. Fluxo

```
[Pipeline offline / jobs]                  [Armazenamento]            [App]
 POWER 35 anos → indicadores clima  ──►  tabela indicadores   ─┐
 SMAP diário → umidade atual        ──►  tabela umidade        │
                                                               ├─► API  ──► Front (mapa)
 MapBiomas / NASADEM (COG)          ──►  bucket de COGs  ──────┤   "dado o polígono,
 SoilGrids (API externa)            ──────────────────────────┤    devolve diagnóstico
 HLS NDVI (tarefa assíncrona)       ──►  cache por talhão ─────┘    e ranking"
                                         Regras legais / ZARC (tabela local)
```

Núcleo: `diagnostico(poligono) → {clima, solo, relevo, historico, rotacao_detectada}` e depois `ranking(diagnostico, pesos)`. Cada fonte é um módulo com a mesma interface: recebe o polígono (ou lat/lon) e devolve um dict.

## 4. Módulos

```
src/field_shift/
  clima/     indicadores_para(lat, lon)        (em construção)
  regiao/    historico_mapbiomas(), relevo()   (em construção)
  solo/      soilgrids(poligono)               (a fazer)
  ndvi/      rotacao_detectada(poligono)       (hoje em talhoes/ndvi.py)
  regras/    regras duras + ZARC               (hoje dentro do engine.py)
  motor/     diagnostico() + ranking()         (sai do app/engine.py atual)
  app/       Streamlit (hackathon) → API FastAPI + front web
```

## 5. Espaço em disco (Oeste do PR)

Estimativa; atualizar com os números reais após os downloads.

| Conjunto | Tamanho estimado |
|---|---|
| POWER | ~150–250 MB de JSON bruto → ~20–40 MB em parquet |
| INMET | ~300–500 MB de CSV (zips de 1–2 GB apagados depois de extrair) → parquet diário com poucos MB |
| MapBiomas 2000–2024 | ~150–250 MB |
| NASADEM + declividade | ~150–250 MB |
| **Total** | **~0,7–1,2 GB, com pico de 2–3 GB no download** |

Em produção vai só a tabela de indicadores de clima (poucos MB) mais os rasters recortados (~300–500 MB), ou nada disso se ler os COGs sob demanda. O Paraná inteiro ≈ 9× isso.

## 6. Hackathon vs. app real

- **Até domingo (15/11/2026):** Streamlit + arquivos locais (parquet/GeoTIFF), sem infraestrutura, mas com módulos nas interfaces acima, para que trocar arquivo local por bucket/banco depois não mexa no motor.
- **App real:** FastAPI + PostGIS (ou parquet/DuckDB) + bucket de COGs + fila para o NDVI. Para expandir a outra região: rodar o pipeline de clima naquela grade e adicionar as regras legais do estado; MapBiomas e NASADEM já cobrem o Brasil.
- **Fora do escopo agora:** pecuária/gado e expansão do FTW.
- **Argumento para o pitch:** escala para o Brasil porque o pesado está pré-calculado e o resto é leitura sob demanda.

Lógica do motor: ver docs/motor.md

Entradas do usuário: ver docs/entradas.md
