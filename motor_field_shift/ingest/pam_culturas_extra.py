"""IBGE PAM (SIDRA) ingestion of the extra second-window crops: sorghum and 2nd-season beans, Western Paraná municipalities.

Writes data/raw/ibge/pam_extra_oeste_pr.parquet with the SAME schema as pam_oeste_pr.parquet
(tabela, cod_ibge, ano, variavel, cultura, valor; long format). `field_shift.pam.produtividade` reads both files.

  table 1612, classification 81: 2714 sorghum (grain)            -> cultura "sorgo"
  table 1002, classification 81: 117992 beans (grain) 2nd season -> cultura "feijao_2safra"

Usage: uv run python ingest/pam_culturas_extra.py [--force]
(A separate file so it does not depend on ingest/solo_pam_oeste_pr.py, which downloads PAM for the whole of Paraná.)
"""
import argparse
import time
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "data/raw/regiao"
SAIDA = ROOT / "data/raw/ibge/pam_extra_oeste_pr.parquet"
SIDRA = "https://apisidra.ibge.gov.br/values"
VARS = {"109": "area_plantada_ha", "216": "area_colhida_ha", "214": "producao_t", "112": "rendimento_kg_ha"}
FONTES = [("1612", {"2714": "sorgo"}), ("1002", {"117992": "feijao_2safra"})]


def _sidra(tabela, vars_, prods, munis):
    url = f"{SIDRA}/t/{tabela}/n6/{','.join(munis)}/v/{','.join(vars_)}/p/all/c81/{','.join(prods)}"
    for _ in range(4):
        try:
            r = requests.get(url, timeout=180)
            r.raise_for_status()
            return r.json()[1:]  # row 0 = header
        except Exception as ex:
            print("  retry SIDRA", type(ex).__name__)
            time.sleep(5)
    raise RuntimeError("SIDRA failed")


def pam_extra(force=False):
    if SAIDA.exists() and not force:
        print("already exists:", SAIDA)
        return
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    munis = [str(int(c)) for c in gpd.read_file(REG / "municipios_oeste_pr.geojson")["cod_ibge"]]
    linhas = []
    for tabela, prods in FONTES:
        for i in range(0, len(munis), 10):
            lote = munis[i:i + 10]
            for j in _sidra(tabela, list(VARS), list(prods), lote):
                linhas.append(dict(tabela=tabela, cod_ibge=j["D1C"], ano=int(j["D3C"]), variavel=VARS[j["D2C"]],
                                   cultura=prods[j["D4C"]], valor_bruto=j["V"]))
            print(f"  table {tabela}: municipalities {i + 1}-{i + len(lote)}")
    df = pd.DataFrame(linhas)
    # "-" (absolute zero), "..." (not applicable), "X" (withheld for confidentiality), ".." and "" -> NaN
    df["valor"] = pd.to_numeric(df["valor_bruto"].replace({"-": None, "...": None, "..": None, "X": None, "": None}),
                                errors="coerce")
    df = df.drop(columns="valor_bruto")
    df.to_parquet(SAIDA, index=False)
    print("saved", SAIDA, len(df), "rows,", df.cod_ibge.nunique(), "municipalities, years", df.ano.min(), "-", df.ano.max())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    pam_extra(ap.parse_args().force)
