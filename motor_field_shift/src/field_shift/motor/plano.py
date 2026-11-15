"""Multi-year rotation plan (2-3 seasons after the current summer crop).

`plano_plurianual(area, ...)` reuses the single-season engine (`servico._contexto`, `E.pontuar`): every season of a plan is one
catalog rotation (summer crop + 2nd-window crop) scored by the engine, plus explicit, declarative transition terms (summer soybean
on summer soybean, same 2nd-window crop twice in a row, family diversification, recycling cover crop). The sequence score is the
sum of the per-season scores plus those terms; the search is exhaustive (a few dozen rotations ^ 3 seasons).

Season 0 is the farmer's current rotation (`rotacao_atual`), used only for the transition into season 1.
Season 1 chronology: rotations with the SAME summer crop as the current one use the chronology derived by `recomendar` (harvest of
the current crop -> 2nd-window sowing date); rotations with ANOTHER summer crop (and every rotation of seasons 2..N) use typical
dates: 2nd window sown at `SEMEADURA_PADRAO` or right after the catalog harvest of that summer crop, whichever is later. This
resolves, for the plan only, the open decision about the sowing date of the `proxima_safra` block (which stays unchanged).
"""
from __future__ import annotations

import itertools

import numpy as np

from field_shift import calendario as cal
from field_shift.app import engine as E
from field_shift.app import estado_area as EA
from field_shift.motor import servico as S

# --------------------------------------------------------------------------- transition terms (catalog estimates)
# All values are in the engine's score units (each season score is 0-1) and are ESTIMATES, to be validated with an agronomist/Embrapa.
FONTE_TERMOS = S._FONTE_SOLO
PEN_SOJA_CONSECUTIVA = 0.30  # summer soybean in consecutive seasons (summer-crop rotation: disease/nematode cycle, yield drag)
PEN_SEGUNDA_REPETIDA = {  # same 2nd-window crop in consecutive seasons
    "milho": (0.10, "milho sobre milho na 2ª janela: hospedeiro contínuo da cigarrinha-do-milho e de doenças foliares"),
    "feijao": (0.15, "feijão sobre feijão: mofo-branco e doenças de solo se acumulam"),
    "trigo": (0.08, "trigo sobre trigo: doenças de palha e raiz (mal-do-pé, giberela) se acumulam"),
    "sorgo": (0.05, "sorgo sobre sorgo: pressão de doenças e pragas de colmo se acumula"),
}
PEN_MILHO_VERAO_CONSECUTIVO = 0.10  # summer corn in consecutive seasons (same logic as corn on corn)
BONUS_FAMILIA = 0.04  # per distinct botanical family beyond the first within the plan horizon
BONUS_COBERTURA = 0.05  # at least one active recycling cover crop (or corn + brachiaria) within the horizon

_FAMILIA_VERAO = {"soja": {"leguminosa"}, "milho_verao": {"gramínea"}}
_FAMILIA_SEGUNDA = {
    "milho_safrinha": {"gramínea"}, "milho_braquiaria": {"gramínea"}, "trigo": {"gramínea"}, "aveia": {"gramínea"},
    "milheto_crotalaria": {"gramínea", "leguminosa"}, "pousio": set(), "soja_safrinha": {"leguminosa"}, "sorgo": {"gramínea"},
    "feijao_safrinha": {"leguminosa"}, "nabo_forrageiro": {"brássica"}, "aveia_nabo": {"gramínea", "brássica"},
}
_GRUPO_SEGUNDA = {"milho_safrinha": "milho", "milho_braquiaria": "milho", "trigo": "trigo", "sorgo": "sorgo", "feijao_safrinha": "feijao"}
_COBERTURA_ATIVA = {"aveia", "milheto_crotalaria", "nabo_forrageiro", "aveia_nabo", "milho_braquiaria"}


def _fmt_ef(x: float) -> str:
    return f"{x:+.2f}".replace(".", ",").replace("-", "−")


def _transicao(prev: str, nome: str) -> tuple[float, list[str]]:
    """Effect (score units, negative = penalty) and reasons of going from rotation `prev` to `nome` (catalog names)."""
    a, b = E.CATALOGO[prev], E.CATALOGO[nome]
    ef, motivos = 0.0, []
    if a["verao"] == "soja" and b["verao"] == "soja":
        ef -= PEN_SOJA_CONSECUTIVA
        motivos.append(f"soja de verão em safras consecutivas (sem rotação de verão): {_fmt_ef(-PEN_SOJA_CONSECUTIVA)}")
    if a["verao"] == "milho_verao" and b["verao"] == "milho_verao":
        ef -= PEN_MILHO_VERAO_CONSECUTIVO
        motivos.append(f"milho verão em safras consecutivas: {_fmt_ef(-PEN_MILHO_VERAO_CONSECUTIVO)}")
    ga, gb = _GRUPO_SEGUNDA.get(a["segunda"]), _GRUPO_SEGUNDA.get(b["segunda"])
    if ga is not None and ga == gb:
        pen, txt = PEN_SEGUNDA_REPETIDA[ga]
        ef -= pen
        motivos.append(f"{txt}: {_fmt_ef(-pen)}")
    return ef, motivos


def _termos_plano(seq: list[str]) -> tuple[float, list[dict]]:
    """Plan-level terms: family diversification and recycling cover crop within seasons 1..N."""
    fam = set()
    for n in seq:
        c = E.CATALOGO[n]
        fam |= _FAMILIA_VERAO[c["verao"]] | _FAMILIA_SEGUNDA[c["segunda"]]
    termos = []
    if len(fam) > 1:
        ef = BONUS_FAMILIA * (len(fam) - 1)
        termos.append(dict(termo="diversificacao", efeito=ef, motivo=f"{len(fam)} famílias no horizonte ({', '.join(sorted(fam))}): {_fmt_ef(ef)}"))
    if any(E.CATALOGO[n]["segunda"] in _COBERTURA_ATIVA for n in seq):
        termos.append(dict(termo="cobertura", efeito=BONUS_COBERTURA,
                           motivo=f"pelo menos uma cobertura ativa recicladora (palhada, ciclagem de nutrientes) no horizonte: {_fmt_ef(BONUS_COBERTURA)}"))
    return sum(t["efeito"] for t in termos), termos


# --------------------------------------------------------------------------- per-season evaluation
def _sem_tipica(nome: str) -> str:
    """Typical 2nd-window sowing: SEMEADURA_PADRAO or the first date after the catalog harvest of the summer crop, whichever is later."""
    c = E.CATALOGO[nome]
    k = cal.chave(cal.somar_dias(c["colheita_verao"], cal.DIAS_PREPARO_2A))
    depois = next((s for s in cal.SEMEADURAS if cal.chave(s) >= k), cal.SEMEADURAS[-1])
    return max(cal.SEMEADURA_PADRAO, depois, key=cal.chave)


def _rk_com_semeadura(rk: dict, sem: str) -> dict:
    """Climate/water context of `rk` re-targeted to another 2nd-window sowing date (no producer harvest date: catalog harvest)."""
    r = dict(rk)
    r.pop("colheita_produtor", None)
    r["semeadura"] = sem
    r["geada_safrinha"] = next(t["prob"] for t in rk["geada_tabela"] if t["semeadura"] == sem)
    if rk.get("agua_ctx"):
        r["agua_ctx"] = dict(rk["agua_ctx"], semeadura=sem)
    return r


def _avaliar(pesos: dict, rk: dict, aj: dict, nomes: list[str], origem: str) -> tuple[dict, dict]:
    """Runs the engine on `nomes` with `rk`; returns ({name: evaluation}, {name: elimination reasons})."""
    if not nomes:
        return {}, {}
    try:
        res = E.pontuar(pesos, rk, aj, nomes)
    except E.SemCandidatas as e:
        return {}, dict(e.eliminadas)
    w_renda = res["pesos_norm"]["renda"]
    out = {}
    for _, linha in res["tabela"].iterrows():
        n, m = linha["candidata"], res["margens"][linha["candidata"]]
        renda = float(linha["renda"])
        renda_sem = float(np.clip(0.5 + (m["incremental"] - m["bonus"]) / (2 * m["escala_S"]), 0.0, 1.0))
        out[n] = dict(nome=n, nota=float(linha["nota"]), criterios={k: float(linha[k]) for k in E.CRITERIOS},
                      contrib={k: float(v) for k, v in linha["contrib"].items()}, margem=float(m["total"]), bonus=float(m["bonus"]),
                      bonus_sc=float(m["bonus_sc"]), preco_soja=float(m["preco_soja"]),
                      nota_sem_bonus=float(linha["nota"]) + w_renda * (renda_sem - renda), margem_sem_bonus=float(m["total"] - m["bonus"]),
                      sem=rk["semeadura"], origem_cron=origem)
    return out, dict(res["eliminadas"])


def _porque(ev: dict, prev: str, nxt: str | None, efeito_trans: float) -> str:
    c = E.CATALOGO[ev["nome"]]
    top = sorted(ev["contrib"].items(), key=lambda kv: -kv[1])[:2]
    txt = (f"{c['nome_verao']} no verão e {c['nome_segunda']} na 2ª janela (semeadura em {ev['sem']}). "
           f"Maiores contribuições para a nota: " + " e ".join(E.CRITERIOS[k] for k, _ in top).lower() + ".")
    pv = E.CATALOGO[prev]["verao"]
    if pv != c["verao"]:
        txt += f" Alterna o verão ({E.VERAO[pv]['nome'].lower()} → {c['nome_verao'].lower()}), o que quebra o ciclo de pragas e doenças."
    elif c["verao"] == "soja":
        txt += " Soja de novo no verão: sem rotação de verão, com penalidade no plano."
    if c["segunda"] in _COBERTURA_ATIVA and E.SEGUNDA[c["segunda"]]["tipo"] != "grão":
        txt += " Cobertura recicladora: palhada e ciclagem de nutrientes."
    if ev["bonus_sc"] > 0:
        if nxt is None or E.CATALOGO[nxt]["verao"] == "soja":
            txt += f" Deixa palhada/N para a soja seguinte (~{ev['bonus_sc']:g} sc/ha, estimativa de catálogo)."
        else:
            txt += " O bônus da soja seguinte não conta: o verão seguinte é milho."
    return txt


def _ajuste(ev: dict, proxima_soja: bool) -> tuple[float, float]:
    """(score, margin) of a season; the next-soybean bonus only counts when the next summer crop is soybean."""
    return (ev["nota"], ev["margem"]) if proxima_soja else (ev["nota_sem_bonus"], ev["margem_sem_bonus"])


def _pontuar_sequencia(seq: list[str], atual: str, evs: list[dict]) -> dict:
    """Score of a sequence of catalog names (seasons 1..N). `evs[t]` = evaluations of season t+1."""
    n = len(seq)
    notas, margens, trans = [], [], []
    for t, nome in enumerate(seq):
        prox_soja = t == n - 1 or E.CATALOGO[seq[t + 1]]["verao"] == "soja"  # beyond the horizon assume soybean (bonus kept)
        nt, mt = _ajuste(evs[t][nome], prox_soja)
        notas.append(nt)
        margens.append(mt)
        prev = atual if t == 0 else seq[t - 1]
        trans.append(_transicao(prev, nome))
    ef_plano, termos = _termos_plano(seq)
    total = sum(notas) + sum(e for e, _ in trans) + ef_plano
    return dict(seq=list(seq), total=total, notas=notas, margens=margens, transicoes=trans, termos=termos,
                margem_total=sum(margens), prox_soja=[t == n - 1 or E.CATALOGO[seq[t + 1]]["verao"] == "soja" for t in range(n)])


def _arred(x: float, casas: int = 3) -> float:
    return round(float(x), casas)


def _montar_plano(pos: int, sc: dict, atual: str, evs: list[dict]) -> dict:
    seq = sc["seq"]
    safras, transicoes = [], []
    for t, nome in enumerate(seq):
        ev = evs[t][nome]
        prev = atual if t == 0 else seq[t - 1]
        nxt = seq[t + 1] if t + 1 < len(seq) else None
        origem = ("cronologia derivada de `recomendar` (colheita do verão atual)" if ev["origem_cron"] == "recomendar"
                  else "data típica (catálogo)")
        safras.append(dict(
            ano_safra=t + 1, **S._verao_segunda(nome), rotacao=E.ID_DE[nome], nome=nome, nota=_arred(sc["notas"][t]),
            margem_r_ha=float(round(sc["margens"][t])), semeadura_2a=dict(data=ev["sem"], origem=origem),
            criterios={k: _arred(v) for k, v in ev["criterios"].items()},
            bonus_soja_seguinte_contado=bool(ev["bonus_sc"] > 0 and sc["prox_soja"][t]),
            porque=_porque(ev, prev, nxt, sc["transicoes"][t][0])))
        ef, mot = sc["transicoes"][t]
        transicoes.append(dict(de=E.ID_DE[prev], para=E.ID_DE[nome], de_safra=t, para_safra=t + 1, efeito=_arred(ef),
                               motivo="; ".join(mot) if mot else "sem penalidade de transição", fonte=FONTE_TERMOS))
    nomes = " → ".join(f"{E.CATALOGO[n]['nome_verao'].lower()} + {E.CATALOGO[n]['nome_segunda']}" for n in seq)
    return dict(
        posicao=pos, nota=_arred(sc["total"] / len(seq)), nota_total=_arred(sc["total"]),
        margem_total_r_ha=dict(valor=float(round(sc["margem_total"])), origem=S._FONTE_RENDA + "; o bônus da soja seguinte só conta quando "
                               "o verão seguinte é soja (depois do horizonte supõe-se soja)"),
        safras=safras, transicoes=transicoes,
        termos_plano=[dict(termo=x["termo"], efeito=_arred(x["efeito"]), motivo=x["motivo"], fonte=FONTE_TERMOS) for x in sc["termos"]],
        resumo=f"{nomes}. Margem somada de R$ {sc['margem_total']:,.0f}/ha em {len(seq)} safras".replace(",", ".")
               + f" (nota média {sc['total'] / len(seq):.2f}, com termos de transição estimados a validar).",
        fonte=FONTE_TERMOS + "; margens: " + S._FONTE_RENDA)


def _ganho_vs_repetir(plano_sc: dict, atual: str, evs: list[dict], elim: list[dict], n: int) -> dict:
    """Plan versus repeating the current rotation every season (same scoring)."""
    id_atual = E.ID_DE[atual]
    faltam = [t for t in range(n) if atual not in evs[t]]
    if faltam:
        motivos = list(dict.fromkeys(m for t in faltam for m in elim[t].get(atual, [])))
        return dict(comparado_com=id_atual, repetir_atual=dict(eliminada=True, motivos=motivos),
                    aviso=f"Repetir a rotação atual ({atual}) é eliminada em ao menos uma safra do horizonte: " + " ".join(motivos))
    rep = _pontuar_sequencia([atual] * n, atual, evs)
    crit = {k: _arred(np.mean([evs_p[k] for evs_p in plano_sc["_crit"]]) - np.mean([evs[t][atual]["criterios"][k] for t in range(n)]))
            for k in E.CRITERIOS}
    pens = list(dict.fromkeys(m for _, ms in rep["transicoes"] for m in ms))
    out = dict(
        comparado_com=id_atual,
        repetir_atual=dict(eliminada=False, nota=_arred(rep["total"] / n), margem_total_r_ha=float(round(rep["margem_total"])),
                           penalidades=pens),
        nota=_arred((plano_sc["total"] - rep["total"]) / n),
        margem_total=dict(r_ha=float(round(plano_sc["margem_total"] - rep["margem_total"])), origem=S._FONTE_RENDA),
        criterios=crit, criterios_origem="diferença da média dos critérios por safra (plano menos repetir a atual)")
    if pens:
        out["aviso"] = ("Repetir a rotação atual todos os anos é penalizado no plano: " + "; ".join(pens) + f" ({FONTE_TERMOS}).")
    return out


def plano_plurianual(area: dict, anos: int = 3, n_planos: int = 3, semeadura_safrinha: str | None = None, pesos: dict | None = None,
                     rotacao_atual: str | None = None, ajustes: dict | None = None, analise_solo: dict | None = None,
                     restricoes: dict | None = None, irrigacao: dict | None = None, rotacoes: list[dict] | None = None,
                     estagio_verao: str | None = None, colheita_prevista: str | None = None, data_referencia=None,
                     problemas_area: list[str] | None = None) -> dict:
    """Multi-year rotation plan: the best `n_planos` sequences of `anos` seasons (2-3) after the current summer crop.

    Same inputs as `servico.recomendar` (rotacao_atual required; `rotacoes`, if given, limits the rotations a plan may use) plus
    `anos` and `n_planos` (1-5). Returns `planos` (ranked), `entrada`, `cronologia` and `metodologia`; see the module docstring
    for the model. Raises the same exceptions as `recomendar` (EntradaInvalida, ForaDaRegiao, ErroConsultaExterna)."""
    inp = S._normalizar_entradas(semeadura_safrinha, pesos, rotacao_atual, ajustes, analise_solo, restricoes, irrigacao, rotacoes,
                                 problemas_area)
    if isinstance(anos, bool) or not isinstance(anos, int) or anos not in (2, 3):
        raise S.EntradaInvalida("anos deve ser 2 ou 3.")
    if isinstance(n_planos, bool) or not isinstance(n_planos, int) or not 1 <= n_planos <= 5:
        raise S.EntradaInvalida("n_planos deve ser um inteiro entre 1 e 5.")
    base = S._cronologia_e_contexto(area, inp, semeadura_safrinha, estagio_verao, colheita_prevista, data_referencia)
    rk, pesos_n, aj_n, sel = base["rk"], inp["pesos_n"], inp["aj_n"], inp["sel"]
    atual, verao_atual = inp["nome_atual"], inp["verao_atual"]
    permitidas = list(E.CATALOGO) if sel is None else [S.ROTACOES[i] for i in sel]
    avaliar = list(dict.fromkeys(permitidas + [atual]))  # the current rotation is always evaluated (repeat comparison)

    # season 1, same summer crop as the current one: chronology derived by `recomendar`
    ev1, el1 = _avaliar(pesos_n, rk, aj_n, [n for n in avaliar if E.CATALOGO[n]["verao"] == verao_atual], "recomendar")
    # typical dates (other summer crop in season 1, and all rotations of seasons 2..N), grouped by sowing date
    grupos: dict[str, list[str]] = {}
    for n in avaliar:
        grupos.setdefault(_sem_tipica(n), []).append(n)
    ev_t, el_t = {}, {}
    for sem, nomes in grupos.items():
        e, el = _avaliar(pesos_n, _rk_com_semeadura(rk, sem), aj_n, nomes, "tipica")
        ev_t.update(e)
        el_t.update(el)
    evs = [{**ev1, **{n: v for n, v in ev_t.items() if E.CATALOGO[n]["verao"] != verao_atual}}] + [ev_t] * (anos - 1)
    elims = [{**el1, **{n: v for n, v in el_t.items() if E.CATALOGO[n]["verao"] != verao_atual}}] + [el_t] * (anos - 1)
    cands = [[n for n in permitidas if n in e] for e in evs]
    for t, c in enumerate(cands):
        if not c:
            motivos = list(dict.fromkeys(m for ms in elims[t].values() for m in ms))
            raise S.EntradaInvalida(f"Nenhuma rotação viável na safra {t + 1} do plano (regras duras ou restrições): " + " ".join(motivos))

    pontuados = [_pontuar_sequencia(list(s), atual, evs) for s in itertools.product(*cands)]
    pontuados.sort(key=lambda p: -p["total"])
    melhores = pontuados[:n_planos]
    for p in melhores:
        p["_crit"] = [evs[t][nome]["criterios"] for t, nome in enumerate(p["seq"])]
    planos = []
    for pos, p in enumerate(melhores, start=1):
        plano = _montar_plano(pos, p, atual, evs)
        plano["ganho_vs_repetir_atual"] = _ganho_vs_repetir(p, atual, evs, elims, anos)
        planos.append(plano)

    avisos = list(base["avisos"])
    ganho = planos[0]["ganho_vs_repetir_atual"]
    if ganho.get("aviso"):
        avisos.append(ganho["aviso"])
    mt = ganho.get("margem_total")
    if mt and mt["r_ha"] < 0:
        avisos.append(f"O plano de maior pontuação soma R$ {-mt['r_ha']:,.0f}/ha a menos de margem do que repetir a rotação atual: a "
                      "diferença vem das penalidades de transição e dos critérios não monetários (estimativas a validar). O custo do "
                      "milho verão usa a referência CONAB de Ponta Grossa (item pendente em docs/pendencias.md) e pesa nessa margem."
                      .replace(",", "."))
    if len(pontuados) < n_planos:
        avisos.append(f"Só {len(pontuados)} plano(s) viável(is) com as restrições e rotações informadas.")
    if atual not in permitidas:
        avisos.append(f"A rotação atual ({atual}) não está em 'rotacoes': não entra nos planos, só no comparativo com repeti-la.")
    entrada = dict(anos=anos, n_planos=n_planos, rotacao_atual=inp["rotacao_atual"], estagio_verao=estagio_verao,
                   colheita_prevista=colheita_prevista, data_referencia=base["data_ref"].isoformat(), pesos=pesos_n,
                   semeadura_safrinha=base["sem_2a"], ajustes=ajustes or {})
    if sel is not None:
        entrada["rotacoes"] = [dict(verao=E.CATALOGO[S.ROTACOES[i]]["verao"], segunda=E.CATALOGO[S.ROTACOES[i]]["segunda"]) for i in sel]
    if inp["probs_n"]:
        entrada["problemas_area"] = inp["probs_n"]
    if inp["solo_n"]:
        entrada["analise_solo"] = {k: v for k, v in inp["solo_n"].items() if v is not None}
    if inp["restr_n"]:
        entrada["restricoes"] = inp["restr_n"]["eco"]
    if inp["irr_n"]:
        entrada["irrigacao"] = inp["irr_n"]
    out = dict(
        entrada=entrada,
        cultura_atual=dict(id=verao_atual, nome=E.VERAO[verao_atual]["nome"]),
        colheita_estimada=base["colheita"],
        cronologia=dict(
            safra_1_mesmo_verao=dict(semeadura_2a=base["sem_2a"], origem=base["sem_origem"]),
            safras_tipicas={n: _sem_tipica(n) for n in avaliar},
            descricao="Safra 1 com o mesmo verão da atual usa a semeadura derivada da colheita (como `recomendar`); as demais usam datas "
                      "típicas: 2ª janela em 01/02 ou logo após a colheita do verão do catálogo (milho verão: 15/02)."),
        planos=planos, avisos=avisos,
        metodologia=dict(
            formula="Pontuação do plano = Σ nota por safra (critérios do motor) + Σ termos de transição + termos do plano; "
                    "nota do plano = pontuação / nº de safras",
            premissas=[
                "Cada safra é uma rotação do catálogo (verão + 2ª janela) não eliminada pelas regras duras e restrições; a rotação atual é a safra 0.",
                "Busca exaustiva sobre as rotações viáveis; devolve os planos distintos de maior pontuação.",
                "O bônus da soja seguinte (palhada/N) só conta quando o verão da safra seguinte é soja; depois do horizonte supõe-se soja.",
                "Não há preços, produtividades ou clima por ano: cada safra usa a média do município (PAM/SEAB/NASA POWER), como no ranking.",
            ],
            termos_transicao=dict(
                soja_verao_consecutiva=-PEN_SOJA_CONSECUTIVA, milho_verao_consecutivo=-PEN_MILHO_VERAO_CONSECUTIVO,
                segunda_janela_repetida={k: -v[0] for k, v in PEN_SEGUNDA_REPETIDA.items()},
                bonus_por_familia_alem_da_primeira=BONUS_FAMILIA, bonus_cobertura_recicladora=BONUS_COBERTURA,
                fonte=FONTE_TERMOS),
            criterios=S._CRIT_METODO, versao=S.VERSAO))
    aplicados = S._ajustes_aplicados(aj_n, inp["solo_fis"], inp["restr_n"], inp["irr_n"]) + EA.ajustes_aplicados(
        rk.get("estado_area"), inp["solo_n"] is not None)
    if aplicados:
        out["metodologia"]["ajustes_aplicados"] = aplicados
    return S._limpo(out)
