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
SAIDA = ROOT / "data/ref/precos_custos.json"
UA = {"User-Agent": "Mozilla/5.0"}

URL_PRECOS = "https://www.agricultura.pr.gov.br/system/files/publico/Precos/pmrp.xls"
URL_PAGINA_PRECOS = "https://www.agricultura.pr.gov.br/deral/Precos"
CONAB = ("https://www.gov.br/conab/pt-br/atuacao/informacoes-agropecuarias/custos-de-producao/"
         "arquivos-custo-de-producao/agricolas/")
# (arquivo, aba, rótulo humano)
CUSTOS = {
    "soja": (CONAB + "serie-historica-custos-soja-1997-a-2026.xls", "OGM-Londrina-PR-2026",
             "CONAB, soja OGM plantio direto alta tecnologia, agricultura empresarial, Londrina-PR, 1ª safra 2026/27 (estimado, mar/2026)"),
    "milho_2safra": (CONAB + "milho/milho_2a_safra_serie_historica_2005-2026.xls", "Londrina-PR-2026",
                     "CONAB, milho 2ª safra OGM plantio direto alta tecnologia, agricultura empresarial, Londrina-PR, 2026 (estimado, mar/2026)"),
    "trigo": (CONAB + "seriehistoricacustostrigo1998a2025.xls", "Ponta Grossa-PR-2025-11",
              "CONAB, trigo plantio direto alta tecnologia, agricultura empresarial, Ponta Grossa-PR, safra de inverno 2025 (ex-post, nov/2025)"),
}
CURTO = {"soja": "CONAB Londrina-PR, safra 2026/27 (est. mar/2026)", "milho_2safra": "CONAB Londrina-PR, 2ª safra 2026 (est. mar/2026)",
         "trigo": "CONAB Ponta Grossa-PR, inverno 2025 (nov/2025)"}
ESTIM = "estimativa de referência, validar (sem série CONAB; ordem de grandeza combinada com o time)"
COBERTURAS = {  # R$/ha: ponto médio das faixas de referência
    "aveia": (375.0, "aveia como cobertura (semente + operação): faixa R$ 300–450/ha"),
    "milheto_crotalaria": (450.0, "milheto/crotalária (semente + operação): milheto ~R$ 300–450, crotalária ~R$ 400–600/ha"),
    "braquiaria_consorcio": (200.0, "braquiária em consórcio com o milho, adicional ao custo do milho: faixa R$ 150–250/ha"),
    "pousio": (200.0, "pousio: dessecação/manejo de plantas daninhas, faixa R$ 150–250/ha"),
}


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
    cols = d.iloc[1, 3:16].tolist()  # OUT/26 ... OUT/25 (mais recente primeiro)
    out = {}
    for chave, produto in (("soja", "Soja"), ("milho", "Milho"), ("trigo", "Trigo")):
        r = d[d[1] == produto].iloc[0]
        v = pd.to_numeric(r[3:15], errors="coerce").dropna()  # 12 meses mais recentes
        assert len(v) == 12, (produto, len(v))
        out[chave] = dict(
            valor=round(float(v.mean()), 2), unidade="R$/sc 60 kg", estimativa=False,
            fonte="SEAB/DERAL-PR, preços médios nominais mensais recebidos pelos produtores no Paraná (média do estado; "
                  "o regional Toledo/Cascavel só existe na série semanal da semana corrente)",
            url=URL_PRECOS, pagina=URL_PAGINA_PRECOS,
            periodo=f"{cols[11].lower()} a {cols[0].lower()} (média de 12 meses)",
            ultimo_mes=round(float(v.iloc[0]), 2))
    return out


def _linhas(f: Path, aba: str) -> dict:
    d = pd.read_excel(f, sheet_name=aba, header=None).dropna(how="all").dropna(how="all", axis=1)
    g = lambda pat: float(d[d[0].astype(str).str.contains(pat, regex=False)].iloc[0, 1])
    return dict(coe=g("CUSTO VARIÁVEL"), cot=g("CUSTO OPERACIONAL"), ct=g("CUSTO TOTAL"))


def custos() -> dict:
    out = {}
    for chave, (url, aba, rotulo) in CUSTOS.items():
        f = _baixar(url, f"conab_{chave}.xls")
        l = _linhas(f, aba)
        out[chave] = dict(
            coe=round(l["coe"], 2), cot=round(l["cot"], 2), ct=round(l["ct"], 2), unidade="R$/ha", estimativa=False,
            fonte=rotulo + ". coe = 'custo variável' (custeio + outras despesas + financeiras, desembolso); "
                  "cot = 'custo operacional' (coe + depreciações e outros custos fixos); ct = cot + renda de fatores",
            url=url, aba=aba, consulta=str(date.today()), curto=CURTO[chave])
    for chave, (v, desc) in COBERTURAS.items():
        out[chave] = dict(coe=v, cot=v, ct=v, unidade="R$/ha", estimativa=True, fonte=f"{ESTIM}: {desc}", url=None,
                          curto="estimativa de referência, validar")
    return out


def main():
    ref = dict(consulta=str(date.today()), linha_custo_padrao="coe", precos=precos(), custos=custos())
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps(ref, ensure_ascii=False, indent=2))
    print("gravado", SAIDA)
    print(json.dumps({k: v["valor"] for k, v in ref["precos"].items()}), {k: (v["coe"], v["cot"]) for k, v in ref["custos"].items()})


if __name__ == "__main__":
    main()
