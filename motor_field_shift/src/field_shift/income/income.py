"""Margem por cultura e por rotação. Lógica pura (sem Streamlit).

margem_cultura = rendimento_municipal (sc/ha, PAM: tendência dos últimos 10 anos projetada para a próxima safra, limitada ao
mín–máx da janela; pam.produtividade.expected_yield) × preço − custo.
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

from field_shift.pam import productivity as pam_yield
from field_shift.pam.productivity import PAM, YIELD_WINDOW_YEARS, series

ROOT = Path(__file__).resolve().parents[3]
REF = ROOT / "data/ref/precos_custos.json"
OESTE_MUNICIPALITIES = ROOT / "data/raw/regiao/municipios_oeste_pr.geojson"
# Piso (R$/ha) da escala S do critério de renda: evita que uma soja de margem muito baixa/negativa (preço baixo, custo
# alto) estique a escala e faça qualquer diferença pequena saturar a nota em 0 ou 1.
INCOME_SCALE_MIN = 1000.0
# cultura vendida -> chave do preço (rendimento e custo usam a própria chave de cultura)
CASH_CROPS = {"soja": "soja", "milho_2safra": "milho", "trigo": "trigo", "milho_1safra": "milho",
                  "feijao_2safra": "feijao", "sorgo": "sorgo"}
BASE_CROPS = ("soja", "milho_2safra", "trigo")  # PAM do município é exigida (senão, média do Oeste do PR para todas)
MIN_YEARS_EXTRA = 3  # culturas extras (milho 1ª safra, feijão, sorgo): o município precisa de ≥ 3 anos de PAM,
MIN_YEAR_EXTRA = 2018  # com o último ano ≥ 2018 (sorgo tem séries antigas e interrompidas); senão usa a média do Oeste
LABEL = {"soja": "Soja", "milho_2safra": "Milho 2ª safra", "trigo": "Trigo", "aveia": "Aveia (cobertura)",
          "milheto_crotalaria": "Milheto/crotalária (cobertura)", "braquiaria_consorcio": "Braquiária em consórcio",
          "pousio": "Pousio (manejo)", "milho_1safra": "Milho verão (1ª safra)", "feijao_2safra": "Feijão 2ª safra",
          "sorgo": "Sorgo", "nabo_forrageiro": "Nabo forrageiro (cobertura)", "aveia_nabo": "Aveia + nabo (cobertura)"}


@lru_cache(maxsize=1)
def load_reference() -> dict:
    return json.loads(REF.read_text())


@lru_cache(maxsize=1)
def _oeste_codes() -> tuple[str, ...]:
    """IBGE codes of the Oeste mesoregion municipalities (the PAM file now covers all of Paraná, but the regional
    average used as fallback stays the Oeste one: it is the region the price/cost references were built for)."""
    cods = {str(c) for c in gpd.read_file(OESTE_MUNICIPALITIES, columns=["cod_ibge"])["cod_ibge"]}
    d = pd.read_parquet(PAM, columns=["cod_ibge"])
    return tuple(sorted(cods & set(d["cod_ibge"].astype(str).unique())))


def _p20_sc(cod, cult: str) -> float | None:
    s = series(cod, cult)
    return float(np.percentile(s.iloc[-YIELD_WINDOW_YEARS:].values, 20) / 60) if len(s) >= 4 else None


def _serve(q: dict, c: str) -> bool:
    """A PAM do município serve para a cultura? Base: basta existir. Extras: ≥ MIN_ANOS_EXTRA anos e dado recente."""
    return c in q and (c in BASE_CROPS or (q[c]["n"] >= MIN_YEARS_EXTRA and int(q[c]["anos"][-4:]) >= MIN_YEAR_EXTRA))


def _crop_yield(q: dict, cod, c: str) -> dict:
    p20 = _p20_sc(cod, c)
    p20 = None if p20 is None else min(p20, q[c]["sc_ha"])  # the bad year never above the expected yield
    return dict(sc_ha=q[c]["sc_ha"], cv=q[c]["cv"], p20_sc_ha=p20, anos=q[c]["anos"], media_sc_ha=q[c]["media_sc_ha"],
                metodo=q[c]["metodo"])


def _oeste_mean(c: str) -> dict:
    """Média dos municípios do Oeste do PR com PAM da cultura `c` (extras: só com ≥ MIN_ANOS_EXTRA anos)."""
    v = []
    for cod in _oeste_codes():
        q = pam_yield(cod)
        if _serve(q, c):
            p20 = _p20_sc(cod, c)
            v.append((q[c]["sc_ha"], q[c]["cv"], None if p20 is None else min(p20, q[c]["sc_ha"]), q[c]["anos"],
                      q[c]["media_sc_ha"]))
    a = np.array([[x if x is not None else np.nan for x in t[:3]] for t in v], dtype=float)
    cv, p20 = (float(np.nanmean(a[:, k])) if not np.all(np.isnan(a[:, k])) else None for k in (1, 2))
    return dict(sc_ha=float(np.nanmean(a[:, 0])), cv=cv, p20_sc_ha=p20, anos=v[-1][3], n_municipios=len(v),
                media_sc_ha=float(np.mean([t[4] for t in v])), metodo="tendência")


@lru_cache(maxsize=64)
def yields(cod_ibge: str | None) -> dict:
    """{cultura: dict(sc_ha, cv, p20_sc_ha, anos)} + chaves '_origem' e '_regionais'. Sem município (ou sem PAM das culturas base),
    usa a média dos municípios do Oeste do PR na PAM ('_origem' avisa). As culturas extras (milho 1ª safra, feijão 2ª safra,
    sorgo) sem PAM suficiente no município usam a média do Oeste do PR, listadas em '_regionais'."""
    p = pam_yield(cod_ibge) if cod_ibge else {}
    com_base = bool(p) and all(c in p for c in BASE_CROPS)
    out, regional = {}, []
    for c in CASH_CROPS:
        if com_base and _serve(p, c):
            out[c] = _crop_yield(p, cod_ibge, c)
        else:
            out[c] = _oeste_mean(c)
            regional.append(c)
    out["_regionais"] = regional if com_base else []  # sem PAM base, '_origem' já avisa que tudo é média do Oeste
    out["_origem"] = (f"PAM do município (cód. IBGE {cod_ibge})" if com_base else
                      f"média dos {len(_oeste_codes())} municípios do Oeste do PR na PAM (talhão fora da região ou sem PAM do município)")
    return out


def _price(ref, aj, k): return float((aj.get("preco") or {}).get(k, ref["precos"][k]["valor"]))


def _cost(ref, aj, k):
    ov = (aj.get("custo") or {})
    if k in ov:
        return float(ov[k])
    return float(ref["custos"][k][aj.get("linha_custo") or ref.get("linha_custo_padrao", "coe")])


def _effective_yield(rend: dict, aj: dict) -> dict:
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


def yield_cost_factor(ref: dict, aj: dict, k: str, sc_ha: float) -> float | None:
    """Ratio local yield / CONAB reference yield, for crops whose CONAB cost sheet has a yield-driven split.

    None when the crop has no split or the farmer typed their own cost (their number is used as given).
    """
    scale = ref["custos"][k].get("escala_produtividade")
    if scale is None or k in (aj.get("custo") or {}):
        return None
    return sc_ha / scale["referencia_sc_ha"]


def _scaled_cost(ref: dict, k: str, cost: float, factor: float | None) -> float:
    """Remove the yield-driven share of `cost` that the local yield does not justify (applies to every cost line:
    the fixed lines `cot`/`ct` only add costs that do not depend on yield)."""
    if factor is None:
        return cost
    return cost - ref["custos"][k]["escala_produtividade"]["proporcional_r_ha"] * (1 - factor)


def _item(ref, aj, rend, k, yield_="sc_ha") -> dict:
    c = _cost(ref, aj, k)
    factor = None
    if k in CASH_CROPS:
        factor = yield_cost_factor(ref, aj, k, rend[k]["sc_ha"])
        c_base = c
        c = _scaled_cost(ref, k, c, factor)  # a bad year keeps the same cost: inputs are already spent
        pk = CASH_CROPS[k]
        pr = _price(ref, aj, pk)
        sc = rend[k]["sc_ha"]
        bad = rend[k]["p20_sc_ha"]
        return dict(chave=k, rotulo=LABEL[k], sc_ha=sc, preco=pr, custo=c, custo_base=c_base, fator_escala_custo=factor,
                    preco_usuario=pk in (aj.get("preco") or {}),
                    custo_usuario=k in (aj.get("custo") or {}), receita=sc * pr, margem=sc * pr - c,
                    cv=rend[k]["cv"], anos=rend[k]["anos"],
                    margem_ano_ruim=None if bad is None else bad * pr - c, sc_ha_ruim=bad,
                    prod_usuario=bool(rend[k].get("usuario")), razao_p20=rend[k].get("razao_p20"), sc_ha_pam=rend[k].get("sc_ha_pam"),
                    sc_ha_media=rend[k].get("media_sc_ha"), metodo_rend=rend[k].get("metodo"))
    return dict(chave=k, rotulo=LABEL[k], sc_ha=None, preco=None, custo=c, preco_usuario=False,
                custo_usuario=k in (aj.get("custo") or {}), receita=0.0, margem=-c, cv=None, anos=None,
                margem_ano_ruim=-c, sc_ha_ruim=None)


def _item_extra(e: dict) -> dict:
    """Custo extra (terceirização de máquina, irrigação): sem venda, margem = −custo. `e`: chave, rotulo, custo, detalhe."""
    return dict(chave=e["chave"], rotulo=e["rotulo"], sc_ha=None, preco=None, custo=float(e["custo"]), preco_usuario=False,
                custo_usuario=False, receita=0.0, margem=-float(e["custo"]), cv=None, anos=None,
                margem_ano_ruim=-float(e["custo"]), sc_ha_ruim=None, extra=True, detalhe=e["detalhe"])


def compute_margins(catalog: dict, rend: dict, adjustments: dict | None = None, extras: dict | None = None) -> dict:
    """Para cada candidata: itens (soja, 2ª cultura/cobertura, extras), bônus, total, margem incremental (sem a soja) e escala S.
    `ajustes`: {'preco': {soja|milho|trigo: R$/sc}, 'custo': {chave: R$/ha}, 'linha_custo': 'coe'|'cot'|'ct',
    'produtividade': {soja|milho_2safra|trigo: sc/ha}}. `extras`: {candidata: [dict(chave, rotulo, custo, detalhe)]} (custos extras)."""
    ref, aj = load_reference(), adjustments or {}
    rend = _effective_yield(rend, aj)
    extras = extras or {}
    soy_price = _price(ref, aj, "soja")
    soy = _item(ref, aj, rend, "soja")
    out = {}
    for nome, c in catalog.items():
        summer = c.get("item_renda_verao", "soja")  # cultura de verão: soja (padrão) ou milho_1safra
        items = ([soy] if summer == "soja" else [_item(ref, aj, rend, summer)]) + [_item(ref, aj, rend, k) for k in c["renda_itens"]] \
            + [_item_extra(e) for e in extras.get(nome, [])]
        bonus = c["bonus_sc"] * soy_price
        total = sum(i["margem"] for i in items) + bonus
        incremental = total - soy["margem"]
        scale = max(soy["margem"], INCOME_SCALE_MIN)
        bad = [i["margem_ano_ruim"] for i in items]
        out[nome] = dict(linha_custo=aj.get("linha_custo") or ref.get("linha_custo_padrao", "coe"), itens=items, bonus_sc=c["bonus_sc"],
                         bonus_verao_sc=c.get("bonus_verao_sc", 0.0), preco_soja=soy_price, bonus=bonus, total=total,
                         incremental=incremental, escala_S=scale,
                         total_ano_ruim=None if None in bad else sum(bad) + bonus)
    return out


def _fmt(x: float) -> str:
    return f"{x:,.0f}".replace(",", ".")


COST_LINE_NAME = {"coe": "custo variável (≈COE)", "cot": "COT", "ct": "CT"}


def cost_source(i: dict, line: str) -> str:
    """Texto curto da origem do custo de um item (para tabela e card)."""
    if i.get("extra"):
        return i["detalhe"]
    if i["custo_usuario"]:
        return "informado pelo usuário"
    c = load_reference()["custos"][i["chave"]]
    text = c["curto"] if c["estimativa"] else f"{c['curto']}, {COST_LINE_NAME[line]}"
    f = i.get("fator_escala_custo")
    if f is not None:
        ref_sc = c["escala_produtividade"]["referencia_sc_ha"]
        text += (f"; fertilizantes, transporte, armazenagem e CESSR ajustados à produtividade local "
                  f"({i['sc_ha']:.0f} sc/ha contra {ref_sc:.0f} sc/ha da referência CONAB) — estimativa, validar")
    return text


def price_source(i: dict) -> str:
    if i["preco"] is None:
        return "-"
    if i["preco_usuario"]:
        return "informado pelo usuário"
    p = load_reference()["precos"][CASH_CROPS[i["chave"]]]
    if p.get("estimativa"):
        return f"estimativa — validar: {p.get('razao_sobre_milho', 0.8):.0%} do preço do milho SEAB/DERAL-PR (razão dos preços mínimos CONAB, não de mercado)"
    return f"SEAB/DERAL-PR, média PR {p['periodo'].split(' (')[0]}"
