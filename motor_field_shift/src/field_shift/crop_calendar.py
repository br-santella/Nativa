"""Calendário da rotação: estágio da cultura de verão -> colheita estimada -> semeadura da 2ª janela.

Módulo puro (sem dados nem geopandas), usado pelo motor (`servico`, `engine`) e pela validação da API.
Datas dd/mm são ordenadas dentro da safra: de julho a dezembro vêm antes de janeiro a junho (`chave`).
"""
from __future__ import annotations

import re
from datetime import date, timedelta

SOWINGS_2ND = ["15/01", "01/02", "15/02", "01/03", "15/03"]  # datas de semeadura da 2ª janela que o motor avalia
DEFAULT_SOWING = "01/02"
PREP_DAYS_2ND = 0  # dias mínimos entre a colheita do verão e a semeadura da 2ª cultura (plantio direto; premissa)

STAGES_SOURCE = "estimativa (escala Fehr & Caviness / Ritchie), validar com Embrapa"

# Dias típicos do estágio até a colheita: meio da faixa, ciclo médio, Oeste do PR (semeadura set–out).
# estimativa (escala Fehr & Caviness / Ritchie), validar com Embrapa.
STAGES: dict[str, dict[str, dict]] = {
    "soja": {
        "vegetativo": dict(nome="Vegetativo (antes do florescimento)", dias=90),
        "floracao": dict(nome="Floração (R1–R2)", dias=65),
        "formacao_vagens": dict(nome="Formação de vagens (R3–R4)", dias=48),
        "enchimento_graos": dict(nome="Enchimento de grãos (R5–R6)", dias=32),
        "maturacao": dict(nome="Maturação (R7–R8)", dias=10),
        "colhida": dict(nome="Já colhida", dias=0),
    },
    "milho_verao": {
        "vegetativo": dict(nome="Vegetativo (antes do pendoamento)", dias=110),
        "pendoamento": dict(nome="Pendoamento e espigamento (VT–R1)", dias=80),
        "grao_leitoso": dict(nome="Grão leitoso (R2–R3)", dias=60),
        "grao_farinaceo": dict(nome="Grão pastoso a farináceo (R4–R5)", dias=40),
        "maturacao": dict(nome="Maturação fisiológica (R6)", dias=15),
        "colhida": dict(nome="Já colhido", dias=0),
    },
}
ALL_STAGES = tuple(dict.fromkeys(e for v in STAGES.values() for e in v))


def key(ddmm: str) -> tuple[int, int, int]:
    """Ordem dentro da safra: jul–dez antes de jan–jun."""
    d, m = map(int, ddmm.split("/"))
    return (0 if m >= 7 else 1, m, d)


def fmt(d: date) -> str:
    return f"{d.day:02d}/{d.month:02d}"


def released_on(harvest: date) -> str:
    """dd/mm a partir da qual a 2ª cultura pode ser semeada (colheita + dias de preparo)."""
    return fmt(harvest + timedelta(days=PREP_DAYS_2ND))


def add_days(ddmm: str, n: int) -> str:
    d, m = map(int, ddmm.split("/"))
    return fmt(date(2001 if m >= 7 else 2002, m, d) + timedelta(days=n))


def summer_of(current_rotation: str) -> str:
    """Cultura de verão de um id '<verao>__<segunda>' (slug antigo, sem '__', é soja no verão)."""
    return current_rotation.split("__", 1)[0] if "__" in current_rotation else "soja"


def derived_sowing(harvest: date) -> str | None:
    """Primeira data de SEMEADURAS >= colheita + preparo; None se a colheita cai depois da última (tarde demais)."""
    k = key(released_on(harvest))
    return next((s for s in SOWINGS_2ND if key(s) >= k), None)


def _date_ddmm(ddmm: str, ref: date) -> date:
    if not isinstance(ddmm, str) or not re.fullmatch(r"\d{2}/\d{2}", ddmm):
        raise ValueError(f"colheita_prevista deve ser dd/mm (recebido: {ddmm!r}).")
    d, m = map(int, ddmm.split("/"))
    for year in (ref.year, ref.year + 1, ref.year + 2):  # próxima ocorrência em/depois da referência
        try:
            x = date(year, m, d)
        except ValueError:
            continue
        if x >= ref:
            return x
    raise ValueError(f"colheita_prevista inválida: {ddmm!r}.")


def resolver(summer: str, stage: str | None, expected_harvest: str | None, reference_date: date | None,
             sowing: str | None = None) -> dict | None:
    """Colheita estimada do verão do produtor. `colheita_prevista` vence o `estagio`. Devolve
    {origem: 'informada'|'estagio', colheita: dd/mm, data: date, dias_ate_colheita: int, semeadura_2a: dd/mm|None,
    tarde_demais: bool} ou None (sem estágio nem colheita: premissa do catálogo). Se `semeadura` vier, ela vence a derivada.
    Lança ValueError (mensagem para o usuário): estágio incompatível com o verão ou semeadura anterior à colheita."""
    ref = reference_date or date.today()
    if stage is not None and stage not in STAGES[summer]:
        other = [v for v, e in STAGES.items() if stage in e and v != summer]
        if other:
            raise ValueError(f"estagio_verao {stage!r} é de {other[0].replace('_', ' ')}, mas a cultura de verão da "
                             f"rotação atual é {summer.replace('_', ' ')}. Opções: {list(STAGES[summer])}.")
        raise ValueError(f"estagio_verao desconhecido: {stage!r}. Opções para {summer.replace('_', ' ')}: {list(STAGES[summer])}.")
    if expected_harvest is not None:
        data, origin = _date_ddmm(expected_harvest, ref), "informada"
    elif stage is not None:
        data, origin = ref + timedelta(days=STAGES[summer][stage]["dias"]), "estagio"
    else:
        return None
    derived = derived_sowing(data)
    if sowing is not None and key(sowing) < key(released_on(data)):
        raise ValueError(f"semeadura_safrinha {sowing} é anterior à colheita estimada do verão ({fmt(data)}"
                         f"{', origem: ' + origin}); a 2ª cultura só pode ser semeada depois da colheita.")
    return dict(origem=origin, colheita=fmt(data), data=data, dias_ate_colheita=(data - ref).days,
                semeadura_2a=sowing or derived, tarde_demais=sowing is None and derived is None)
