"""Downloads prices (SEAB/DERAL-PR) and costs (CONAB) and writes data/ref/precos_custos.json.

Usage:  uv run python -m field_shift.renda.atualizar
The raw files stay in data/raw/renda/ (not in git); the final JSON is small and goes into git.
Cover/fallow have NO official source: they are reference estimates flagged in the JSON.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "data/raw/renda"
SAIDA = ROOT / "data/ref/precos_custos.json"
UA = {"User-Agent": "Mozilla/5.0"}

URL_PRECOS = "https://www.agricultura.pr.gov.br/system/files/publico/Precos/pmrp.xls"
URL_PAGINA_PRECOS = "https://www.agricultura.pr.gov.br/deral/Precos"
CONAB = ("https://www.gov.br/conab/pt-br/atuacao/informacoes-agropecuarias/custos-de-producao/"
         "arquivos-custo-de-producao/agricolas/")
# (file, sheet, human label)
CUSTOS = {
    "soja": (CONAB + "serie-historica-custos-soja-1997-a-2026.xls", "OGM-Londrina-PR-2026",
             "CONAB, GM soybean, no-till, high technology, commercial farming, Londrina-PR, 1st season 2026/27 (estimated, Mar/2026)"),
    "milho_2safra": (CONAB + "milho/milho_2a_safra_serie_historica_2005-2026.xls", "Londrina-PR-2026",
                     "CONAB, GM 2nd-season corn, no-till, high technology, commercial farming, Londrina-PR, 2026 (estimated, Mar/2026)"),
    "trigo": (CONAB + "seriehistoricacustostrigo1998a2025.xls", "Ponta Grossa-PR-2025-11",
              "CONAB, wheat, no-till, high technology, commercial farming, Ponta Grossa-PR, 2025 winter season (ex-post, Nov/2025)"),
    # summer corn (1st season): the only Paraná sheets are for Ponta Grossa/Guarapuava (reference yield 12 t/ha, higher than Western Paraná's)
    "milho_1safra": (CONAB + "milho/milho_1a_safra_serie_historica_1997-2026.xls", "Ponta Grossa-PR-2026",
                     "CONAB, GM 1st-season corn, no-till, high technology, commercial farming, Ponta Grossa-PR, 2026/27 (estimated, Mar/2026; "
                     "reference yield 12 t/ha, above the Western Paraná average)"),
    "feijao_2safra": (CONAB + "feijao/feijao_2_e_3_safras_serie_historica_2013-2026.xls", "Francisco Beltrão-PR-2026",
                      "CONAB, 2nd-season beans, no-till, high technology, family farming, Francisco Beltrão-PR, 2026 (estimated, Mar/2026; "
                      "the Cascavel-PR sheet only goes up to 2021)"),
}
# No CONAB sorghum sheet for Paraná: uses the Rio Verde-GO 2nd-season grain sorghum sheet as an approximation (flagged as an estimate).
CUSTO_PROXY = {
    "sorgo": (CONAB + "seriehistoricacustossorgo2013a2026.xls", "Rio Verde-GO-2026",
              "estimate — to be validated: there is no CONAB sorghum sheet for Paraná; uses CONAB, GM 2nd-season grain sorghum, no-till, high technology, "
              "commercial farming, Rio Verde-GO, 2026 (estimated, Mar/2026)"),
}
CURTO = {"soja": "CONAB Londrina-PR, 2026/27 season (est. Mar/2026)", "milho_2safra": "CONAB Londrina-PR, 2nd season 2026 (est. Mar/2026)",
         "trigo": "CONAB Ponta Grossa-PR, winter 2025 (Nov/2025)",
         "milho_1safra": "CONAB Ponta Grossa-PR, 1st season 2026/27 (est. Mar/2026)",
         "feijao_2safra": "CONAB Francisco Beltrão-PR, 2nd season 2026 (est. Mar/2026)",
         "sorgo": "estimate — to be validated (CONAB Rio Verde-GO 2026, no Paraná sheet)"}
ESTIM = "reference estimate, to be validated (no CONAB series; order of magnitude agreed with the team)"
COBERTURAS = {  # BRL/ha: midpoint of the reference ranges
    "aveia": (375.0, "oat as cover (seed + operation): range BRL 300–450/ha"),
    "milheto_crotalaria": (450.0, "millet/crotalaria (seed + operation): millet ~BRL 300–450, crotalaria ~BRL 400–600/ha"),
    "braquiaria_consorcio": (200.0, "brachiaria intercropped with corn, on top of the corn cost: range BRL 150–250/ha"),
    "pousio": (200.0, "fallow: desiccation/weed management, range BRL 150–250/ha"),
    "nabo_forrageiro": (275.0, "forage radish as cover (10–15 kg/ha of seed + sowing): range BRL 200–350/ha"),
    "aveia_nabo": (400.0, "oat + forage radish mix as cover (seed of both + sowing): range BRL 350–450/ha"),
}
ESTIM_VALIDAR = "estimate — to be validated"
RAZAO_SORGO_MILHO = 0.80  # sorghum price ≈ 80% of the corn price (no SEAB/DERAL sorghum series) — estimate, to be validated


def _baixar(url: str, nome: str) -> Path:
    RAW.mkdir(parents=True, exist_ok=True)
    f = RAW / nome
    r = requests.get(url, headers=UA, timeout=180)
    r.raise_for_status()
    f.write_bytes(r.content)
    return f


def precos() -> dict:
    f = _baixar(URL_PRECOS, "seab_pmrp.xls")
    d = pd.read_excel(f, header=None)
    cols = d.iloc[1, 3:16].tolist()  # OUT/26 ... OUT/25 (most recent first)
    out = {}
    for chave, produto in (("soja", "Soja"), ("milho", "Milho"), ("trigo", "Trigo"), ("feijao", "Feijao preto")):
        r = d[d[1] == produto].iloc[0]
        v = pd.to_numeric(r[3:15], errors="coerce").dropna()  # 12 most recent months
        assert len(v) == 12, (produto, len(v))
        out[chave] = dict(
            valor=round(float(v.mean()), 2), unidade="BRL/bag (60 kg)", estimativa=False,
            fonte="SEAB/DERAL-PR, mean nominal monthly prices received by farmers in Paraná (state average; "
                  "the Toledo/Cascavel regional value only exists in the weekly series for the current week)",
            url=URL_PRECOS, pagina=URL_PAGINA_PRECOS,
            periodo=f"{cols[11].lower()} to {cols[0].lower()} (12-month average)",
            ultimo_mes=round(float(v.iloc[0]), 2))
    out["feijao"]["fonte"] += ". Beans = black type (predominant in Paraná; colored beans have a much higher price: validate the type)"
    m = out["milho"]
    out["sorgo"] = dict(
        valor=round(m["valor"] * RAZAO_SORGO_MILHO, 2), unidade="BRL/bag (60 kg)", estimativa=True,
        fonte=f"{ESTIM_VALIDAR}: SEAB/DERAL does not publish a sorghum price; uses {RAZAO_SORGO_MILHO:.0%} of the corn price (Paraná average, same period)",
        url=m["url"], pagina=m["pagina"], periodo=m["periodo"], ultimo_mes=round(m["ultimo_mes"] * RAZAO_SORGO_MILHO, 2))
    return out


def _linhas(f: Path, aba: str) -> dict:
    d = pd.read_excel(f, sheet_name=aba, header=None).dropna(how="all").dropna(how="all", axis=1)
    g = lambda pat: float(d[d[0].astype(str).str.contains(pat, regex=False)].iloc[0, 1])
    return dict(coe=g("CUSTO VARIÁVEL"), cot=g("CUSTO OPERACIONAL"), ct=g("CUSTO TOTAL"))


def custos() -> dict:
    out = {}
    for chave, (url, aba, rotulo) in {**CUSTOS, **CUSTO_PROXY}.items():
        f = _baixar(url, f"conab_{chave}.xls")
        l = _linhas(f, aba)
        out[chave] = dict(
            coe=round(l["coe"], 2), cot=round(l["cot"], 2), ct=round(l["ct"], 2), unidade="R$/ha", estimativa=chave in CUSTO_PROXY,
            fonte=rotulo + ". coe = 'variable cost' (operating inputs + other expenses + financial costs, cash outlay); "
                  "cot = 'operating cost' (coe + depreciation and other fixed costs); ct = cot + returns to factors",
            url=url, aba=aba, consulta=str(date.today()), curto=CURTO[chave])
    for chave, (v, desc) in COBERTURAS.items():
        out[chave] = dict(coe=v, cot=v, ct=v, unidade="R$/ha", estimativa=True,
                          fonte=f"{ESTIM_VALIDAR if chave in ('nabo_forrageiro', 'aveia_nabo') else ESTIM}: {desc}", url=None,
                          curto="reference estimate, to be validated")
    return out


def main():
    ref = dict(consulta=str(date.today()), linha_custo_padrao="coe", precos=precos(), custos=custos())
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps(ref, ensure_ascii=False, indent=2))
    print("gravado", SAIDA)
    print(json.dumps({k: v["valor"] for k, v in ref["precos"].items()}), {k: (v["coe"], v["cot"]) for k, v in ref["custos"].items()})


if __name__ == "__main__":
    main()
