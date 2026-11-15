"""Ingestão IBGE PAM (SIDRA) das culturas extras da 2ª janela: sorgo e feijão 2ª safra, municípios do Oeste do PR ou do PR inteiro.

Grava data/raw/ibge/pam_extra_oeste_pr.parquet (--regiao oeste_pr) ou pam_extra_pr.parquet (--regiao pr) no MESMO esquema de pam_oeste_pr.parquet
(tabela, cod_ibge, ano, variavel, cultura, valor; formato longo). `field_shift.pam.produtividade` lê os dois arquivos.

  tabela 1612, classificação 81: 2714 sorgo (em grão)            -> cultura "sorgo"
  tabela 1002, classificação 81: 117992 feijão (em grão) 2ª safra -> cultura "feijao_2safra"

Uso: uv run python ingest/pam_culturas_extra.py [--force] [--regiao oeste_pr|pr]
(Arquivo próprio para não depender de ingest/solo_pam_oeste_pr.py, que baixa o PAM do PR inteiro.)
"""
import argparse
import time
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "data/raw/regiao"
REGIOES = {"oeste_pr": ("municipios_oeste_pr.geojson", "pam_extra_oeste_pr.parquet"),
           "pr": ("municipios_pr.geojson", "pam_extra_pr.parquet")}
SIDRA = "https://apisidra.ibge.gov.br/values"
VARS = {"109": "area_plantada_ha", "216": "area_colhida_ha", "214": "producao_t", "112": "rendimento_kg_ha"}
FONTES = [("1612", {"2714": "sorgo"}), ("1002", {"117992": "feijao_2safra"})]


def _sidra(tabela, vars_, prods, munis):
    url = f"{SIDRA}/t/{tabela}/n6/{','.join(munis)}/v/{','.join(vars_)}/p/all/c81/{','.join(prods)}"
    for _ in range(4):
        try:
            r = requests.get(url, timeout=180)
            r.raise_for_status()
            return r.json()[1:]  # linha 0 = cabeçalho
        except Exception as ex:
            print("  retry SIDRA", type(ex).__name__)
            time.sleep(5)
    raise RuntimeError("SIDRA falhou")


def pam_extra(force=False, regiao="oeste_pr"):
    geojson, nome = REGIOES[regiao]
    SAIDA = ROOT / "data/raw/ibge" / nome
    if SAIDA.exists() and not force:
        print("já existe:", SAIDA)
        return
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    munis = [str(int(c)) for c in gpd.read_file(REG / geojson)["cod_ibge"]]
    linhas = []
    for tabela, prods in FONTES:
        for i in range(0, len(munis), 10):
            lote = munis[i:i + 10]
            for j in _sidra(tabela, list(VARS), list(prods), lote):
                linhas.append(dict(tabela=tabela, cod_ibge=j["D1C"], ano=int(j["D3C"]), variavel=VARS[j["D2C"]],
                                   cultura=prods[j["D4C"]], valor_bruto=j["V"]))
            print(f"  tabela {tabela}: municípios {i + 1}-{i + len(lote)}")
    df = pd.DataFrame(linhas)
    # "-" (zero absoluto), "..." (não se aplica), "X" (omitido por sigilo), ".." e "" -> NaN
    df["valor"] = pd.to_numeric(df["valor_bruto"].replace({"-": None, "...": None, "..": None, "X": None, "": None}),
                                errors="coerce")
    df = df.drop(columns="valor_bruto")
    df.to_parquet(SAIDA, index=False)
    print("salvo", SAIDA, len(df), "linhas,", df.cod_ibge.nunique(), "municípios, anos", df.ano.min(), "-", df.ano.max())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--regiao", choices=list(REGIOES), default="oeste_pr")
    a = ap.parse_args()
    pam_extra(a.force, a.regiao)
