"""Margem por cultura e por rotação. Lógica pura (sem Streamlit).

margem_cultura = rendimento_municipal (sc/ha, PAM, média dos últimos 5 anos) × preço − custo.
Cobertura/pousio: − custo. margem_rotacao = soja + 2ª cultura + bônus na soja seguinte (bonus_sc × preço da soja).
margem_incremental = margem_rotacao − margem da soja = margem da 2ª cultura + bônus (a soja é comum a todas as candidatas).
Critério de renda (nota): clip(0,5 + incremental / (2·S), 0, 1), S = max(margem da soja do município, RENDA_ESCALA_MIN).
Referências em data/ref/precos_custos.json (gerado por field_shift.renda.atualizar).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from field_shift.pam import produtividade as pam_produtividade
from field_shift.pam.produtividade import PAM, serie

ROOT = Path(__file__).resolve().parents[3]
REF = ROOT / "data/ref/precos_custos.json"
# Piso (R$/ha) da escala S do critério de renda: evita que uma soja de margem muito baixa/negativa (preço baixo, custo
# alto) estique a escala e faça qualquer diferença pequena saturar a nota em 0 ou 1.
RENDA_ESCALA_MIN = 1000.0
# cultura vendida -> chave do preço (rendimento e custo usam a própria chave de cultura)
CULTURAS_VENDA = {"soja": "soja", "milho_2safra": "milho", "trigo": "trigo"}
ROTULO = {"soja": "Soja", "milho_2safra": "Milho 2ª safra", "trigo": "Trigo", "aveia": "Aveia (cobertura)",
          "milheto_crotalaria": "Milheto/crotalária (cobertura)", "braquiaria_consorcio": "Braquiária em consórcio",
          "pousio": "Pousio (manejo)"}


@lru_cache(maxsize=1)
def carregar_referencia() -> dict:
    return json.loads(REF.read_text())


@lru_cache(maxsize=1)
def _cods_oeste() -> tuple[str, ...]:
    d = pd.read_parquet(PAM, columns=["cod_ibge"])
    return tuple(sorted(d["cod_ibge"].astype(str).unique()))


def _p20_sc(cod, cult: str) -> float | None:
    s = serie(cod, cult)
    return float(np.percentile(s.iloc[-10:].values, 20) / 60) if len(s) >= 4 else None


@lru_cache(maxsize=64)
def rendimentos(cod_ibge: str | None) -> dict:
    """{cultura: dict(sc_ha, cv, p20_sc_ha, anos)} + chave '_origem'. Sem município (ou sem PAM), usa a média dos
    municípios do Oeste do PR na PAM (e '_origem' avisa)."""
    p = pam_produtividade(cod_ibge) if cod_ibge else {}
    if p and all(c in p for c in CULTURAS_VENDA):
        out = {c: dict(sc_ha=p[c]["sc_ha"], cv=p[c]["cv"], p20_sc_ha=_p20_sc(cod_ibge, c), anos=p[c]["anos"])
               for c in CULTURAS_VENDA}
        out["_origem"] = f"PAM do município (cód. IBGE {cod_ibge})"
        return out
    per = [pam_produtividade(c) for c in _cods_oeste()]
    out = {}
    for c in CULTURAS_VENDA:
        v = [(q[c]["sc_ha"], q[c]["cv"], _p20_sc(cod, c)) for q, cod in zip(per, _cods_oeste()) if c in q]
        a = np.array([[x if x is not None else np.nan for x in t] for t in v], dtype=float)
        out[c] = dict(sc_ha=float(np.nanmean(a[:, 0])), cv=float(np.nanmean(a[:, 1])), p20_sc_ha=float(np.nanmean(a[:, 2])),
                      anos=next(q[c]["anos"] for q in per if c in q))
    out["_origem"] = (f"média dos {len(per)} municípios do Oeste do PR na PAM (talhão fora da região ou sem PAM do município)")
    return out


def _preco(ref, aj, k): return float((aj.get("preco") or {}).get(k, ref["precos"][k]["valor"]))


def _custo(ref, aj, k):
    ov = (aj.get("custo") or {})
    if k in ov:
        return float(ov[k])
    return float(ref["custos"][k][aj.get("linha_custo") or ref.get("linha_custo_padrao", "coe")])


def _item(ref, aj, rend, k, rendimento="sc_ha") -> dict:
    c = _custo(ref, aj, k)
    if k in CULTURAS_VENDA:
        pk = CULTURAS_VENDA[k]
        pr = _preco(ref, aj, pk)
        sc = rend[k]["sc_ha"]
        ruim = rend[k]["p20_sc_ha"]
        return dict(chave=k, rotulo=ROTULO[k], sc_ha=sc, preco=pr, custo=c, preco_usuario=pk in (aj.get("preco") or {}),
                    custo_usuario=k in (aj.get("custo") or {}), receita=sc * pr, margem=sc * pr - c,
                    cv=rend[k]["cv"], anos=rend[k]["anos"],
                    margem_ano_ruim=None if ruim is None else ruim * pr - c, sc_ha_ruim=ruim)
    return dict(chave=k, rotulo=ROTULO[k], sc_ha=None, preco=None, custo=c, preco_usuario=False,
                custo_usuario=k in (aj.get("custo") or {}), receita=0.0, margem=-c, cv=None, anos=None,
                margem_ano_ruim=-c, sc_ha_ruim=None)


def calcular_margens(catalogo: dict, rend: dict, ajustes: dict | None = None) -> dict:
    """Para cada candidata: itens (soja, 2ª cultura/cobertura, extras), bônus, total, margem incremental (sem a soja) e escala S.
    `ajustes`: {'preco': {soja|milho|trigo: R$/sc}, 'custo': {chave: R$/ha}, 'linha_custo': 'coe'|'cot'|'ct'}."""
    ref, aj = carregar_referencia(), ajustes or {}
    preco_soja = _preco(ref, aj, "soja")
    soja = _item(ref, aj, rend, "soja")
    out = {}
    for nome, c in catalogo.items():
        itens = [soja] + [_item(ref, aj, rend, k) for k in c["renda_itens"]]
        bonus = c["bonus_sc"] * preco_soja
        total = sum(i["margem"] for i in itens) + bonus
        incremental = total - soja["margem"]
        escala = max(soja["margem"], RENDA_ESCALA_MIN)
        ruim = [i["margem_ano_ruim"] for i in itens]
        out[nome] = dict(linha_custo=aj.get("linha_custo") or ref.get("linha_custo_padrao", "coe"), itens=itens, bonus_sc=c["bonus_sc"], preco_soja=preco_soja, bonus=bonus, total=total,
                         incremental=incremental, escala_S=escala,
                         total_ano_ruim=None if None in ruim else sum(ruim) + bonus)
    return out


def _fmt(x: float) -> str:
    return f"{x:,.0f}".replace(",", ".")


LINHA_NOME = {"coe": "custo variável (≈COE)", "cot": "COT", "ct": "CT"}


def fonte_custo(i: dict, linha: str) -> str:
    """Texto curto da origem do custo de um item (para tabela e card)."""
    if i["custo_usuario"]:
        return "informado pelo usuário"
    c = carregar_referencia()["custos"][i["chave"]]
    return c["curto"] if c["estimativa"] else f"{c['curto']}, {LINHA_NOME[linha]}"


def fonte_preco(i: dict) -> str:
    if i["preco"] is None:
        return "-"
    if i["preco_usuario"]:
        return "informado pelo usuário"
    p = carregar_referencia()["precos"][CULTURAS_VENDA[i["chave"]]]
    return f"SEAB/DERAL-PR, média PR {p['periodo'].split(' (')[0]}"
