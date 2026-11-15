"""Ingestão regional: SoilGrids (solo) e IBGE PAM (produtividade municipal) do Oeste do PR.

Subcomandos (idempotentes: pulam o que já existe; --force refaz):
  soilgrids  recorta o bbox do Oeste do PR (+margem) dos VRTs do ISRIC, reprojeta para EPSG:4326
             (~0,0025° ≈ 275 m) e salva 1 GeoTIFF por propriedade em data/raw/soilgrids_oeste_pr/
             (4 bandas = 0-5, 5-15, 15-30, 30-60 cm), já em UNIDADES FÍSICAS (ver ESCALAS).
  pam        baixa SIDRA (tabela 1612: soja, milho total, trigo, aveia; tabela 839: milho 1ª e 2ª safra)
             dos 50 municípios -> data/raw/ibge/pam_oeste_pr.parquet (formato longo).
  all        os dois.

Uso: uv run python ingest/solo_pam_oeste_pr.py {soilgrids|pam|all} [--force] [--regiao oeste_pr|pr]
  --regiao pr: Paraná inteiro (399 municípios; lê regiao/pr.geojson e municipios_pr.geojson, gerados por
  ingest/mapbiomas_relevo_oeste_pr.py --regiao pr) -> data/raw/soilgrids_pr/ e data/raw/ibge/pam_pr.parquet.
"""
import argparse
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import requests
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject, transform_bounds
from rasterio.windows import from_bounds

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "data/raw/regiao"
SUF = "oeste_pr"
SG = ROOT / "data/raw/soilgrids_oeste_pr"
PAM = ROOT / "data/raw/ibge/pam_oeste_pr.parquet"
VRT = "/vsicurl/https://files.isric.org/soilgrids/latest/data/{p}/{p}_{d}_mean.vrt"
PROFS = ["0-5cm", "5-15cm", "15-30cm", "30-60cm"]
MARGIN = 0.1
RES = 0.0025  # graus

# Fatores de escala do SoilGrids 2.0 (valor inteiro mapeado / fator = unidade física).
# unidade física salva: clay/sand/silt em % (g/100 g; mapeado em g/kg -> /10);
# soc em g/kg (mapeado em dg/kg -> /10); phh2o em pH (mapeado ×10 -> /10);
# bdod em g/cm³ (mapeado em cg/cm³ -> /100).
# wv0033/wv1500 NÃO existem no servidor (latest/data só tem bdod, cec, cfvo, clay, nitrogen, ocd, ocs, phh2o, sand, silt, soc, wrb),
# por isso a CAD sai de pedotransferência (Saxton & Rawls) no módulo field_shift.solo.
SCALES = {"clay": 10.0, "sand": 10.0, "silt": 10.0, "soc": 10.0, "phh2o": 10.0, "bdod": 100.0}


def configure(region):
    global SUF, SG, PAM
    SUF = region
    SG = ROOT / f"data/raw/soilgrids_{region}"
    PAM = ROOT / f"data/raw/ibge/pam_{region}.parquet"


def bbox():
    b = gpd.read_file(REG / f"{SUF}.geojson").total_bounds
    return b[0] - MARGIN, b[1] - MARGIN, b[2] + MARGIN, b[3] + MARGIN


def soilgrids(force=False, props=None):
    SG.mkdir(parents=True, exist_ok=True)
    w, s, e, n = bbox()
    ncol, nrow = int(round((e - w) / RES)), int(round((n - s) / RES))
    dst_tr = from_origin(w, n, RES, RES)
    for prop, factor in SCALES.items():
        if props and prop not in props:
            continue
        out = SG / f"{prop}.tif"
        if out.exists() and not force:
            print("já existe:", out.name)
            continue
        bands = []
        for d in PROFS:
            t0 = time.time()
            for tent in range(4):
                try:
                    with rasterio.open(VRT.format(p=prop, d=d)) as src:
                        bb = transform_bounds("EPSG:4326", src.crs, w, s, e, n, densify_pts=50)
                        win = from_bounds(*bb, transform=src.transform).round_offsets().round_lengths()
                        dados = src.read(1, window=win).astype("float32")
                        tr = src.window_transform(win)
                        nod = src.nodata
                        crs = src.crs
                    break
                except Exception as ex:  # rede instável
                    print("  retry", prop, d, type(ex).__name__)
                    time.sleep(5)
            else:
                raise RuntimeError(f"falhou {prop} {d}")
            dados[dados == nod] = np.nan
            dst = np.full((nrow, ncol), np.nan, "float32")
            reproject(dados, dst, src_transform=tr, src_crs=crs, dst_transform=dst_tr, dst_crs="EPSG:4326",
                      src_nodata=np.nan, dst_nodata=np.nan, resampling=Resampling.bilinear)
            bands.append(dst / factor)
            print(f"  {prop} {d}: {time.time() - t0:.0f}s, média {np.nanmean(dst / factor):.2f}")
        with rasterio.open(out, "w", driver="GTiff", height=nrow, width=ncol, count=len(PROFS), dtype="float32",
                           crs="EPSG:4326", transform=dst_tr, nodata=np.nan, compress="deflate",
                           predictor=3, tiled=True) as dst_f:
            for i, b in enumerate(bands, 1):
                dst_f.write(b, i)
                dst_f.set_band_description(i, f"{prop} {PROFS[i - 1]}")
        print("salvo", out, out.stat().st_size // 1024, "KB")


# ------------------------------------------------------------------------------- PAM
SIDRA = "https://apisidra.ibge.gov.br/values"
VARS = {"109": "area_plantada_ha", "216": "area_colhida_ha", "214": "producao_t", "112": "rendimento_kg_ha"}
VAR_VALOR = {"215": "valor_mil_reais"}
# tabela 1612, classificação 81 (produto): 2713 soja, 2711 milho (em grão, total), 2716 trigo, 2693 aveia
PROD_1612 = {"2713": "soja", "2711": "milho_total", "2716": "trigo", "2693": "aveia"}
# tabela 839, classificação 81: 114253 milho 1ª safra, 114254 milho 2ª safra
PROD_839 = {"114253": "milho_1safra", "114254": "milho_2safra"}


def _sidra(table, vars_, prods, munis):
    url = (f"{SIDRA}/t/{table}/n6/{','.join(munis)}/v/{','.join(vars_)}/p/all/c81/{','.join(prods)}")
    for tent in range(4):
        try:
            r = requests.get(url, timeout=180)
            r.raise_for_status()
            return r.json()[1:]  # linha 0 = cabeçalho
        except Exception as ex:
            print("  retry SIDRA", type(ex).__name__)
            time.sleep(5)
    raise RuntimeError("SIDRA falhou")


def pam(force=False):
    if PAM.exists() and not force:
        print("já existe:", PAM)
        return
    PAM.parent.mkdir(parents=True, exist_ok=True)
    munis = [str(int(c)) for c in gpd.read_file(REG / f"municipios_{SUF}.geojson")["cod_ibge"]]
    lines = []
    for table, vars_, prods in [("1612", {**VARS, **VAR_VALOR}, PROD_1612), ("839", VARS, PROD_839)]:
        for i in range(0, len(munis), 10):
            batch = munis[i:i + 10]
            for j in _sidra(table, list(vars_), list(prods), batch):
                lines.append(dict(tabela=table, cod_ibge=j["D1C"], ano=int(j["D3C"]), variavel=vars_[j["D2C"]],
                                   cultura=prods[j["D4C"]], valor_bruto=j["V"]))
            print(f"  tabela {table}: municípios {i + 1}-{i + len(batch)}")
    df = pd.DataFrame(lines)
    # "-" (zero absoluto), "..." (não se aplica), "X" (omitido por sigilo), ".." e "" -> NaN
    df["valor"] = pd.to_numeric(df["valor_bruto"].replace({"-": None, "...": None, "..": None, "X": None, "": None}),
                                errors="coerce")
    df = df.drop(columns="valor_bruto")
    df.to_parquet(PAM, index=False)
    print("salvo", PAM, len(df), "linhas,", df.cod_ibge.nunique(), "municípios, anos", df.ano.min(), "-", df.ano.max(),
          f"{PAM.stat().st_size // 1024} KB")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["soilgrids", "pam", "all"])
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--regiao", choices=["oeste_pr", "pr"], default="oeste_pr")
    ap.add_argument("--props", nargs="*", help="só estas propriedades do SoilGrids (permite rodar em paralelo)")
    a = ap.parse_args()
    configure(a.region)
    if a.cmd in ("soilgrids", "all"):
        soilgrids(a.force, a.props)
    if a.cmd in ("pam", "all"):
        pam(a.force)
