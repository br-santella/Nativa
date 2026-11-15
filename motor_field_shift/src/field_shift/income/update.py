"""Baixa preços (SEAB/DERAL-PR) e custos (CONAB) e grava data/ref/precos_custos.json.

Uso:  uv run python -m field_shift.renda.atualizar
Os brutos ficam em data/raw/renda/ (fora do git); o JSON final é pequeno e vai para o git.
Coberturas/pousio NÃO têm fonte oficial: são estimativas de referência marcadas no JSON.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "data/raw/renda"
OUTPUT = ROOT / "data/ref/precos_custos.json"
UA = {"User-Agent": "Mozilla/5.0"}

PRICES_URL = "https://www.agricultura.pr.gov.br/system/files/publico/Precos/pmrp.xls"
PRICES_PAGE_URL = "https://www.agricultura.pr.gov.br/deral/Precos"
CONAB = ("https://www.gov.br/conab/pt-br/atuacao/informacoes-agropecuarias/custos-de-producao/"
         "arquivos-custo-de-producao/agricolas/")
# (arquivo, aba, rótulo humano)
COSTS = {
    "soja": (CONAB + "serie-historica-custos-soja-1997-a-2026.xls", "OGM-Londrina-PR-2026",
             "CONAB, soja OGM plantio direto alta tecnologia, agricultura empresarial, Londrina-PR, 1ª safra 2026/27 (estimado, mar/2026)"),
    "milho_2safra": (CONAB + "milho/milho_2a_safra_serie_historica_2005-2026.xls", "Londrina-PR-2026",
                     "CONAB, milho 2ª safra OGM plantio direto alta tecnologia, agricultura empresarial, Londrina-PR, 2026 (estimado, mar/2026)"),
    "trigo": (CONAB + "seriehistoricacustostrigo1998a2025.xls", "Ponta Grossa-PR-2025-11",
              "CONAB, trigo plantio direto alta tecnologia, agricultura empresarial, Ponta Grossa-PR, safra de inverno 2025 (ex-post, nov/2025)"),
    # milho de verão (1ª safra): só há planilha PR em Ponta Grossa/Guarapuava (produtividade de referência 12 t/ha, maior que a do Oeste)
    "milho_1safra": (CONAB + "milho/milho_1a_safra_serie_historica_1997-2026.xls", "Ponta Grossa-PR-2026",
                     "CONAB, milho 1ª safra OGM plantio direto alta tecnologia, agricultura empresarial, Ponta Grossa-PR, 2026/27 (estimado, mar/2026; "
                     "produtividade de referência 12 t/ha, acima da média do Oeste do PR)"),
    "feijao_2safra": (CONAB + "feijao/feijao_2_e_3_safras_serie_historica_2013-2026.xls", "Francisco Beltrão-PR-2026",
                      "CONAB, feijão 2ª safra plantio direto alta tecnologia, agricultura familiar, Francisco Beltrão-PR, 2026 (estimado, mar/2026; "
                      "a planilha de Cascavel-PR só vai até 2021)"),
}
# Sem planilha CONAB do sorgo no PR: usa a do sorgo granífero 2ª safra de Rio Verde-GO como aproximação (marcada como estimativa).
PROXY_COST = {
    "sorgo": (CONAB + "seriehistoricacustossorgo2013a2026.xls", "Rio Verde-GO-2026",
              "estimativa — validar: não há planilha CONAB do sorgo no PR; usa CONAB, sorgo granífero 2ª safra OGM plantio direto alta tecnologia, "
              "agricultura empresarial, Rio Verde-GO, 2026 (estimado, mar/2026)"),
}
SHORT = {"soja": "CONAB Londrina-PR, safra 2026/27 (est. mar/2026)", "milho_2safra": "CONAB Londrina-PR, 2ª safra 2026 (est. mar/2026)",
         "trigo": "CONAB Ponta Grossa-PR, inverno 2025 (nov/2025)",
         "milho_1safra": "CONAB Ponta Grossa-PR, 1ª safra 2026/27 (est. mar/2026)",
         "feijao_2safra": "CONAB Francisco Beltrão-PR, 2ª safra 2026 (est. mar/2026)",
         "sorgo": "estimativa — validar (CONAB Rio Verde-GO 2026, sem planilha PR)"}
ESTIMATED = "estimativa de referência, validar (sem série CONAB; ordem de grandeza combinada com o time)"
COVER_CROPS = {  # R$/ha: ponto médio das faixas de referência
    "aveia": (375.0, "aveia como cobertura (semente + operação): faixa R$ 300–450/ha"),
    "milheto_crotalaria": (450.0, "milheto/crotalária (semente + operação): milheto ~R$ 300–450, crotalária ~R$ 400–600/ha"),
    "braquiaria_consorcio": (200.0, "braquiária em consórcio com o milho, adicional ao custo do milho: faixa R$ 150–250/ha"),
    "pousio": (200.0, "pousio: dessecação/manejo de plantas daninhas, faixa R$ 150–250/ha"),
    "nabo_forrageiro": (275.0, "nabo forrageiro como cobertura (10–15 kg/ha de semente + semeadura): faixa R$ 200–350/ha"),
    "aveia_nabo": (400.0, "mix aveia + nabo forrageiro como cobertura (semente das duas + semeadura): faixa R$ 350–450/ha"),
}
ESTIMATED_TO_VALIDATE = "estimativa — validar"
# Crops whose CONAB reference yield is far from the municipal PAM yield: their yield-driven cost is rescaled at runtime.
YIELD_SCALED_CROPS = ("milho_1safra",)
YIELD_DRIVEN_ITEMS = {"Fertilizantes": "9 - Fertilizantes", "Transporte externo": "14 - Transporte Externo",
                      "Armazenagem": "16 - Despesas de armazenagem", "CESSR": "23 - CESSR"}
# Sorghum price / corn price. There is no SEAB/DERAL or Cepea market series for grain sorghum in Paraná; the only official ratio found is the
# one between the CONAB/MAPA minimum prices of the 2026/27 crop for Sudeste and Paraná (sorghum R$ 40.19 / corn R$ 53.58 = 75.0%).
# It is a minimum-price ratio, not a market one: still an estimate.
SORGHUM_CORN_RATIO = 0.75
SORGHUM_RATIO_SOURCE = "relação entre os preços mínimos CONAB/MAPA da safra 2026/27 para Sudeste e Paraná (sorgo R$ 40,19 / milho R$ 53,58)"


def _download(url: str, nome: str) -> Path:
    RAW.mkdir(parents=True, exist_ok=True)
    f = RAW / nome
    r = requests.get(url, headers=UA, timeout=180)
    r.raise_for_status()
    f.write_bytes(r.content)
    return f


def prices() -> dict:
    f = _download(PRICES_URL, "seab_pmrp.xls")
    d = pd.read_excel(f, header=None)
    cols = d.iloc[1, 3:16].tolist()  # OUT/26 ... OUT/25 (mais recente primeiro)
    out = {}
    for key, product in (("soja", "Soja"), ("milho", "Milho"), ("trigo", "Trigo"), ("feijao", "Feijao preto")):
        r = d[d[1] == product].iloc[0]
        v = pd.to_numeric(r[3:15], errors="coerce").dropna()  # 12 meses mais recentes
        assert len(v) == 12, (product, len(v))
        out[key] = dict(
            valor=round(float(v.mean()), 2), unidade="R$/sc 60 kg", estimativa=False,
            fonte="SEAB/DERAL-PR, preços médios nominais mensais recebidos pelos produtores no Paraná (média do estado; "
                  "o regional Toledo/Cascavel só existe na série semanal da semana corrente)",
            url=PRICES_URL, pagina=PRICES_PAGE_URL,
            periodo=f"{cols[11].lower()} a {cols[0].lower()} (média de 12 meses)",
            ultimo_mes=round(float(v.iloc[0]), 2))
    out["feijao"]["fonte"] += (". Feijão = tipo preto: cerca de dois terços da área de 2ª safra do PR (estimativa do Deral reportada em 2026, data não confirmada); o feijão de cor tem preço bem maior (ex.: carioca/de cor R$ 360 contra preto R$ 320 em Apucarana na semana de 13/11/2026), então o resultado vale para o feijão preto")
    m = out["milho"]
    out["sorgo"] = dict(
        valor=round(m["valor"] * SORGHUM_CORN_RATIO, 2), unidade="R$/sc 60 kg", estimativa=True,
        fonte=f"{ESTIMATED_TO_VALIDATE}: a SEAB/DERAL não publica preço do sorgo; usa {SORGHUM_CORN_RATIO:.0%} do preço do milho (média PR, mesmo período), "
              f"razão dos preços mínimos, não de mercado: {SORGHUM_RATIO_SOURCE}",
        razao_sobre_milho=SORGHUM_CORN_RATIO,
        url=m["url"], pagina=m["pagina"], periodo=m["periodo"], ultimo_mes=round(m["ultimo_mes"] * SORGHUM_CORN_RATIO, 2))
    return out


def _rows(f: Path, tab: str) -> dict:
    d = pd.read_excel(f, sheet_name=tab, header=None).dropna(how="all").dropna(how="all", axis=1)
    g = lambda pat: float(d[d[0].astype(str).str.contains(pat, regex=False)].iloc[0, 1])
    return dict(coe=g("CUSTO VARIÁVEL"), cot=g("CUSTO OPERACIONAL"), ct=g("CUSTO TOTAL"))


def yield_scaling(f: Path, tab: str) -> dict:
    """Split the CONAB variable cost into the part that moves with yield and the part that does not.

    The CONAB sheet is built for a reference yield (e.g. 12 t/ha). When the municipal yield is lower, only the
    yield-driven line items shrink: fertilizer (dose is set from the yield target), external transport, storage and
    CESSR (levy on revenue). Seed, pesticides, machinery, labour, administration, technical assistance and interest
    stay fixed per hectare. This is a modelling premise, not a CONAB figure.
    """
    d = pd.read_excel(f, sheet_name=tab, header=None).dropna(how="all").dropna(how="all", axis=1)
    ref_kg = float(d[d[0].astype(str).str.contains("Produtividade Média", regex=False)].iloc[0, 0]
                   .split(":")[1].replace("kg/ha", "").strip().replace(".", "").replace(",", "."))
    parts = {}
    for label, pat in YIELD_DRIVEN_ITEMS.items():
        parts[label] = round(float(d[d[0].astype(str).str.contains(pat, regex=False)].iloc[0, 1]), 2)
    return dict(referencia_sc_ha=round(ref_kg / 60, 2), proporcional_r_ha=round(sum(parts.values()), 2), componentes=parts,
                premissa="estimativa — validar: só fertilizantes, transporte externo, armazenagem e CESSR escalam com a produtividade; "
                         "sementes, defensivos, máquinas, mão de obra, administração, assistência técnica e juros ficam fixos por hectare")


def costs() -> dict:
    out = {}
    for key, (url, tab, label) in {**COSTS, **PROXY_COST}.items():
        f = _download(url, f"conab_{key}.xls")
        l = _rows(f, tab)
        out[key] = dict(
            coe=round(l["coe"], 2), cot=round(l["cot"], 2), ct=round(l["ct"], 2), unidade="R$/ha", estimativa=key in PROXY_COST,
            fonte=label + ". coe = 'custo variável' (custeio + outras despesas + financeiras, desembolso); "
                  "cot = 'custo operacional' (coe + depreciações e outros custos fixos); ct = cot + renda de fatores",
            url=url, aba=tab, consulta=str(date.today()), curto=SHORT[key])
        if key in YIELD_SCALED_CROPS:
            out[key]["escala_produtividade"] = yield_scaling(f, tab)
    for key, (v, desc) in COVER_CROPS.items():
        out[key] = dict(coe=v, cot=v, ct=v, unidade="R$/ha", estimativa=True,
                          fonte=f"{ESTIMATED_TO_VALIDATE if key in ('nabo_forrageiro', 'aveia_nabo') else ESTIMATED}: {desc}", url=None,
                          curto="estimativa de referência, validar")
    return out


def main():
    ref = dict(consulta=str(date.today()), linha_custo_padrao="coe", precos=prices(), custos=costs())
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(ref, ensure_ascii=False, indent=2))
    print("gravado", OUTPUT)
    print(json.dumps({k: v["valor"] for k, v in ref["precos"].items()}), {k: (v["coe"], v["cot"]) for k, v in ref["custos"].items()})


if __name__ == "__main__":
    main()
