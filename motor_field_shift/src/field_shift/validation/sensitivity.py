"""Sensitivity of the rotation ranking to the engine's estimated parameters and to the farmer's weights.

The engine is never modified: each perturbation patches a copy of the catalog entries (``catalog_overrides``) or passes
price/cost overrides through the internal ``ajustes`` dict, and everything is restored afterwards.

Ranking = order of the valid candidates inside the block of the current summer crop (the ``agora`` block of the API).
"""
from __future__ import annotations

import contextlib
import copy
from dataclasses import dataclass, field
from typing import Callable, Iterator

import numpy as np
import pandas as pd
from scipy.stats import kendalltau

from field_shift.app import engine as E
from field_shift.core import service as S
from field_shift.income.income import load_reference

PERTURBATION = 0.20  # ±20 % one-at-a-time


@dataclass(frozen=True)
class Scenario:
    key: str
    description: str
    current: str = "soja__milho_safrinha"
    area: dict = field(default_factory=lambda: {"talhao_id": "72638"})
    stage: str | None = None
    harvest: str | None = None
    reference_date: str | None = "2026-12-01"
    sowing: str | None = None          # semeadura_safrinha (dd/mm); None = derived from stage/harvest
    irrigation: dict | None = None     # irrigacao, e.g. {"disponivel": True}


SCENARIOS = [
    Scenario("soy_grain_fill", "Field 72638, soybean in grain filling on 01/12 (harvest ~02/01, sowing 15/01)", stage="enchimento_graos"),
    Scenario("soy_default", "Field 72638, soybean, no stage (catalog assumption, sowing 01/02)", reference_date=None),
    Scenario("soy_late", "Field 72638, soybean harvested late (~25/02, sowing 01/03)", harvest="25/02"),
    Scenario("corn_milk", "Field 72638, summer corn in milk stage on 01/12 (current: summer corn → off-season corn)",
             current="milho_verao__milho_safrinha", stage="grao_leitoso"),
]


@dataclass
class Context:
    scenario: Scenario
    rk: dict
    weights: dict
    summer: str


def build_context(sc: Scenario) -> Context:
    """Climate/soil/yield context of the scenario, computed once (the expensive part) through the service internals."""
    inp = S._normalize_inputs(sc.sowing, None, sc.current, None, None, None, sc.irrigation, None, None)
    base = S._timeline_and_context(sc.area, inp, sc.sowing, sc.stage, sc.harvest, sc.reference_date)
    return Context(sc, base["rk"], inp["pesos_n"], inp["verao_atual"])


def rank(ctx: Context, weights: dict | None = None, adjustments: dict | None = None) -> pd.DataFrame:
    """Valid candidates of the current summer's block, best first (columns: id, nota and the 5 criteria)."""
    res = E.score_rotation(weights or ctx.weights, ctx.rk, adjustments or {}, None)
    tab = res["tabela"]
    tab = tab[tab["candidata"].map(lambda n: E.CATALOG[n]["verao"] == ctx.summer)].reset_index(drop=True)
    tab.insert(0, "id", tab["candidata"].map(lambda n: E.CATALOG[n]["id"]))
    return tab.drop(columns=["contrib"])


@contextlib.contextmanager
def catalog_overrides(fn: Callable[[dict], None]) -> Iterator[None]:
    """Apply ``fn(entry)`` to a copy of every CATALOGO entry; restores the original entries on exit."""
    saved = {n: c for n, c in E.CATALOG.items()}
    try:
        for n, c in saved.items():
            new = copy.deepcopy(c)
            fn(new)
            E.CATALOG[n] = new
        yield
    finally:
        E.CATALOG.update(saved)


# --------------------------------------------------------------------------- parameters


@dataclass(frozen=True)
class Param:
    key: str            # stable id, e.g. "segunda.milho_braquiaria.bonus_sc"
    group: str          # catalog | penalty | cost | price
    label: str
    base: float
    patch: Callable[[float], Callable[[dict], None]] | None = None   # factor -> entry patcher
    adjust: Callable[[float], dict] | None = None                    # factor -> internal ajustes dict


def _second_patch(crop: str, attr: str, base: float):
    def make(f: float):
        def fn(c: dict):
            if c["segunda"] != crop:
                return
            v = base * f
            if attr == "bonus_sc":
                c["bonus_sc"] = v + c["bonus_verao_sc"]
            elif attr == "pragas":
                pen = E.CORN_ON_CORN_PENALTY if c["milho_sobre_milho"] else 0.0
                c["pragas_base"] = min(1.0, v)
                c["pragas"] = max(0.0, min(1.0, v) - pen)
            elif attr == "dias_descobertos":
                c[attr] = v
            else:
                c[attr] = min(1.0, v)
        return fn
    return make


def _summer_bonus_patch(f: float):
    def fn(c: dict):
        if c["verao"] == "milho_verao":
            c["bonus_verao_sc"] = E.SUMMER["milho_verao"]["bonus_sc"] * f
            c["bonus_sc"] = E.SECOND[c["segunda"]]["bonus_sc"] + c["bonus_verao_sc"]
    return fn


def _corn_on_corn_patch(f: float):
    def fn(c: dict):
        if c["milho_sobre_milho"]:
            c["pragas"] = max(0.0, c["pragas_base"] - E.CORN_ON_CORN_PENALTY * f)
    return fn


SECOND_ATTRS = {"bonus_sc": "bonus on following soybean (sc/ha)", "cobertura": "soil cover (0–1)",
                 "n_fix": "N fixation/cycling (0–1)", "dias_descobertos": "bare-soil days", "pragas": "pest-cycle break (0–1)"}


def parameters() -> list[Param]:
    """Every parameter flagged as an estimate in the catalog/reference, plus the market prices (data, but volatile)."""
    ps = []
    for crop, s in E.SECOND.items():
        if crop == "soja_safrinha":  # always eliminated by the hard rules
            continue
        for attr, lab in SECOND_ATTRS.items():
            if attr == "bonus_sc" and s[attr] == 0:
                continue
            ps.append(Param(f"segunda.{crop}.{attr}", "catalog", f"{s['nome']}: {lab}", float(s[attr]),
                            patch=_second_patch(crop, attr, float(s[attr]))))
    ps.append(Param("verao.milho_verao.bonus_sc", "catalog", "summer corn: bonus on following soybean (sc/ha)",
                    E.SUMMER["milho_verao"]["bonus_sc"], patch=_summer_bonus_patch))
    ps.append(Param("penalty.corn_on_corn", "penalty", "corn-on-corn pest penalty", E.CORN_ON_CORN_PENALTY,
                    patch=_corn_on_corn_patch))
    ref = load_reference()
    line = ref.get("linha_custo_padrao", "coe")
    for k, c in ref["custos"].items():
        if c.get("estimativa"):
            base = float(c[line])
            ps.append(Param(f"cost.{k}", "cost", f"cost of {k} (BRL/ha, estimate)", base,
                            adjust=lambda f, k=k, base=base: {"custo": {k: base * f}}))
    for k, p in ref["precos"].items():
        base = float(p["valor"])
        tag = "estimate" if p.get("estimativa") else "market"
        ps.append(Param(f"price.{k}", "price", f"price of {k} (BRL/sc, {tag})", base,
                        adjust=lambda f, k=k, base=base: {"preco": {k: base * f}}))
    return ps


# --------------------------------------------------------------------------- metrics


def compare(base: list[str], new: list[str]) -> dict:
    """top-1 change, top-3 Jaccard overlap and Kendall tau between two rankings (ids, best first)."""
    common = [x for x in base if x in new]
    tau = kendalltau([base.index(x) for x in common], [new.index(x) for x in common]).statistic if len(common) > 1 else 1.0
    b3, n3 = set(base[:3]), set(new[:3])
    return dict(top1_changed=base[0] != new[0], new_top1=new[0], top3_jaccard=len(b3 & n3) / len(b3 | n3),
                kendall_tau=float(tau), same_set=set(base) == set(new))


def one_at_a_time(ctx: Context, delta: float = PERTURBATION) -> pd.DataFrame:
    base_tab = rank(ctx)
    base = list(base_tab["id"])
    base_score = dict(zip(base_tab["id"], base_tab["nota"]))
    rows = []
    for p in parameters():
        for sign in (-1, +1):
            f = 1 + sign * delta
            if p.patch:
                with catalog_overrides(p.patch(f)):
                    tab = rank(ctx)
            else:
                tab = rank(ctx, adjustments=p.adjust(f))
            new = list(tab["id"])
            score_shift = max(abs(s - base_score[i]) for i, s in zip(tab["id"], tab["nota"]) if i in base_score)
            rows.append(dict(scenario=ctx.scenario.key, param=p.key, group=p.group, label=p.label, base_value=p.base,
                             factor=f, max_score_shift=score_shift, **compare(base, new)))
    return pd.DataFrame(rows)


def weight_extremes(ctx: Context) -> pd.DataFrame:
    """Each weight set to 0 and to 10, the others at the default."""
    base = list(rank(ctx)["id"])
    rows = []
    for k in E.DEFAULT_WEIGHTS:
        for v in (0, 10):
            w = dict(E.DEFAULT_WEIGHTS, **{k: v})
            rows.append(dict(scenario=ctx.scenario.key, weight=k, value=v, **compare(base, list(rank(ctx, weights=w)["id"]))))
    return pd.DataFrame(rows)


def weight_monte_carlo(ctx: Context, n: int = 1000, seed: int = 42) -> pd.DataFrame:
    """Random weights (uniform 0–10 each): how often each rotation is top-1 and in the top-3."""
    rng = np.random.default_rng(seed)
    top1: dict[str, int] = {}
    top3: dict[str, int] = {}
    for _ in range(n):
        w = {k: float(v) for k, v in zip(E.DEFAULT_WEIGHTS, rng.uniform(0, 10, len(E.DEFAULT_WEIGHTS)))}
        ids = list(rank(ctx, weights=w)["id"])
        top1[ids[0]] = top1.get(ids[0], 0) + 1
        for i in ids[:3]:
            top3[i] = top3.get(i, 0) + 1
    ids = sorted(set(top1) | set(top3), key=lambda i: (-top1.get(i, 0), -top3.get(i, 0)))
    return pd.DataFrame([dict(scenario=ctx.scenario.key, id=i, top1_share=top1.get(i, 0) / n, top3_share=top3.get(i, 0) / n)
                         for i in ids])
