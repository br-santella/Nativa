# Field Shift — Arquitetura de dados e do app

Como o motor obtém cada dado, como os módulos se encaixam e o que fica em disco.

## 1. Origem de cada dado

| Dado | Como é obtido | Arquivo / fonte | Gerado por |
|---|---|---|---|
| Clima (indicadores NASA POWER) | Pré-calculado por célula da grade (~0,5° × 0,625°) e por município; consulta por lat/lon | `data/processed/clima/indicadores.parquet`, `indicadores_anuais.parquet` | `ingest/clima_oeste_pr.py` |
| Clima diário (balanço hídrico) | Pré-calculado | `data/processed/clima/power_diario.parquet` | `ingest/clima_oeste_pr.py` |
| Clima sem célula pré-calculada | NASA POWER ao vivo, com cache em disco | `data/raw/power/power_<lat>_<lon>.json` | `app/engine.py:buscar_power()` |
| MapBiomas (histórico de uso, 2019–2024) | Raster local recortado para o Oeste do PR | `data/raw/mapbiomas_oeste_pr/coverage_*.tif` | `ingest/mapbiomas_relevo_oeste_pr.py` |
| NASADEM (altitude e declividade) | Raster local; declividade pré-calculada | `data/raw/nasadem_oeste_pr/elev.tif`, `data/processed/relevo_oeste_pr/slope_pct.tif` | `ingest/mapbiomas_relevo_oeste_pr.py` |
| SoilGrids (textura, C orgânico, pH) | Raster local; API REST do SoilGrids 2.0 quando o raster não cobre a área | `data/raw/soilgrids_oeste_pr/*.tif` | `ingest/solo_pam_oeste_pr.py` |
| IBGE PAM (produtividade municipal) | Tabela local | `data/raw/ibge/pam_oeste_pr.parquet`, `pam_extra_oeste_pr.parquet` | `ingest/solo_pam_oeste_pr.py`, `ingest/pam_culturas_extra.py` |
| Preços e custos | Tabela local versionada | `data/ref/precos_custos.json` | `python -m field_shift.renda.atualizar` |
| NDVI / HLS (rotação detectada) | Série pré-calculada; existe só para o talhão 72638 | `data/processed/timelapse/ndvi_hls_<id>.csv` | `ingest/timelapse_talhao.py` |
| Talhões demo (FTW) | Geometrias e histórico locais | `data/processed/ftw/fields_tile_mapbiomas_geo.parquet`, `candidatos_demo.geojson` | `src/field_shift/mapbiomas/join_fields.py` |
| Região (recorte do Oeste do PR) | GeoJSON local | `data/raw/regiao/oeste_pr.geojson` | `ingest/mapbiomas_relevo_oeste_pr.py` |
| Regras legais e calendário | Código | `src/field_shift/calendario.py`, `app/engine.py` | — |
| Contexto atual (ENSO, SMAP, MJO, pragas, alertas INMET) | Consulta ao vivo em `/v1/contexto`, com cache em disco por TTL (ENSO, SMAP e pragas 24 h; MJO 6 h; alertas 30 min) | `data/cache_contexto/`; pragas curadas em `data/contexto/pragas_alertas.json` | `src/field_shift/contexto/` |

`data/raw/` e `data/processed/` não são versionados. A lista com tamanhos está em [`../api/README.md`](../api/README.md).

## 2. Fluxo

```
[ingest/ (offline)]                     [data/ (disco)]                    [API]
 POWER 1991–2025 → indicadores  ──►  parquet de clima        ─┐
 MapBiomas, NASADEM, SoilGrids  ──►  GeoTIFF recortados       │
 IBGE PAM                       ──►  parquet de PAM           ├─► servico.py ──► FastAPI ──► cliente
 HLS NDVI (talhão demo)         ──►  CSV por talhão           │   diagnosticar()
                                     precos_custos.json      ─┘   recomendar()
 NOAA, NASA SMAP, IDR-PR/ADAPAR ──── ao vivo + cache ──────────►  /v1/contexto
```

Núcleo: `diagnosticar(area)` devolve relevo, solo, histórico, rotação detectada, clima e produtividade; `recomendar(area, ...)` usa o mesmo contexto e devolve o ranking. Cada módulo de dados recebe o polígono (ou lat/lon) e devolve um dict.

## 3. Módulos

```
src/field_shift/
  motor/      servico.py: opcoes(), diagnosticar(), recomendar(), aquecer()
  app/        engine.py: regras duras, critérios, nota, cards; mvp.py: app Streamlit
  calendario.py  datas de semeadura e colheita, regras de calendário
  clima/      lookup.py (indicadores por lat/lon), indicadores.py, inmet.py (validação), validacao.py
  regiao/     recorte.py: região, histórico MapBiomas, relevo
  solo/       solo.py: SoilGrids no polígono, CAD (Saxton & Rawls), análise do produtor
  agua/       balanco.py: balanço hídrico diário FAO-56
  pam/        produtividade.py: rendimento municipal
  renda/      renda.py: margens; atualizar.py: atualização de preços e custos
  talhoes/    ndvi.py, relevo.py: séries por talhão
  mapbiomas/  join_fields.py: junção talhões × MapBiomas
  contexto/   enso.py, smap.py, mjo.py, pragas.py, alertas_inmet.py
  ftw/        busca e plot de cenas do Fields of The World
```

Lógica do motor: [`motor.md`](motor.md). Entradas do usuário: [`entradas.md`](entradas.md).
