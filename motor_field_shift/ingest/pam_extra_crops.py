"""IBGE PAM (SIDRA) ingestion of the extra 2nd-window crops: sorghum and 2nd-season beans, Oeste do PR or whole-PR municipalities.

Writes data/raw/ibge/pam_extra_oeste_pr.parquet (--regiao oeste_pr) or pam_extra_pr.parquet (--regiao pr) with the SAME schema as
pam_oeste_pr.parquet (tabela, cod_ibge, ano, variavel, cultura, valor; long format). `field_shift.pam.productivity` reads both files.

  table 1612, classification 81: 2714 sorgo (em grão)            -> crop "sorgo"
  table 1002, classification 81: 117992 feijão (em grão) 2ª safra -> crop "feijao_2safra"

Usage: uv run python ingest/pam_extra_crops.py [--force] [--regiao oeste_pr|pr]
(A separate file so it does not depend on ingest/soil_pam_oeste_pr.py, which downloads the PAM of the whole of PR.)
"""
import argparse
import time
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "data/raw/regiao"
REGIONS = {"oeste_pr": ("municipios_oeste_pr.geojson", "pam_extra_oeste_pr.parquet"),
           "pr": ("municipios_pr.geojson", "pam_extra_pr.parquet")}
SIDRA = "https://apisidra.ibge.gov.br/values"
VARS = {"109": "area_plantada_ha", "216": "area_colhida_ha", "214": "producao_t", "112": "rendimento_kg_ha"}
SOURCES = [("1612", {"2714": "sorgo"}), ("1002", {"117992": "feijao_2safra"})]


def _sidra(table, vars_, prods, munis):
    url = f"{SIDRA}/t/{table}/n6/{','.join(munis)}/v/{','.join(vars_)}/p/all/c81/{','.join(prods)}"
    for _ in range(4):
        try:
            r = requests.get(url, timeout=180)
            r.raise_for_status()
            return r.json()[1:]  # row 0 = header
        except Exception as ex:
            print("  retry SIDRA", type(ex).__name__)
            time.sleep(5)
    raise RuntimeError("SIDRA falhou")


def pam_extra(force=False, region="oeste_pr"):
    geojson, nome = REGIONS[region]
    OUTPUT = ROOT / "data/raw/ibge" / nome
    if OUTPUT.exists() and not force:
        print("already exists:", OUTPUT)
        return
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    munis = [str(int(c)) for c in gpd.read_file(REG / geojson)["cod_ibge"]]
    lines = []
    for table, prods in SOURCES:
        for i in range(0, len(munis), 10):
            batch = munis[i:i + 10]
            for j in _sidra(table, list(VARS), list(prods), batch):
                lines.append(dict(tabela=table, cod_ibge=j["D1C"], ano=int(j["D3C"]), variavel=VARS[j["D2C"]],
                                   cultura=prods[j["D4C"]], valor_bruto=j["V"]))
            print(f"  table {table}: municipalities {i + 1}-{i + len(batch)}")
    df = pd.DataFrame(lines)
    # "-" (absolute zero), "..." (not applicable), "X" (withheld for confidentiality), ".." and "" -> NaN
    df["valor"] = pd.to_numeric(df["valor_bruto"].replace({"-": None, "...": None, "..": None, "X": None, "": None}),
                                errors="coerce")
    df = df.drop(columns="valor_bruto")
    df.to_parquet(OUTPUT, index=False)
    print("saved", OUTPUT, len(df), "rows,", df.cod_ibge.nunique(), "municipalities, years", df.ano.min(), "-", df.ano.max())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--regiao", choices=list(REGIONS), default="oeste_pr")
    a = ap.parse_args()
    pam_extra(a.force, a.region)
