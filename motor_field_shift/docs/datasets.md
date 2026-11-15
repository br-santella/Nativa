# Field Shift — Datasets

De-duplicated consolidation of every dataset cited in the challenge, in the reference PDF, in the official resources and in the Brazilian sources discussed, with the status of each one in the project. Date: 2026-11-14. Access links ("Links" column) checked on 2026-11-14 with `curl` (HTTP 200; some USGS, JPL, CEPEA and IBGE sites return 403 to clients without a browser User-Agent, but open normally in a browser).

**Status legend** (checked on 2026-11-14): "Downloaded" = there are files in `data/`; "Download tested" = downloaded successfully, but not in `data/` yet; "Login OK / catalog OK" = access confirmed, no download; "Not tested" = nothing checked.

**Pilot**: soybean → off-season corn in Western Paraná; the engine now covers all of Paraná. Statuses of the datasets in use were updated on 2026-11-15.

## (a) NASA datasets cited in the challenge

| Dataset | Product/version | Resolution / revisit | Use in Field Shift | How to access | Login | Status | Links |
|---|---|---|---|---|---|---|---|
| NASA POWER | "ag" archive (agroclimatology), daily, since 1981 | ~50 km; daily | Point historical climate, dry spells, frost, water balance | POWER API (HTTP, JSON/CSV) | No | API returned 200 without login | [POWER API](https://power.larc.nasa.gov/docs/services/api/) · [Portal](https://power.larc.nasa.gov/) |
| SMAP L3 (surface) | SPL3SMP_E, L3 Enhanced, V006 | 9 km; daily, since 2015 | Current moisture: "can I plant today?" | earthaccess, AppEEARS, NSIDC | Earthdata | AppEEARS catalog OK (SPL3SMP_E.006); download not tested | [NSIDC SPL3SMP_E](https://nsidc.org/data/SPL3SMP_E) · [AppEEARS](https://appeears.earthdatacloud.nasa.gov/) |
| SMAP L4 (root zone) | SPL4SMGP, V8 (008); model that assimilates SMAP | 9 km; 3 h, since 2015 | Moisture at root depth | earthaccess, AppEEARS, NSIDC | Earthdata | In use: `/v1/contexto` reads the field pixel at request time (`src/field_shift/context/smap.py`, earthaccess) | [NSIDC SPL4SMGP](https://nsidc.org/data/spl4smgp) · [AppEEARS](https://appeears.earthdatacloud.nasa.gov/) |
| ECOSTRESS | ECO_L2T_LSTE V002 (temperature); L3 JET (ET) and L4 ESI | 70 m; irregular (ISS) | Crop heat and water stress | LP DAAC, AppEEARS | Earthdata | Download tested (ECO_L2T_LSTE v002); AppEEARS catalog OK | [ECOSTRESS documentation](https://ecostress.jpl.nasa.gov/data/atbds-summary-table) · [LP DAAC](https://lpdaac.usgs.gov/products/eco_l2t_lstev002/) |
| GPM IMERG | GPM_3IMERGDF V07, Final, daily | 0.1° (~10 km); daily, since 2000 | Historical rain and heavy rain (erosion) | GES DISC, earthaccess, AWS | Earthdata | Download tested (GES DISC) | [GES DISC GPM_3IMERGDF](https://disc.gsfc.nasa.gov/datasets/GPM_3IMERGDF_07/summary) · [AWS Open Data](https://registry.opendata.aws/nasa-gpm3imergdf/) |
| Landsat 8/9 | Collection 2 Level-2 Surface Reflectance | 30 m; 8 days | Historical NDVI per field, exposed soil | USGS EarthExplorer, Planetary Computer, GEE | USGS (EarthExplorer) / no (PC) | Not tested (HLS covers the dense series) | [USGS Collection 2 L2](https://www.usgs.gov/landsat-missions/landsat-collection-2-level-2-science-products) · [EarthExplorer](https://earthexplorer.usgs.gov/) |
| MODIS (vegetation) | MOD13Q1 v061, NDVI/EVI | 250 m; 16 days, since 2000 | Long vigor series and crop calendar | AppEEARS, LP DAAC, GEE | Earthdata | Download tested (LP DAAC); AppEEARS catalog OK | [LP DAAC MOD13Q1](https://lpdaac.usgs.gov/products/mod13q1v061/) · [Earth Engine](https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MOD13Q1) |
| VIIRS (vegetation) | VIIRS vegetation indices (product to be defined; only cited in the challenge text/resources) | 375–1000 m; daily/16 days | Alternative/continuity of MODIS | Earthdata Search, AppEEARS | Earthdata | Not tested | [LP DAAC VNP13A1](https://lpdaac.usgs.gov/products/vnp13a1v002/) · [Earthdata Search](https://search.earthdata.nasa.gov/) |
| MODIS (evapotranspiration) | MOD16A2GF v061, gap-filled ET | 500 m; 8 days, since 2000 | Actual vegetation water use | AppEEARS, LP DAAC, GEE | Earthdata | AppEEARS catalog OK (MOD16A2GF.061); download not tested | [LP DAAC MOD16A2GF](https://lpdaac.usgs.gov/products/mod16a2gfv061/) · [Earth Engine](https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MOD16A2GF) |
| GRACE / GRACE-FO | JPL Mascon RL06.3Mv04 (total water) | ~300 km; monthly, since 2002 | Long-term water trend of the region | GEE (JPL Mascon), PO.DAAC (CSR Land) | Earthdata (PO.DAAC) | Not tested | [Earth Engine Mascon](https://developers.google.com/earth-engine/datasets/catalog/NASA_GRACE_MASS_GRIDS_V04_MASCON) · [PO.DAAC CSR Land](https://podaac.jpl.nasa.gov/dataset/TELLUS_GRFO_L3_CSR_RL06.3_LND_v04) |
| SRTM / NASADEM | NASADEM_HGT v001 (preferred) or SRTMGL1 v003 | 30 m; static | Slope, erosion, frost-prone lowlands | LP DAAC, earthaccess, Planetary Computer | Earthdata (PC: no) | Downloaded via Planetary Computer: `data/raw/nasadem_pr/elev.tif`, slope in `data/processed/relevo_pr/` | [LP DAAC NASADEM](https://lpdaac.usgs.gov/products/nasadem_hgtv001/) · [LP DAAC SRTMGL1](https://lpdaac.usgs.gov/products/srtmgl1v003/) |
| GEDI | L4A V3, aboveground biomass per footprint | 25 m footprints; sampled | Biomass of nearby forest; of little use for annual crops | ORNL DAAC | Earthdata | Not tested | [ORNL DAAC GEDI L4A](https://daac.ornl.gov/GEDI/guides/GEDI_L4A_AGB_Density_V3.html) · [Dataset](https://daac.ornl.gov/cgi-bin/dsviewer.pl?ds_id=2056) |

## (b) Other useful NASA datasets

| Dataset | Product/version | Resolution / revisit | Use in Field Shift | How to access | Login | Status | Links |
|---|---|---|---|---|---|---|---|
| HLS (Harmonized Landsat Sentinel-2) | HLSL30 / HLSS30 v2.0 (020) | 30 m; 2–3 days | Best option for per-field NDVI and bare soil | LP DAAC, AppEEARS, Planetary Computer | Earthdata (PC: no) | Download tested (HLSL30/HLSS30 v2.0); AppEEARS catalog OK (.020) | [HLS (NASA)](https://hls.gsfc.nasa.gov/) · [LP DAAC HLSS30](https://lpdaac.usgs.gov/products/hlss30v002/) |
| OPERA | DSWx (surface water) and DIST (vegetation disturbance), from HLS and radar | 30 m; a few days | Detects harvest/exposed soil without computing an index | Earthdata Search, PO.DAAC/LP DAAC | Earthdata | Not tested | [OPERA (JPL)](https://www.jpl.nasa.gov/go/opera/) · [Earthdata Search](https://search.earthdata.nasa.gov/) |
| Crop-CASMA | SMAP soil-moisture viewer for agriculture (USDA + GMU) | 1–9 km | Ready-made moisture and anomaly maps (reference; US coverage) | Web viewer | No | Not tested | [Crop-CASMA](https://cloud.csiss.gmu.edu/CropCASMA/) |
| NEX-GDDP-CMIP6 | Daily climate projections to 2100 | ~25 km; daily | Rotation under a future scenario (climate slider) | NCCS (THREDDS/AWS) | No | Not tested | [NCCS NEX-GDDP-CMIP6](https://www.nccs.nasa.gov/services/data-collections/land-based-products/nex-gddp-cmip6) |
| GLDAS / NLDAS | Land surface model: moisture, ET, runoff, soil temperature (NLDAS only covers North America) | 25 km; 3 h (GLDAS) | Ready-made full water balance; use GLDAS in Brazil | GES DISC, Earthdata Search | Earthdata | Not tested | [GLDAS](https://ldas.gsfc.nasa.gov/gldas) · [NLDAS](https://ldas.gsfc.nasa.gov/nldas) |
| FLDAS | GLDAS variant for food security | ~10 km; monthly | Agricultural drought indicators | GES DISC | Earthdata | Not tested | [FLDAS](https://ldas.gsfc.nasa.gov/fldas) |
| EMIT | Hyperspectral spectrum (285 bands, 380–2500 nm) | 60 m; irregular (ISS) | Soil minerals, straw × exposed soil; outside the MVP | LP DAAC | Earthdata | Not tested | [EMIT (JPL)](https://earth.jpl.nasa.gov/emit/) · [LP DAAC EMITL2ARFL](https://lpdaac.usgs.gov/products/emitl2arflv001/) |

## (c) ESA, reanalyses and other international datasets

| Dataset | Product/version | Resolution / revisit | Use in Field Shift | How to access | Login | Status | Links |
|---|---|---|---|---|---|---|---|
| Copernicus Sentinel-2 | L2A (10–20 m; red-edge, NIR, SWIR) | 10–20 m; ~5 days | NDVI/EVI, exposed soil, stress; basis of the FTW field boundaries | Planetary Computer (STAC), Copernicus Data Space, GEE | No (PC) | In use: scene search via Planetary Computer (`src/field_shift/ftw/search_scenes.py`); scene `data/processed/ftw/scene_ab.tif` generated (Downloaded) | [Planetary Computer (sentinel-2-l2a)](https://planetarycomputer.microsoft.com/dataset/sentinel-2-l2a) · [Copernicus Data Space](https://dataspace.copernicus.eu/) |
| ERA5 (ECMWF) | Hourly reanalysis (temperature, rain, wind, humidity, soil, radiation) | ~31 km; hourly | Fill station gaps, trends, temporal features | Copernicus CDS API | CDS (free account) | Not tested | [CDS ERA5 (single levels)](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels) · [ERA5 documentation](https://confluence.ecmwf.int/display/CKB/ERA5%3A+data+documentation) |
| FAO GAEZ | Agro-climatic suitability per crop, soil constraints, yield potential | ~10 km; static/scenarios | Check the rotation crop's fit to climate/soil | gaez.fao.org | No | Not tested | [GAEZ v5](https://gaez.fao.org/) |

## (d) Brazil

| Dataset | Product/version | Resolution / revisit | Use in Field Shift | How to access | Login | Status | Links |
|---|---|---|---|---|---|---|---|
| MapBiomas | Collection 10, annual land use and cover (sugarcane, soybean, corn); 1985+ | 30 m; annual | Crop history per field, current rotation | COG mirror on Source Cooperative (the official bucket returns 403 to anonymous access); brasil.mapbiomas.org | No | Downloaded: `data/raw/mapbiomas_pr/` (2019–2024); legend and join in `data/processed/ftw/` | [MapBiomas Brasil](https://brasil.mapbiomas.org/) · [Source Cooperative](https://source.coop/) |
| Fields of The World (FTW) | Field boundaries (2- and 3-class models, own checkpoints) | Field (from Sentinel-2) | Field polygons for the pilot | FTW model + Sentinel-2 | No | Downloaded/processed: `data/processed/ftw/` (`fields_*.gpkg/parquet`, `pred_*.tif`, `*.ckpt`) | [FTW](https://fieldsofthe.world/) · [Repository](https://github.com/fieldsoftheworld/ftw-baselines) |
| IBGE PAM | Municipal Agricultural Production (area, production, yield) | Municipality; annual | Municipal yield per crop (expected yield, bad year, track record) | SIDRA API (sidra.ibge.gov.br) | No | Downloaded: `data/raw/ibge/pam_pr.parquet`, `pam_extra_pr.parquet` (399 municipalities) | [SIDRA PAM (table 1612)](https://sidra.ibge.gov.br/tabela/1612) |
| CONAB | Crop seasons, production costs, prices | State/municipality; monthly/season | Production costs (COE) of each rotation crop | conab.gov.br | No | In use: cost sheets in `data/ref/precos_custos.json` (`src/field_shift/income/update.py`) | [CONAB seasons](https://www.conab.gov.br/info-agro/safras) · [Production costs](https://www.conab.gov.br/info-agro/custos-de-producao) |
| CEPEA | Price indicators (soybean, corn, sugarcane, etc.) | Daily/weekly | Market and crop prices | cepea.org.br | No (some require sign-up) | Not tested | [CEPEA indicators](https://www.cepea.org.br/br/indicador.aspx) |
| INMET BDMEP | Historical weather station data | Station; hourly/daily | Validate NASA POWER against field measurements | bdmep.inmet.gov.br / portal.inmet.gov.br (historical data) | No | Downloaded: 7 stations used to validate POWER (`src/field_shift/climate/station_validation.py`) | [BDMEP](https://bdmep.inmet.gov.br/) · [Historical data](https://portal.inmet.gov.br/dadoshistoricos) |
| ZARC (MAPA/Embrapa) | Agricultural climate-risk zoning | Municipality/soil; per season | Validates the planting window; basis for rural credit and insurance (engine validation: `docs/validation.md` §2) | ZARC portal (MAPA); risk table per season as open CSV at dados.agricultura.gov.br (`scripts/validation/zarc_agreement.py`) | No | Downloaded (2025/2026 table, Paraná rows in `data/raw/zarc/`) | [ZARC program (MAPA)](https://www.gov.br/agricultura/pt-br/assuntos/riscos-seguro/programa-nacional-de-zoneamento-agricola-de-risco-climatico) · [Risk table (open data)](https://dados.agricultura.gov.br/dataset/tabua-de-risco-zoneamento-agricola-de-risco-climatico) |
| PronaSolos / Embrapa GeoInfo | Official soil maps and geospatial data | Variable (soil maps) | Official soil classes | geoinfo.dados.embrapa.br | No | Not tested | [GeoInfo Embrapa](https://geoinfo.dados.embrapa.br/) · [PronaSolos](https://www.embrapa.br/solos/pronasolos) |
| SoilGrids (ISRIC) | Estimated clay, sand, organic carbon, pH | 250 m | Default soil when the farmer has no analysis | soilgrids.org / API | No | Downloaded: `data/raw/soilgrids_pr/` (REST API as fallback) | [SoilGrids](https://soilgrids.org/) · [API documentation](https://www.isric.org/explore/soilgrids/faq-soilgrids) |
| CAR / SICAR | Rural property polygons | Property | Property boundary in the demo | car.gov.br | No | Not tested | [SICAR](https://www.car.gov.br/) |
| SEAB/DERAL-PR | Weekly/monthly prices received by Paraná farmers | State and regional nucleus; weekly/monthly | Prices of the rotation crops (12-month average) | agricultura.pr.gov.br/deral/Precos | No | In use: `data/ref/precos_custos.json` (`src/field_shift/income/update.py`) | [DERAL prices](https://www.agricultura.pr.gov.br/deral/Precos) |
| Observatório da Cana (UNICA) | Crushing, ATR, ethanol production | Season/monthly | Sugar-energy market context (sugarcane) | observatoriodacana.com.br | No | Not tested | [Observatório da Cana](https://observatoriodacana.com.br/) |

## (e) USA (official challenge resources that do not apply to Brazil)

Status of all: Not tested (outside the geographic scope). Login: no, unless stated.

| Dataset | Product/version | Resolution / revisit | Use in Field Shift (Brazilian substitute) | How to access | Login | Status | Links |
|---|---|---|---|---|---|---|---|
| USDA CDL / CropScape | Annual crop classification | 30 m; annual | Substitute: MapBiomas | nass.usda.gov/Research_and_Science/Cropland | No | Not tested | [CDL (NASS)](https://www.nass.usda.gov/research-and-science/cropland/sars1a) |
| NRCS SSURGO / STATSGO2 | Soil attributes (texture, OM, drainage, HSG) | Field / regional | Substitute: SoilGrids / PronaSolos | USDA NRCS Geospatial Gateway | No | Not tested | [SSURGO (data.gov)](https://catalog.data.gov/dataset/soil-survey-geographic-database-ssurgo) · [Geospatial Gateway](https://gdg.sc.egov.usda.gov/) |
| Web Soil Survey (WSS) | Soil maps and properties (NRCS) | Field | Substitute: SoilGrids / PronaSolos | websoilsurvey.nrcs.usda.gov | No | Not tested | [Web Soil Survey](https://websoilsurvey.nrcs.usda.gov/) |
| PRISM (Oregon State) | Daily/monthly climate, 30-year normals | ~4 km | Substitute: INMET / NASA POWER | prism.oregonstate.edu | No | Not tested | [PRISM](https://prism.oregonstate.edu/) |
| USDA NASS QuickStats | Agricultural statistics by county/state | County; annual | Substitute: IBGE PAM | quickstats.nass.usda.gov | No (API key) | Not tested | [QuickStats](https://quickstats.nass.usda.gov/) · [API key](https://quickstats.nass.usda.gov/api) |
| USDA AMS Market News | Commodity prices and demand | Daily/weekly | Substitute: CEPEA / CONAB | mymarketnews.ams.usda.gov | No | Not tested | [AMS Market News](https://www.ams.usda.gov/market-news) |
| NAIP | Summer aerial imagery | ~1 m; ~2–3 years | Substitute: HLS / Sentinel-2 | Earth Explorer / Planetary Computer | No | Not tested | [NAIP (Planetary Computer)](https://planetarycomputer.microsoft.com/dataset/naip) · [EarthExplorer](https://earthexplorer.usgs.gov/) |
| USGS NLCD | Land cover and land use | 30 m; multi-year | Substitute: MapBiomas | mrlc.gov | No | Not tested | [NLCD (USGS)](https://www.usgs.gov/centers/eros/science/national-land-cover-database) |
| OpenET | Field-scale ET (western USA) | 30 m; monthly/daily | Substitute: MOD16 / ECOSTRESS | openetdata.org | Yes (API key) | Not tested | [OpenET](https://openetdata.org/) · [API](https://openet.gitbook.io/docs) |
| USGS NWIS | Water levels, streamflow, quality | Station | Substitute: ANA HidroWeb | waterdata.usgs.gov | No | Not tested | [Water Data (NWIS)](https://waterdata.usgs.gov/nwis) |
| CoCoRaHS | Volunteer daily rainfall (North America) | Point; daily | Substitute: INMET / Cemaden | cocorahs.org | No | Not tested | [CoCoRaHS](https://cocorahs.org/) |
| USFS LANDFIRE | Vegetation, fuels, landscape | 30 m | Substitute: MapBiomas | landfire.gov | No | Not tested | [LANDFIRE](https://landfire.gov/) |
| USDA Ag Data Commons | Open agricultural datasets (soil, crop, management) | Variable | Substitute: Embrapa (Open Data / GeoInfo) | agdatacommons.nal.usda.gov | No | Not tested | [Ag Data Commons (NAL)](https://www.nal.usda.gov/services/agdatacommons) |

## (f) Access tools

| Tool | What it is for | How to access | Login | Status | Links |
|---|---|---|---|---|---|
| Earthdata Login | Account required by most NASA downloads | urs.earthdata.nasa.gov | Yes (it is the login) | Login OK | [Earthdata Login](https://urs.earthdata.nasa.gov/) |
| Earthdata Search | Search and download by area and date | search.earthdata.nasa.gov | Earthdata | Not tested | [Earthdata Search](https://search.earthdata.nasa.gov/) |
| AppEEARS | Point/polygon extraction (CSV or raster) of MODIS, SMAP, ECOSTRESS, HLS, Landsat | appeears.earthdatacloud.nasa.gov (API) | Earthdata | API login OK; catalog contains ECO_L2T_LSTE.002, SPL3SMP_E.006, SPL4SMGP.008, MOD13Q1.061, MOD16A2GF.061, HLSL30.020, HLSS30.020 | [AppEEARS](https://appeears.earthdatacloud.nasa.gov/) · [API](https://appeears.earthdatacloud.nasa.gov/api/) |
| Worldview | Daily visualization, date comparison, screenshots | worldview.earthdata.nasa.gov | No | Not tested | [Worldview](https://worldview.earthdata.nasa.gov/) |
| Giovanni | Charts and area averages without downloading | giovanni.gsfc.nasa.gov | Earthdata | Not tested | [Giovanni](https://giovanni.gsfc.nasa.gov/giovanni/) |
| NASA POWER API | Daily point climate over HTTP | power.larc.nasa.gov/api | No | Returned 200 | [API documentation](https://power.larc.nasa.gov/docs/services/api/) |
| earthaccess | Python library: Earthdata login, search and download | GitHub / PyPI | Earthdata | Not tested | [GitHub](https://github.com/nsidc/earthaccess) · [PyPI](https://pypi.org/project/earthaccess/) |
| CMR-STAC | NASA STAC catalog (pystac-client) | cmr.earthdata.nasa.gov/stac | No (search) | Not tested | [CMR-STAC](https://cmr.earthdata.nasa.gov/stac) |
| Harmony | Server-side subsetting/reprojection | harmony.earthdata.nasa.gov | Earthdata | Not tested | [Harmony](https://harmony.earthdata.nasa.gov/) |
| Microsoft Planetary Computer | Open copy of HLS, Landsat, Sentinel-2, MODIS via STAC | planetarycomputer.microsoft.com | No | In use (Sentinel-2 search) | [Planetary Computer](https://planetarycomputer.microsoft.com/) · [Catalog](https://planetarycomputer.microsoft.com/catalog) |
| Google Earth Engine | Cloud processing (MODIS, Landsat, SMAP, GPM, GRACE) | earthengine.google.com | Google/GEE account | Not tested | [Earth Engine](https://earthengine.google.com/) · [Catalog](https://developers.google.com/earth-engine/datasets) |
| NASA Acres | NASA agriculture consortium (use cases and contacts) | nasaacres.org | No | Not tested | [NASA Acres](https://www.nasaacres.org/) |
| NASA Harvest | Agriculture and food security program | nasaharvest.org | No | Not tested | [NASA Harvest](https://nasaharvest.org/) |

## Count

| Group | Datasets |
|---|---|
| (a) NASA cited | 12 |
| (b) Other NASA | 7 |
| (c) ESA/reanalyses/international | 3 |
| (d) Brazil | 12 |
| (e) USA | 13 |
| (f) Tools | 13 |

## Consolidated sources

These files are local to the team and not versioned in this repository.

- `novos_datasets_Nasa.md` (official challenge resources, including USA and ESA)
- `Field_Shift_—_Dados_e_ferramentas_da_NASA.pdf` (recommended products, tools, NASA extras and Brazilian sources)
- `desafio.MD` (challenge statement)

Complements: extra Brazilian sources and NEX-GDDP-CMIP6/ERA5/Sentinel-2 discussed in the session; repository state (`data/raw`, `data/processed`, `src/field_shift`).
