"""Margem por cultura e por rotação. Lógica pura (sem Streamlit).

margem_cultura = rendimento_municipal (sc/ha, PAM, média dos últimos 10 anos) × preço − custo.
Cobertura/pousio: − custo. margem_rotacao = cultura de verão (soja ou milho verão) + 2ª cultura + bônus na soja seguinte
(bonus_sc × preço da soja; inclui o bônus do milho verão no lugar da soja).
margem_incremental = margem_rotacao − margem da soja de verão do município = (margem do verão − margem da soja) + margem da 2ª
cultura + bônus. Com soja no verão o 1º termo é zero (a soja é comum a essas candidatas).
Critério de renda (nota): clip(0,5 + incremental / (2·S), 0, 1), S = max(margem da soja do município, RENDA_ESCALA_MIN).
Referências em data/ref/precos_custos.json (gerado por field_shift.renda.atualizar).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from field_shift.pam import produtividade as pam_produtividade
from field_shift.pam.produtividade import PAM, YIELD_WINDOW_YEARS, serie

ROOT = Path(__file__).resolve().parents[3]
REF = ROOT / "data/ref/precos_custos.json"
OESTE_MUN = ROOT / "data/raw/regiao/municipios_oeste_pr.geojson"
# Piso (R$/ha) da escala S do critério de renda: evita que uma soja de margem muito baixa/negativa (preço baixo, custo
# alto) estique a escala e faça qualquer diferença pequena saturar a nota em 0 ou 1.
RENDA_ESCALA_MIN = 1000.0
# cultura vendida -> chave do preço (rendimento e custo usam a própria chave de cultura)
CULTURAS_VENDA = {"soja": "soja", "milho_2safra": "milho", "trigo": "trigo", "milho_1safra": "milho",
                  "feijao_2safra": "feijao", "sorgo": "sorgo"}
CULTURAS_BASE = ("soja", "milho_2safra", "trigo")  # PAM do município é exigida (senão, média do Oeste do PR para todas)
MIN_ANOS_EXTRA = 3  # culturas extras (milho 1ª safra, feijão, sorgo): o município precisa de ≥ 3 anos de PAM,
ANO_MIN_EXTRA = 2018  # com o último ano ≥ 2018 (sorgo tem séries antigas e interrompidas); senão usa a média do Oeste
ROTULO = {"soja": "Soja", "milho_2safra": "Milho 2ª safra", "trigo": "Trigo", "aveia": "Aveia (cobertura)",
          "milheto_crotalaria": "Milheto/crotalária (cobertura)", "braquiaria_consorcio": "Braquiária em consórcio",
          "pousio": "Pousio (manejo)", "milho_1safra": "Milho verão (1ª safra)", "feijao_2safra": "Feijão 2ª safra",
          "sorgo": "Sorgo", "nabo_forrageiro": "Nabo forrageiro (cobertura)", "aveia_nabo": "Aveia + nabo (cobertura)"}


@lru_cache(maxsize=1)
def carregar_referencia() -> dict:
    return json.loads(REF.read_text())


@lru_cache(maxsize=1)
def _cods_oeste() -> tuple[str, ...]:
    """IBGE codes of the Oeste mesoregion municipalities (the PAM file now covers all of Paraná, but the regional
    average used as fallback stays the Oeste one: it is the region the price/cost references were built for)."""
    cods = {str(c) for c in gpd.read_file(OESTE_MUN, columns=["cod_ibge"])["cod_ibge"]}
    d = pd.read_parquet(PAM, columns=["cod_ibge"])
    return tuple(sorted(cods & set(d["cod_ibge"].astype(str).unique())))


def _p20_sc(cod, cult: str) -> float | None:
    s = serie(cod, cult)
    return float(np.percentile(s.iloc[-YIELD_WINDOW_YEARS:].values, 20) / 60) if len(s) >= 4 else None


def _serve(q: dict, c: str) -> bool:
    """A PAM do município serve para a cultura? Base: basta existir. Extras: ≥ MIN_ANOS_EXTRA anos e dado recente."""
    return c in q and (c in CULTURAS_BASE or (q[c]["n"] >= MIN_ANOS_EXTRA and int(q[c]["anos"][-4:]) >= ANO_MIN_EXTRA))


def _rend_cultura(q: dict, cod, c: str) -> dict:
    return dict(sc_ha=q[c]["sc_ha"], cv=q[c]["cv"], p20_sc_ha=_p20_sc(cod, c), anos=q[c]["anos"])


def _media_oeste(c: str) -> dict:
    """Média dos municípios do Oeste do PR com PAM da cultura `c` (extras: só com ≥ MIN_ANOS_EXTRA anos)."""
    v = []
    for cod in _cods_oeste():
        q = pam_produtividade(cod)
        if _serve(q, c):
            v.append((q[c]["sc_ha"], q[c]["cv"], _p20_sc(cod, c), q[c]["anos"]))
    a = np.array([[x if x is not None else np.nan for x in t[:3]] for t in v], dtype=float)
    cv, p20 = (float(np.nanmean(a[:, k])) if not np.all(np.isnan(a[:, k])) else None for k in (1, 2))
    return dict(sc_ha=float(np.nanmean(a[:, 0])), cv=cv, p20_sc_ha=p20, anos=v[-1][3], n_municipios=len(v))


@lru_cache(maxsize=64)
def rendimentos(cod_ibge: str | None) -> dict:
    """{cultura: dict(sc_ha, cv, p20_sc_ha, anos)} + chaves '_origem' e '_regionais'. Sem município (ou sem PAM das culturas base),
    usa a média dos municípios do Oeste do PR na PAM ('_origem' avisa). As culturas extras (milho 1ª safra, feijão 2ª safra,
    sorgo) sem PAM suficiente no município usam a média do Oeste do PR, listadas em '_regionais'."""
    p = pam_produtividade(cod_ibge) if cod_ibge else {}
    com_base = bool(p) and all(c in p for c in CULTURAS_BASE)
    out, regionais = {}, []
    for c in CULTURAS_VENDA:
        if com_base and _serve(p, c):
            out[c] = _rend_cultura(p, cod_ibge, c)
        else:
            out[c] = _media_oeste(c)
            regionais.append(c)
    out["_regionais"] = regionais if com_base else []  # sem PAM base, '_origem' já avisa que tudo é média do Oeste
    out["_origem"] = (f"PAM do município (cód. IBGE {cod_ibge})" if com_base else
                      f"média dos {len(_cods_oeste())} municípios do Oeste do PR na PAM (talhão fora da região ou sem PAM do município)")
    return out


def _preco(ref, aj, k): return float((aj.get("preco") or {}).get(k, ref["precos"][k]["valor"]))


def _custo(ref, aj, k):
    ov = (aj.get("custo") or {})
    if k in ov:
        return float(ov[k])
    return float(ref["custos"][k][aj.get("linha_custo") or ref.get("linha_custo_padrao", "coe")])


def _rend_efetivo(rend: dict, aj: dict) -> dict:
    """Aplica `aj['produtividade']` ({soja|milho_2safra|trigo|milho_1safra|feijao_2safra|sorgo: sc/ha}) sobre o rendimento PAM. O rendimento do ano ruim
    escala proporcionalmente: próprio × (p20 / média da PAM)."""
    prod = aj.get("produtividade") or {}
    if not prod:
        return rend
    out = dict(rend)
    for k, v in prod.items():
        r = dict(rend[k])
        f = float(v) / r["sc_ha"]
        r["p20_sc_ha"] = None if r["p20_sc_ha"] is None else r["p20_sc_ha"] * f
        r["razao_p20"] = None if rend[k]["p20_sc_ha"] is None else rend[k]["p20_sc_ha"] / rend[k]["sc_ha"]
        r["sc_ha_pam"] = rend[k]["sc_ha"]
        r["sc_ha"], r["usuario"] = float(v), True
        out[k] = r
    return out


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
                    margem_ano_ruim=None if ruim is None else ruim * pr - c, sc_ha_ruim=ruim,
                    prod_usuario=bool(rend[k].get("usuario")), razao_p20=rend[k].get("razao_p20"), sc_ha_pam=rend[k].get("sc_ha_pam"))
    return dict(chave=k, rotulo=ROTULO[k], sc_ha=None, preco=None, custo=c, preco_usuario=False,
                custo_usuario=k in (aj.get("custo") or {}), receita=0.0, margem=-c, cv=None, anos=None,
                margem_ano_ruim=-c, sc_ha_ruim=None)


def _item_extra(e: dict) -> dict:
    """Custo extra (terceirização de máquina, irrigação): sem venda, margem = −custo. `e`: chave, rotulo, custo, detalhe."""
    return dict(chave=e["chave"], rotulo=e["rotulo"], sc_ha=None, preco=None, custo=float(e["custo"]), preco_usuario=False,
                custo_usuario=False, receita=0.0, margem=-float(e["custo"]), cv=None, anos=None,
                margem_ano_ruim=-float(e["custo"]), sc_ha_ruim=None, extra=True, detalhe=e["detalhe"])


def calcular_margens(catalogo: dict, rend: dict, ajustes: dict | None = None, extras: dict | None = None) -> dict:
    """Para cada candidata: itens (soja, 2ª cultura/cobertura, extras), bônus, total, margem incremental (sem a soja) e escala S.
    `ajustes`: {'preco': {soja|milho|trigo: R$/sc}, 'custo': {chave: R$/ha}, 'linha_custo': 'coe'|'cot'|'ct',
    'produtividade': {soja|milho_2safra|trigo: sc/ha}}. `extras`: {candidata: [dict(chave, rotulo, custo, detalhe)]} (custos extras)."""
    ref, aj = carregar_referencia(), ajustes or {}
    rend = _rend_efetivo(rend, aj)
    extras = extras or {}
    preco_soja = _preco(ref, aj, "soja")
    soja = _item(ref, aj, rend, "soja")
    out = {}
    for nome, c in catalogo.items():
        verao = c.get("item_renda_verao", "soja")  # cultura de verão: soja (padrão) ou milho_1safra
        itens = ([soja] if verao == "soja" else [_item(ref, aj, rend, verao)]) + [_item(ref, aj, rend, k) for k in c["renda_itens"]] \
            + [_item_extra(e) for e in extras.get(nome, [])]
        bonus = c["bonus_sc"] * preco_soja
        total = sum(i["margem"] for i in itens) + bonus
        incremental = total - soja["margem"]
        escala = max(soja["margem"], RENDA_ESCALA_MIN)
        ruim = [i["margem_ano_ruim"] for i in itens]
        out[nome] = dict(linha_custo=aj.get("linha_custo") or ref.get("linha_custo_padrao", "coe"), itens=itens, bonus_sc=c["bonus_sc"],
                         bonus_verao_sc=c.get("bonus_verao_sc", 0.0), preco_soja=preco_soja, bonus=bonus, total=total,
                         incremental=incremental, escala_S=escala,
                         total_ano_ruim=None if None in ruim else sum(ruim) + bonus)
    return out


def _fmt(x: float) -> str:
    return f"{x:,.0f}".replace(",", ".")


LINHA_NOME = {"coe": "custo variável (≈COE)", "cot": "COT", "ct": "CT"}


def fonte_custo(i: dict, linha: str) -> str:
    """Texto curto da origem do custo de um item (para tabela e card)."""
    if i.get("extra"):
        return i["detalhe"]
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
    if p.get("estimativa"):
        return "estimativa — validar: 80% do preço do milho SEAB/DERAL-PR"
    return f"SEAB/DERAL-PR, média PR {p['periodo'].split(' (')[0]}"
