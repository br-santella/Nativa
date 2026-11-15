# Field Shift — Bases de dados

Consolidação sem duplicatas de todas as bases citadas no desafio, no PDF de referência, nos recursos oficiais e nas fontes brasileiras discutidas. Links de acesso (coluna "Links") verificados em 2026-11-14 com `curl` (HTTP 200; alguns sites do USGS, JPL, CEPEA e IBGE devolvem 403 a clientes sem User-Agent de navegador, mas abrem normalmente no navegador).

## (a) NASA citados no desafio

| Dataset | Produto/versão | Resolução / revisita | Uso no Field Shift | Como acessar | Login | Links |
|---|---|---|---|---|---|---|
| NASA POWER | Arquivo "ag" (agroclimatologia), diário, desde 1981 | ~50 km; diário | Clima histórico do ponto, veranico, geada, balanço hídrico | POWER API (HTTP, JSON/CSV) | Não | [POWER API](https://power.larc.nasa.gov/docs/services/api/) · [Portal](https://power.larc.nasa.gov/) |
| SMAP L3 (superfície) | SPL3SMP_E, L3 Enhanced, V006 | 9 km; diário, desde 2015 | Umidade atual: "dá para plantar hoje?" | earthaccess, AppEEARS, NSIDC | Earthdata | [NSIDC SPL3SMP_E](https://nsidc.org/data/SPL3SMP_E) · [AppEEARS](https://appeears.earthdatacloud.nasa.gov/) |
| SMAP L4 (zona radicular) | SPL4SMGP, V8 (008); modelo que assimila SMAP | 9 km; 3 h, desde 2015 | Umidade na profundidade das raízes | earthaccess, AppEEARS, NSIDC | Earthdata | [NSIDC SPL4SMGP](https://nsidc.org/data/spl4smgp) · [AppEEARS](https://appeears.earthdatacloud.nasa.gov/) |
| ECOSTRESS | ECO_L2T_LSTE V002 (temperatura); L3 JET (ET) e L4 ESI | 70 m; irregular (ISS) | Estresse térmico e hídrico da lavoura | LP DAAC, AppEEARS | Earthdata | [Documentação ECOSTRESS](https://ecostress.jpl.nasa.gov/data/atbds-summary-table) · [LP DAAC](https://lpdaac.usgs.gov/products/eco_l2t_lstev002/) |
| GPM IMERG | GPM_3IMERGDF V07, Final, diário | 0,1° (~10 km); diário, desde 2000 | Chuva histórica e chuva intensa (erosão) | GES DISC, earthaccess, AWS | Earthdata | [GES DISC GPM_3IMERGDF](https://disc.gsfc.nasa.gov/datasets/GPM_3IMERGDF_07/summary) · [AWS Open Data](https://registry.opendata.aws/nasa-gpm3imergdf/) |
| Landsat 8/9 | Collection 2 Level-2 Surface Reflectance | 30 m; 8 dias | NDVI histórico por talhão, solo exposto | USGS EarthExplorer, Planetary Computer, GEE | USGS (EarthExplorer) / não (PC) | [USGS Collection 2 L2](https://www.usgs.gov/landsat-missions/landsat-collection-2-level-2-science-products) · [EarthExplorer](https://earthexplorer.usgs.gov/) |
| MODIS (vegetação) | MOD13Q1 v061, NDVI/EVI | 250 m; 16 dias, desde 2000 | Série longa de vigor e calendário da cultura | AppEEARS, LP DAAC, GEE | Earthdata | [LP DAAC MOD13Q1](https://lpdaac.usgs.gov/products/mod13q1v061/) · [Earth Engine](https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MOD13Q1) |
| VIIRS (vegetação) | Índices de vegetação VIIRS (produto a definir; só citado no enunciado/recursos) | 375–1000 m; diário/16 dias | Alternativa/continuidade do MODIS | Earthdata Search, AppEEARS | Earthdata | [LP DAAC VNP13A1](https://lpdaac.usgs.gov/products/vnp13a1v002/) · [Earthdata Search](https://search.earthdata.nasa.gov/) |
| MODIS (evapotranspiração) | MOD16A2GF v061, ET com preenchimento de falhas | 500 m; 8 dias, desde 2000 | Uso de água real da vegetação | AppEEARS, LP DAAC, GEE | Earthdata | [LP DAAC MOD16A2GF](https://lpdaac.usgs.gov/products/mod16a2gfv061/) · [Earth Engine](https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MOD16A2GF) |
| GRACE / GRACE-FO | JPL Mascon RL06.3Mv04 (água total) | ~300 km; mensal, desde 2002 | Tendência hídrica de longo prazo da região | GEE (JPL Mascon), PO.DAAC (CSR Land) | Earthdata (PO.DAAC) | [Earth Engine Mascon](https://developers.google.com/earth-engine/datasets/catalog/NASA_GRACE_MASS_GRIDS_V04_MASCON) · [PO.DAAC CSR Land](https://podaac.jpl.nasa.gov/dataset/TELLUS_GRFO_L3_CSR_RL06.3_LND_v04) |
| SRTM / NASADEM | NASADEM_HGT v001 (preferido) ou SRTMGL1 v003 | 30 m; estático | Declividade, erosão, baixadas sujeitas a geada | LP DAAC, earthaccess | Earthdata | [LP DAAC NASADEM](https://lpdaac.usgs.gov/products/nasadem_hgtv001/) · [LP DAAC SRTMGL1](https://lpdaac.usgs.gov/products/srtmgl1v003/) |
| GEDI | L4A V3, biomassa acima do solo por pegada | Pegadas de 25 m; amostral | Biomassa de mata vizinha; pouco útil p/ lavoura anual | ORNL DAAC | Earthdata | [ORNL DAAC GEDI L4A](https://daac.ornl.gov/GEDI/guides/GEDI_L4A_AGB_Density_V3.html) · [Dataset](https://daac.ornl.gov/cgi-bin/dsviewer.pl?ds_id=2056) |

## (b) Outros NASA úteis

| Dataset | Produto/versão | Resolução / revisita | Uso no Field Shift | Como acessar | Login | Links |
|---|---|---|---|---|---|---|
| HLS (Harmonized Landsat Sentinel-2) | HLSL30 / HLSS30 v2.0 (020) | 30 m; 2–3 dias | Melhor opção para NDVI por talhão e solo descoberto | LP DAAC, AppEEARS, Planetary Computer | Earthdata (PC: não) | [HLS (NASA)](https://hls.gsfc.nasa.gov/) · [LP DAAC HLSS30](https://lpdaac.usgs.gov/products/hlss30v002/) |
| OPERA | DSWx (água superficial) e DIST (perturbação da vegetação), a partir de HLS e radar | 30 m; poucos dias | Detecta colheita/solo exposto sem processar índice | Earthdata Search, PO.DAAC/LP DAAC | Earthdata | [OPERA (JPL)](https://www.jpl.nasa.gov/go/opera/) · [Earthdata Search](https://search.earthdata.nasa.gov/) |
| Crop-CASMA | Visualizador de umidade do solo SMAP p/ agricultura (USDA + GMU) | 1–9 km | Mapas de umidade e anomalia prontos (referência; cobertura EUA) | Web viewer | Não | [Crop-CASMA](https://cloud.csiss.gmu.edu/CropCASMA/) |
| NEX-GDDP-CMIP6 | Projeções climáticas diárias até 2100 | ~25 km; diário | Rotação em cenário futuro (slider de clima) | NCCS (THREDDS/AWS) | Não | [NCCS NEX-GDDP-CMIP6](https://www.nccs.nasa.gov/services/data-collections/land-based-products/nex-gddp-cmip6) |
| GLDAS / NLDAS | Modelo de superfície: umidade, ET, escoamento, temp. do solo (NLDAS só cobre América do Norte) | 25 km; 3 h (GLDAS) | Balanço hídrico completo pronto; usar GLDAS no Brasil | GES DISC, Earthdata Search | Earthdata | [GLDAS](https://ldas.gsfc.nasa.gov/gldas) · [NLDAS](https://ldas.gsfc.nasa.gov/nldas) |
| FLDAS | Variante do GLDAS para segurança alimentar | ~10 km; mensal | Indicadores de seca agrícola | GES DISC | Earthdata | [FLDAS](https://ldas.gsfc.nasa.gov/fldas) |
| EMIT | Espectro hiperespectral (285 bandas, 380–2500 nm) | 60 m; irregular (ISS) | Minerais do solo, palha × solo exposto; fora do MVP | LP DAAC | Earthdata | [EMIT (JPL)](https://earth.jpl.nasa.gov/emit/) · [LP DAAC EMITL2ARFL](https://lpdaac.usgs.gov/products/emitl2arflv001/) |

## (c) ESA, reanálises e outros internacionais

| Dataset | Produto/versão | Resolução / revisita | Uso no Field Shift | Como acessar | Login | Links |
|---|---|---|---|---|---|---|
| Copernicus Sentinel-2 | L2A (10–20 m; red-edge, NIR, SWIR) | 10–20 m; ~5 dias | NDVI/EVI, solo exposto, estresse; base dos limites de talhão FTW | Planetary Computer (STAC), Copernicus Data Space, GEE | Não (PC) | [Planetary Computer (sentinel-2-l2a)](https://planetarycomputer.microsoft.com/dataset/sentinel-2-l2a) · [Copernicus Data Space](https://dataspace.copernicus.eu/) |
| ERA5 (ECMWF) | Reanálise horária (temperatura, chuva, vento, umidade, solo, radiação) | ~31 km; horário | Preencher falhas de estações, tendências, features temporais | Copernicus CDS API | CDS (conta gratuita) | [CDS ERA5 (single levels)](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels) · [Documentação ERA5](https://confluence.ecmwf.int/display/CKB/ERA5%3A+data+documentation) |
| FAO GAEZ | Aptidão agroclimática por cultura, restrições de solo, potencial de produtividade | ~10 km; estático/cenários | Verificar aderência da cultura da rotação ao clima/solo | gaez.fao.org | Não | [GAEZ v5](https://gaez.fao.org/) |

## (d) Brasil

| Dataset | Produto/versão | Resolução / revisita | Uso no Field Shift | Como acessar | Login | Links |
|---|---|---|---|---|---|---|
| MapBiomas | Coleção 10, uso e cobertura anual (cana, soja, milho); 1985+ | 30 m; anual | Histórico de culturas por talhão, rotação atual | Espelho COG no Source Cooperative (bucket oficial retorna 403 anônimo); brasil.mapbiomas.org | Não | [MapBiomas Brasil](https://brasil.mapbiomas.org/) · [Source Cooperative](https://source.coop/) |
| Fields of The World (FTW) | Limites de talhão (modelos 2 e 3 classes, checkpoints próprios) | Talhão (a partir de Sentinel-2) | Polígonos de talhão do piloto | Modelo FTW + Sentinel-2 | Não | [FTW](https://fieldsofthe.world/) · [Repositório](https://github.com/fieldsoftheworld/ftw-baselines) |
| IBGE PAM | Produção Agrícola Municipal (área, produção, produtividade) | Município; anual | Produtividade média regional por cultura | API SIDRA (sidra.ibge.gov.br) | Não | [SIDRA PAM (tabela 1612)](https://sidra.ibge.gov.br/tabela/1612) |
| CONAB | Safras, custos de produção, preços | Estado/município; mensal/safra | Renda estimada de cada cultura da rotação | conab.gov.br | Não | [Safras CONAB](https://www.conab.gov.br/info-agro/safras) · [Custos de produção](https://www.conab.gov.br/info-agro/custos-de-producao) |
| CEPEA | Indicadores de preços (soja, milho, cana etc.) | Diário/semanal | Mercado e preço das culturas | cepea.org.br | Não (alguns cadastro) | [Indicadores CEPEA](https://www.cepea.org.br/br/indicador.aspx) |
| INMET BDMEP | Dados históricos de estações meteorológicas | Estação; horário/diário | Validar NASA POWER com medição de campo | bdmep.inmet.gov.br / portal.inmet.gov.br (dados históricos) | Não | [BDMEP](https://bdmep.inmet.gov.br/) · [Dados históricos](https://portal.inmet.gov.br/dadoshistoricos) |
| ZARC (MAPA/Embrapa) | Zoneamento agrícola de risco climático | Município/solo; por safra | Valida janela de plantio; base de crédito e seguro rural | Portal ZARC (MAPA) | Não | [Programa ZARC (MAPA)](https://www.gov.br/agricultura/pt-br/assuntos/riscos-seguro/programa-nacional-de-zoneamento-agricola-de-risco-climatico) |
| PronaSolos / Embrapa GeoInfo | Mapas de solo e dados geoespaciais oficiais | Variável (mapas de solo) | Classes de solo oficiais | geoinfo.dados.embrapa.br | Não | [GeoInfo Embrapa](https://geoinfo.dados.embrapa.br/) · [PronaSolos](https://www.embrapa.br/solos/pronasolos) |
| SoilGrids (ISRIC) | Argila, areia, carbono orgânico, pH estimados | 250 m | Solo padrão quando o produtor não tem análise | soilgrids.org / API | Não | [SoilGrids](https://soilgrids.org/) · [Documentação da API](https://www.isric.org/explore/soilgrids/faq-soilgrids) |
| CAR / SICAR | Polígonos de imóveis rurais | Imóvel | Limite da propriedade na demo | car.gov.br | Não | [SICAR](https://www.car.gov.br/) |
| Observatório da Cana (UNICA) | Moagem, ATR, produção de etanol | Safra/mensal | Contexto de mercado sucroenergético (cana) | observatoriodacana.com.br | Não | [Observatório da Cana](https://observatoriodacana.com.br/) |

## (e) EUA (recursos oficiais do desafio que não se aplicam ao Brasil)

Login: não, salvo indicação.

| Dataset | Produto/versão | Resolução / revisita | Uso no Field Shift (substituto brasileiro) | Como acessar | Login | Links |
|---|---|---|---|---|---|---|
| USDA CDL / CropScape | Classificação anual de culturas | 30 m; anual | Substituto: MapBiomas | nass.usda.gov/Research_and_Science/Cropland | Não | [CDL (NASS)](https://www.nass.usda.gov/research-and-science/cropland/sars1a) |
| NRCS SSURGO / STATSGO2 | Atributos de solo (textura, MO, drenagem, HSG) | Campo / regional | Substituto: SoilGrids / PronaSolos | USDA NRCS Geospatial Gateway | Não | [SSURGO (data.gov)](https://catalog.data.gov/dataset/soil-survey-geographic-database-ssurgo) · [Geospatial Gateway](https://gdg.sc.egov.usda.gov/) |
| Web Soil Survey (WSS) | Mapas e propriedades de solo (NRCS) | Campo | Substituto: SoilGrids / PronaSolos | websoilsurvey.nrcs.usda.gov | Não | [Web Soil Survey](https://websoilsurvey.nrcs.usda.gov/) |
| PRISM (Oregon State) | Clima diário/mensal/normais 30 anos | ~4 km | Substituto: INMET / NASA POWER | prism.oregonstate.edu | Não | [PRISM](https://prism.oregonstate.edu/) |
| USDA NASS QuickStats | Estatísticas agrícolas por condado/estado | Condado; anual | Substituto: IBGE PAM | quickstats.nass.usda.gov | Não (API key) | [QuickStats](https://quickstats.nass.usda.gov/) · [API key](https://quickstats.nass.usda.gov/api) |
| USDA AMS Market News | Preços e demanda de commodities | Diário/semanal | Substituto: CEPEA / CONAB | mymarketnews.ams.usda.gov | Não | [AMS Market News](https://www.ams.usda.gov/market-news) |
| NAIP | Imagem aérea de verão | ~1 m; ~2–3 anos | Substituto: HLS / Sentinel-2 | Earth Explorer / Planetary Computer | Não | [NAIP (Planetary Computer)](https://planetarycomputer.microsoft.com/dataset/naip) · [EarthExplorer](https://earthexplorer.usgs.gov/) |
| USGS NLCD | Cobertura e uso da terra | 30 m; multi-ano | Substituto: MapBiomas | mrlc.gov | Não | [NLCD (USGS)](https://www.usgs.gov/centers/eros/science/national-land-cover-database) |
| OpenET | ET em escala de campo (oeste dos EUA) | 30 m; mensal/diário | Substituto: MOD16 / ECOSTRESS | openetdata.org | Sim (API key) | [OpenET](https://openetdata.org/) · [API](https://openet.gitbook.io/docs) |
| USGS NWIS | Níveis de água, vazão, qualidade | Estação | Substituto: ANA HidroWeb | waterdata.usgs.gov | Não | [Water Data (NWIS)](https://waterdata.usgs.gov/nwis) |
| CoCoRaHS | Chuva diária voluntária (América do Norte) | Ponto; diário | Substituto: INMET / Cemaden | cocorahs.org | Não | [CoCoRaHS](https://cocorahs.org/) |
| USFS LANDFIRE | Vegetação, combustíveis, paisagem | 30 m | Substituto: MapBiomas | landfire.gov | Não | [LANDFIRE](https://landfire.gov/) |
| USDA Ag Data Commons | Datasets abertos agrícolas (solo, cultura, manejo) | Variável | Substituto: Embrapa (Dados Abertos / GeoInfo) | agdatacommons.nal.usda.gov | Não | [Ag Data Commons (NAL)](https://www.nal.usda.gov/services/agdatacommons) |

## (f) Ferramentas de acesso

| Ferramenta | Para que serve | Como acessar | Login | Links |
|---|---|---|---|---|
| Earthdata Login | Conta exigida pela maioria dos downloads NASA | urs.earthdata.nasa.gov | Sim (é o login) | [Earthdata Login](https://urs.earthdata.nasa.gov/) |
| Earthdata Search | Busca e download por área e data | search.earthdata.nasa.gov | Earthdata | [Earthdata Search](https://search.earthdata.nasa.gov/) |
| AppEEARS | Recorte por ponto/polígono (CSV ou raster) de MODIS, SMAP, ECOSTRESS, HLS, Landsat | appeears.earthdatacloud.nasa.gov (API) | Earthdata | [AppEEARS](https://appeears.earthdatacloud.nasa.gov/) · [API](https://appeears.earthdatacloud.nasa.gov/api/) |
| Worldview | Visualização diária, comparação de datas, prints | worldview.earthdata.nasa.gov | Não | [Worldview](https://worldview.earthdata.nasa.gov/) |
| Giovanni | Gráficos e médias de área sem baixar | giovanni.gsfc.nasa.gov | Earthdata | [Giovanni](https://giovanni.gsfc.nasa.gov/giovanni/) |
| NASA POWER API | Clima diário por ponto via HTTP | power.larc.nasa.gov/api | Não | [Documentação da API](https://power.larc.nasa.gov/docs/services/api/) |
| earthaccess | Biblioteca Python: login, busca e download Earthdata | GitHub / PyPI | Earthdata | [GitHub](https://github.com/nsidc/earthaccess) · [PyPI](https://pypi.org/project/earthaccess/) |
| CMR-STAC | Catálogo STAC da NASA (pystac-client) | cmr.earthdata.nasa.gov/stac | Não (busca) | [CMR-STAC](https://cmr.earthdata.nasa.gov/stac) |
| Harmony | Recorte/reprojeção no servidor | harmony.earthdata.nasa.gov | Earthdata | [Harmony](https://harmony.earthdata.nasa.gov/) |
| Microsoft Planetary Computer | Cópia aberta de HLS, Landsat, Sentinel-2, MODIS via STAC | planetarycomputer.microsoft.com | Não | [Planetary Computer](https://planetarycomputer.microsoft.com/) · [Catálogo](https://planetarycomputer.microsoft.com/catalog) |
| Google Earth Engine | Processamento em nuvem (MODIS, Landsat, SMAP, GPM, GRACE) | earthengine.google.com | Conta Google/GEE | [Earth Engine](https://earthengine.google.com/) · [Catálogo](https://developers.google.com/earth-engine/datasets) |
| NASA Acres | Consórcio de agricultura da NASA (casos de uso e contatos) | nasaacres.org | Não | [NASA Acres](https://www.nasaacres.org/) |
| NASA Harvest | Programa de agricultura e segurança alimentar | nasaharvest.org | Não | [NASA Harvest](https://nasaharvest.org/) |

## Contagem

| Grupo | Datasets |
|---|---|
| (a) NASA citados | 12 |
| (b) Outros NASA | 7 |
| (c) ESA/reanálises/internacionais | 3 |
| (d) Brasil | 11 |
| (e) EUA | 13 |
| (f) Ferramentas | 13 |

## Fontes consolidadas

- `novos_datasets_Nasa.md` (recursos oficiais do desafio, incluindo EUA e ESA)
- `Field_Shift_—_Dados_e_ferramentas_da_NASA.pdf` (produtos recomendados, ferramentas, extras NASA e fontes brasileiras)
- `desafio.MD` (enunciado)

Complementos: fontes brasileiras extras e NEX-GDDP-CMIP6/ERA5/Sentinel-2 discutidos na sessão; estado do repositório (`data/raw`, `data/processed`, `src/field_shift`).
