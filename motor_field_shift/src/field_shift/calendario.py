"""Rotation calendar: summer-crop stage -> estimated harvest -> second-window sowing date.

Pure module (no data or geopandas), used by the engine (`servico`, `engine`) and by the API validation.
dd/mm dates are ordered within the season: July to December come before January to June (`chave`).
"""
from __future__ import annotations

import re
from datetime import date, timedelta

SEMEADURAS = ["15/01", "01/02", "15/02", "01/03", "15/03"]  # second-window sowing dates the engine evaluates
SEMEADURA_PADRAO = "01/02"
DIAS_PREPARO_2A = 0  # minimum days between the summer harvest and the second-crop sowing (no-till; assumption)

FONTE_ESTAGIOS = "estimate (Fehr & Caviness / Ritchie scale), to be validated with Embrapa"

# Typical days from the stage to harvest: middle of the range, medium cycle, Western Paraná (sowing Sep–Oct).
# estimate (Fehr & Caviness / Ritchie scale), to be validated with Embrapa.
ESTAGIOS: dict[str, dict[str, dict]] = {
    "soja": {
        "vegetativo": dict(nome="Vegetative (before flowering)", dias=90),
        "floracao": dict(nome="Flowering (R1–R2)", dias=65),
        "formacao_vagens": dict(nome="Pod formation (R3–R4)", dias=48),
        "enchimento_graos": dict(nome="Grain fill (R5–R6)", dias=32),
        "maturacao": dict(nome="Maturity (R7–R8)", dias=10),
        "colhida": dict(nome="Already harvested", dias=0),
    },
    "milho_verao": {
        "vegetativo": dict(nome="Vegetative (before tasseling)", dias=110),
        "pendoamento": dict(nome="Tasseling and silking (VT–R1)", dias=80),
        "grao_leitoso": dict(nome="Milk stage (R2–R3)", dias=60),
        "grao_farinaceo": dict(nome="Dough to dent (R4–R5)", dias=40),
        "maturacao": dict(nome="Physiological maturity (R6)", dias=15),
        "colhida": dict(nome="Already harvested", dias=0),
    },
}
TODOS_ESTAGIOS = tuple(dict.fromkeys(e for v in ESTAGIOS.values() for e in v))


def chave(ddmm: str) -> tuple[int, int, int]:
    """Order within the season: Jul–Dec before Jan–Jun."""
    d, m = map(int, ddmm.split("/"))
    return (0 if m >= 7 else 1, m, d)


def fmt(d: date) -> str:
    return f"{d.day:02d}/{d.month:02d}"


def liberada_em(colheita: date) -> str:
    """dd/mm from which the second crop can be sown (harvest + preparation days)."""
    return fmt(colheita + timedelta(days=DIAS_PREPARO_2A))


def somar_dias(ddmm: str, n: int) -> str:
    d, m = map(int, ddmm.split("/"))
    return fmt(date(2001 if m >= 7 else 2002, m, d) + timedelta(days=n))


def verao_de(rotacao_atual: str) -> str:
    """Summer crop of an id '<verao>__<segunda>' (an old slug, without '__', is soybean in summer)."""
    return rotacao_atual.split("__", 1)[0] if "__" in rotacao_atual else "soja"


def semeadura_derivada(colheita: date) -> str | None:
    """First SEMEADURAS date >= harvest + preparation; None if the harvest falls after the last one (too late)."""
    k = chave(liberada_em(colheita))
    return next((s for s in SEMEADURAS if chave(s) >= k), None)


def _data_ddmm(ddmm: str, ref: date) -> date:
    if not isinstance(ddmm, str) or not re.fullmatch(r"\d{2}/\d{2}", ddmm):
        raise ValueError(f"colheita_prevista must be dd/mm (received: {ddmm!r}).")
    d, m = map(int, ddmm.split("/"))
    for ano in (ref.year, ref.year + 1, ref.year + 2):  # next occurrence on/after the reference date
        try:
            x = date(ano, m, d)
        except ValueError:
            continue
        if x >= ref:
            return x
    raise ValueError(f"Invalid colheita_prevista: {ddmm!r}.")


def resolver(verao: str, estagio: str | None, colheita_prevista: str | None, data_referencia: date | None,
             semeadura: str | None = None) -> dict | None:
    """Estimated harvest of the farmer's summer crop. `colheita_prevista` overrides `estagio`. Returns
    {origem: 'informada'|'estagio', colheita: dd/mm, data: date, dias_ate_colheita: int, semeadura_2a: dd/mm|None,
    tarde_demais: bool} or None (no stage and no harvest: catalog assumption). If `semeadura` is given, it overrides the derived one.
    Raises ValueError (user-facing message): stage incompatible with the summer crop or sowing date earlier than the harvest."""
    ref = data_referencia or date.today()
    if estagio is not None and estagio not in ESTAGIOS[verao]:
        outro = [v for v, e in ESTAGIOS.items() if estagio in e and v != verao]
        if outro:
            raise ValueError(f"estagio_verao {estagio!r} belongs to {outro[0].replace('_', ' ')}, but the summer crop of the "
                             f"current rotation is {verao.replace('_', ' ')}. Options: {list(ESTAGIOS[verao])}.")
        raise ValueError(f"Unknown estagio_verao: {estagio!r}. Options for {verao.replace('_', ' ')}: {list(ESTAGIOS[verao])}.")
    if colheita_prevista is not None:
        data, origem = _data_ddmm(colheita_prevista, ref), "informada"
    elif estagio is not None:
        data, origem = ref + timedelta(days=ESTAGIOS[verao][estagio]["dias"]), "estagio"
    else:
        return None
    derivada = semeadura_derivada(data)
    if semeadura is not None and chave(semeadura) < chave(liberada_em(data)):
        raise ValueError(f"semeadura_safrinha {semeadura} is earlier than the estimated summer harvest ({fmt(data)}"
                         f"{', origin: ' + origem}); the second crop can only be sown after the harvest.")
    return dict(origem=origem, colheita=fmt(data), data=data, dias_ate_colheita=(data - ref).days,
                semeadura_2a=semeadura or derivada, tarde_demais=semeadura is None and derivada is None)
