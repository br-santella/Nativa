"""Estado da área informado pelo produtor: problemas da área e fertilidade do solo (ambos OPCIONAIS).

Regra dura: sem a informação do produtor, NADA entra na análise (sem estimativa, sem valor padrão). Com ela, o efeito é
declarativo e auditável nas tabelas abaixo, e usa as escalas que o motor já tem (deltas aditivos nos critérios `pragas` e
`solo`, 0–1, e itens de custo extra na margem). TODOS os números abaixo são ESTIMATIVAS DE CATÁLOGO, a validar com
agrônomo/Embrapa/IDR-PR (mesmo padrão de `_FONTE_SOLO`), salvo onde há fonte citada.

Estado = {"problemas": [slugs], "fert": dict de `preparar_fertilidade` | None}, guardado em rk["estado_area"].
"""
from __future__ import annotations

from pathlib import Path

import yaml

FONTE_ESTIMATIVA = "estimativa de catálogo, validar com agrônomo/Embrapa"

# --------------------------------------------------------------------------- vocabulário (catalog/vocabulario.yaml)
_PROBLEMAS_FALLBACK = ("nematoide", "mofo_branco", "cigarrinha", "compactacao")


def _carregar_problemas() -> tuple[str, ...]:
    p = Path(__file__).resolve().parents[4] / "catalog" / "vocabulario.yaml"
    try:
        return tuple(yaml.safe_load(p.read_text(encoding="utf-8"))["problemas_area"])
    except (OSError, KeyError, TypeError, yaml.YAMLError):
        return _PROBLEMAS_FALLBACK  # catálogo ausente (deploy só do motor); um teste confere que os dois coincidem


PROBLEMAS = _carregar_problemas()

# --------------------------------------------------------------------------- A) problemas da área
# Cada efeito: (alvo, critério, delta, motivo). Alvo: "segunda:<slug>" (cultura da 2ª janela), "verao:<slug>" (cultura de
# verão) ou "milho_sobre_milho". Delta aditivo no critério (escala 0–1, maior = melhor); o resultado é limitado a [0, 1].
# A rotação soma os efeitos do verão e da 2ª janela (a soja de verão pesa igual em todas as rotações do mesmo bloco).
PROBLEMAS_ROTULO = {"nematoide": "nematoide", "mofo_branco": "mofo-branco", "cigarrinha": "cigarrinha-do-milho",
                    "compactacao": "compactação"}
EFEITOS_PROBLEMAS: dict[str, list[tuple[str, str, float, str]]] = {
    "mofo_branco": [  # Sclerotinia sclerotiorum: hospedeiros feijão, soja e crucíferas (nabo; girassol/canola)
        ("segunda:feijao_safrinha", "pragas", -0.25, "feijão é hospedeiro forte do mofo-branco"),
        ("verao:soja", "pragas", -0.15, "soja é hospedeira do mofo-branco"),
        ("segunda:nabo_forrageiro", "pragas", -0.15, "nabo (crucífera) é hospedeiro do mofo-branco"),
        ("segunda:aveia_nabo", "pragas", -0.08, "o nabo do mix é hospedeiro do mofo-branco (metade do efeito do nabo solteiro)"),
    ],
    "nematoide": [  # cultivar/espécie importam (braquiária e milheto variam por nematoide); validar com Embrapa Soja
        ("segunda:milheto_crotalaria", "pragas", +0.25, "crotalária e milheto reduzem a população de nematoides"),
        ("segunda:milho_braquiaria", "pragas", +0.10, "braquiária reduz nematoides (depende da espécie/cultivar)"),
        ("segunda:feijao_safrinha", "pragas", -0.25, "feijão é hospedeiro de nematoides"),
        ("verao:soja", "pragas", -0.15, "soja é hospedeira de nematoides (Pratylenchus, Meloidogyne, Heterodera)"),
    ],
    "cigarrinha": [  # Dalbulus maidis: vetor do enfezamento; o milho sobre milho já perde 0,25 no catálogo
        ("segunda:milho_safrinha", "pragas", -0.05, "milho safrinha é o hospedeiro da cigarrinha"),
        ("segunda:milho_braquiaria", "pragas", -0.05, "milho safrinha é o hospedeiro da cigarrinha"),
        ("verao:milho_verao", "pragas", -0.05, "milho verão é o hospedeiro da cigarrinha"),
        ("milho_sobre_milho", "pragas", -0.15, "milho sobre milho mantém a cigarrinha ativa o ano todo (soma-se à penalidade do catálogo)"),
    ],
    "compactacao": [  # raízes pivotantes/profundas descompactam; efeito no critério solo
        ("segunda:nabo_forrageiro", "solo", +0.15, "raiz pivotante do nabo descompacta"),
        ("segunda:aveia_nabo", "solo", +0.10, "o nabo do mix descompacta (efeito menor que o do nabo solteiro)"),
        ("segunda:milho_braquiaria", "solo", +0.15, "raiz profunda da braquiária descompacta"),
    ],
}


def _efeitos_problemas(c: dict, problemas) -> list[dict]:
    chaves = {f"segunda:{c['segunda']}", f"verao:{c['verao']}"} | ({"milho_sobre_milho"} if c.get("milho_sobre_milho") else set())
    return [dict(problema=p, criterio=crit, delta=d, motivo=m) for p in problemas
            for alvo, crit, d, m in EFEITOS_PROBLEMAS[p] if alvo in chaves]


# --------------------------------------------------------------------------- B) fertilidade
# Campos (todos opcionais; unidades do laudo brasileiro): P Mehlich-1 mg/dm³, K/Ca/Mg/Al/CTC cmolc/dm³, V%.
CAMPOS_FERTILIDADE = {  # campo: (mínimo, máximo) de validação plausível
    "p_mg_dm3": (0, 500), "k_cmolc_dm3": (0, 10), "ca_cmolc_dm3": (0, 40), "mg_cmolc_dm3": (0, 20),
    "al_cmolc_dm3": (0, 15), "v_pct": (0, 100), "ctc_cmolc_dm3": (0, 60),
}

# Faixas de classe (limite superior exclusivo de cada classe, em ordem). Fonte de referência: Manual de Adubação e Calagem para o
# Estado do Paraná (SBCS/NEPAR, 2017) e IDR-PR, SIMPLIFICADAS: K, V% e Al seguem as faixas usuais do PR; as de P no PR variam com
# a argila e aqui usam uma única escala (estimativa, validar com o laudo/agrônomo).
CLASSES = {
    "p": [(3.0, "muito_baixo"), (6.0, "baixo"), (12.0, "medio"), (18.0, "alto"), (float("inf"), "muito_alto")],  # Mehlich-1, mg/dm³
    "k": [(0.15, "baixo"), (0.30, "medio"), (float("inf"), "alto")],  # cmolc/dm³ (faixas do PR)
    "v": [(35.0, "muito_baixa"), (50.0, "baixa"), (70.0, "media"), (float("inf"), "adequada")],  # V%
    "al": [(0.5, "baixo"), (1.0, "medio"), (float("inf"), "alto")],  # cmolc/dm³ (Al > 0,5 já limita culturas sensíveis)
}


def _classe(tabela: str, x: float) -> str:
    return next(nome for lim, nome in CLASSES[tabela] if x < lim)


# Calagem pela saturação por bases: NC (t/ha) = (V2 − V1)/100 × CTC / PRNT, com CTC em cmolc/dm³ (1 cmolc/dm³ = 1 t de CaCO₃/ha em
# 0–20 cm); equivale a (V2−V1)·CTC/10 quando a CTC está em mmolc/dm³ e o PRNT em fração ×10. Fórmula padrão (Manual PR, Embrapa).
PRNT = 0.80  # estimativa de calcário comum, validar
NC_MAX_T_HA = 6.0  # teto de uma aplicação (acima disso parcelar); estimativa, validar
CALCARIO_R_T = 220.0  # R$/t aplicado (produto + frete + aplicação); estimativa, validar
CALAGEM_ANOS = 3  # o custo é diluído na duração típica da calagem em plantio direto; estimativa, validar
# V2 (saturação por bases desejada) por cultura da 2ª janela; None = a cultura não motiva calagem por si (cobertura/pousio).
V2 = {"milho_safrinha": 70.0, "milho_braquiaria": 70.0, "trigo": 70.0, "feijao_safrinha": 70.0, "sorgo": 60.0}
V2_FONTE = "V2 de 70% para milho, trigo e feijão e 60% para sorgo: estimativa de catálogo (Manual de Adubação e Calagem PR), validar"

# Adubação P/K: dose por classe (kg/ha de P2O5 e K2O). A margem já traz a adubação de referência do custo CONAB, que tomamos como a
# da classe "média": o custo extra é (dose da classe − dose média) × exigência × preço, negativo (economia) em solo rico.
DOSE_P2O5 = {"muito_baixo": 90.0, "baixo": 70.0, "medio": 50.0, "alto": 30.0, "muito_alto": 0.0}
DOSE_K2O = {"baixo": 80.0, "medio": 50.0, "alto": 30.0}
PRECO_P2O5_R_KG = 7.5  # superfosfato triplo ≈ R$ 3.450/t a 46% de P2O5; estimativa, validar
PRECO_K2O_R_KG = 4.6  # cloreto de potássio ≈ R$ 2.700/t a 58% de K2O; estimativa, validar
# Exigência de P/K (1 = exigente; coberturas e pousio não recebem adubação no catálogo).
EXIGENCIA_PK = {"milho_safrinha": 1.0, "milho_braquiaria": 1.0, "trigo": 1.0, "feijao_safrinha": 1.0, "sorgo": 0.6}

# Penalidade no critério solo para cultura sensível à acidez: PENALIDADE_ACIDEZ × severidade (0–2) × sensibilidade.
# Severidade = max(Al: médio 1, alto 2; V%: baixa 1, muito baixa 2).
PENALIDADE_ACIDEZ = 0.08
SENSIBILIDADE_ACIDEZ = {"trigo": 1.0, "milho_safrinha": 1.0, "milho_braquiaria": 0.9, "feijao_safrinha": 0.8, "sorgo": 0.4}
# Bônus no critério solo das coberturas recicladoras quando P ou K estão baixos (nabo e braquiária reciclam K/P) e da crotalária
# (fixa N) quando o solo é pobre em P, K ou V%.
BONUS_RECICLAGEM = {"nabo_forrageiro": 0.10, "aveia_nabo": 0.06, "milho_braquiaria": 0.08}
BONUS_CROTALARIA = {"milheto_crotalaria": 0.05}


def preparar_fertilidade(f: dict | None) -> dict | None:
    """Interpreta a fertilidade informada (dict com um subconjunto de CAMPOS_FERTILIDADE, já validado) em classes.
    None se nada foi informado. Nada é estimado: V% só é derivada se vierem Ca, Mg, K e CTC (V = (Ca+Mg+K)/CTC)."""
    f = {k: float(v) for k, v in (f or {}).items() if k in CAMPOS_FERTILIDADE and v is not None}
    if not f:
        return None
    v_origem = "informada" if "v_pct" in f else None
    if v_origem is None and all(k in f for k in ("ca_cmolc_dm3", "mg_cmolc_dm3", "k_cmolc_dm3", "ctc_cmolc_dm3")) and f["ctc_cmolc_dm3"] > 0:
        f["v_pct"] = min(100.0, 100 * (f["ca_cmolc_dm3"] + f["mg_cmolc_dm3"] + f["k_cmolc_dm3"]) / f["ctc_cmolc_dm3"])
        v_origem = "derivada de (Ca+Mg+K)/CTC"
    classes = {}
    if "p_mg_dm3" in f: classes["p"] = _classe("p", f["p_mg_dm3"])
    if "k_cmolc_dm3" in f: classes["k"] = _classe("k", f["k_cmolc_dm3"])
    if "v_pct" in f: classes["v"] = _classe("v", f["v_pct"])
    if "al_cmolc_dm3" in f: classes["al"] = _classe("al", f["al_cmolc_dm3"])
    sev = max([{"baixo": 0, "medio": 1, "alto": 2}[classes["al"]] if "al" in classes else 0,
               {"muito_baixa": 2, "baixa": 1}.get(classes.get("v"), 0)])
    pk_baixo = classes.get("p") in ("muito_baixo", "baixo") or classes.get("k") == "baixo"
    return dict(valores=f, classes=classes, v_origem=v_origem, severidade_acidez=sev, pk_baixo=pk_baixo,
                pobre=pk_baixo or sev > 0, informados=[k for k in CAMPOS_FERTILIDADE if k in f],
                ausentes=[k for k in CAMPOS_FERTILIDADE if k not in f])


def _nc_t_ha(fert: dict, v2: float) -> float | None:
    """Necessidade de calagem (t/ha de calcário com PRNT padrão); None se faltam V% ou CTC (nada é estimado)."""
    v, ctc = fert["valores"].get("v_pct"), fert["valores"].get("ctc_cmolc_dm3")
    if v is None or ctc is None:
        return None
    return min(NC_MAX_T_HA, max(0.0, (v2 - v) / 100.0 * ctc / PRNT))


def custos(c: dict, estado: dict | None) -> list[dict]:
    """Itens de custo extra da fertilidade (calagem e adubação P/K) no formato de `extras_custo`. [] sem fertilidade."""
    fert = (estado or {}).get("fert")
    if not fert:
        return []
    out, seg = [], c["segunda"]
    if seg in V2:
        nc = _nc_t_ha(fert, V2[seg])
        if nc:
            anual = nc * CALCARIO_R_T / CALAGEM_ANOS
            out.append(dict(chave="calagem", rotulo="Calagem", custo=anual,
                            detalhe=f"NC = ({V2[seg]:g} − V% {fert['valores']['v_pct']:.0f})/100 × CTC {fert['valores']['ctc_cmolc_dm3']:g} / PRNT "
                                    f"{PRNT:.0%} = {nc:.1f} t/ha × R$ {CALCARIO_R_T:g}/t, diluída em {CALAGEM_ANOS} anos; {FONTE_ESTIMATIVA}"))
    exig = EXIGENCIA_PK.get(seg, 0.0)
    if exig:
        cl = fert["classes"]
        partes, delta = [], 0.0
        if "p" in cl:
            d = (DOSE_P2O5[cl["p"]] - DOSE_P2O5["medio"]) * exig
            delta += d * PRECO_P2O5_R_KG
            partes.append(f"P {cl['p'].replace('_', ' ')} ({d:+.0f} kg P2O5/ha)")
        if "k" in cl:
            d = (DOSE_K2O[cl["k"]] - DOSE_K2O["medio"]) * exig
            delta += d * PRECO_K2O_R_KG
            partes.append(f"K {cl['k']} ({d:+.0f} kg K2O/ha)")
        if partes:
            out.append(dict(chave="adubacao_pk", rotulo="Adubação P/K acima/abaixo da referência" if delta >= 0 else "Economia de adubação P/K",
                            custo=delta, detalhe=", ".join(partes) + f" em relação à classe média embutida no custo CONAB; {FONTE_ESTIMATIVA}"))
    return out


def ajuste(c: dict, estado: dict | None) -> dict:
    """Deltas aditivos nos critérios da candidata: {"pragas": x, "solo": y, "efeitos": [dict(origem, criterio, delta, motivo)]}.
    Sem estado (nada informado) devolve zeros e nenhum efeito."""
    out = dict(pragas=0.0, solo=0.0, efeitos=[])
    if not estado:
        return out
    for e in _efeitos_problemas(c, estado.get("problemas") or ()):
        out[e["criterio"]] += e["delta"]
        out["efeitos"].append(dict(e, origem=f"problema da área: {PROBLEMAS_ROTULO[e['problema']]}"))
    fert, seg = estado.get("fert"), c["segunda"]
    if fert:
        sens = SENSIBILIDADE_ACIDEZ.get(seg, 0.0)
        if sens and fert["severidade_acidez"]:
            d = -PENALIDADE_ACIDEZ * fert["severidade_acidez"] * sens
            out["solo"] += d
            out["efeitos"].append(dict(origem="fertilidade", criterio="solo", delta=d, problema=None,
                                       motivo=f"cultura sensível à acidez (Al {fert['classes'].get('al', 'n/i')}, V% {fert['classes'].get('v', 'n/i').replace('_', ' ')}); "
                                              f"severidade {fert['severidade_acidez']}"))
        b = BONUS_RECICLAGEM.get(seg, 0.0) if fert["pk_baixo"] else 0.0
        if b:
            out["solo"] += b
            out["efeitos"].append(dict(origem="fertilidade", criterio="solo", delta=b, problema=None,
                                       motivo="recicla K/P em solo com P ou K baixos"))
        b = BONUS_CROTALARIA.get(seg, 0.0) if fert["pobre"] else 0.0
        if b:
            out["solo"] += b
            out["efeitos"].append(dict(origem="fertilidade", criterio="solo", delta=b, problema=None,
                                       motivo="crotalária fixa N e adiciona matéria orgânica em solo pobre"))
    return out


# --------------------------------------------------------------------------- textos (card e metodologia)
def _txt_fert(fert: dict) -> str:
    rot = {"p_mg_dm3": "P", "k_cmolc_dm3": "K", "ca_cmolc_dm3": "Ca", "mg_cmolc_dm3": "Mg", "al_cmolc_dm3": "Al", "v_pct": "V%",
           "ctc_cmolc_dm3": "CTC"}
    v = fert["valores"]
    return ", ".join(f"{rot[k]} {v[k]:g}" for k in fert["informados"]) + (
        f"; V% {v['v_pct']:.0f} {fert['v_origem']}" if fert["v_origem"] and fert["v_origem"] != "informada" else "")


def card(c: dict, estado: dict | None) -> dict:
    """Linhas do card da candidata: `evidencias`, `lacunas` (o que não foi considerado) e `revisar`."""
    est = estado or {}
    probs, fert = est.get("problemas") or [], est.get("fert")
    ev, lac, rev = [], [], []
    aj = ajuste(c, estado)
    if probs:
        lac.append("Problemas da área considerados: " + ", ".join(PROBLEMAS_ROTULO[p] for p in probs)
                   + f" (efeito por cultura: {FONTE_ESTIMATIVA}).")
        efs = [e for e in aj["efeitos"] if e["problema"]]
        for e in efs:
            ev.append(f"Problema da área ({PROBLEMAS_ROTULO[e['problema']]}): critério {e['criterio']} {e['delta']:+.2f} ({e['motivo']}; "
                      f"{FONTE_ESTIMATIVA}).")
        if not efs:
            ev.append("Problemas da área informados (" + ", ".join(PROBLEMAS_ROTULO[p] for p in probs)
                      + "): sem efeito catalogado nesta rotação.")
    else:
        lac.append("Problemas da área (nematoide, mofo-branco, cigarrinha, compactação) não informados: não considerados.")
    if fert:
        ev.append(f"Fertilidade informada pelo produtor ({_txt_fert(fert)}); classes: "
                  + ", ".join(f"{k.upper()} {v.replace('_', ' ')}" for k, v in fert["classes"].items()) + ".")
        for e in (x for x in aj["efeitos"] if x["origem"] == "fertilidade"):
            ev.append(f"Fertilidade: critério {e['criterio']} {e['delta']:+.2f} ({e['motivo']}; {FONTE_ESTIMATIVA}).")
        for it in custos(c, estado):
            ev.append(f"Fertilidade: {it['rotulo']} {'+' if it['custo'] >= 0 else '−'}R$ {abs(it['custo']):.0f}/ha/ano ({it['detalhe']}).")
        if c["segunda"] in V2 and _nc_t_ha(fert, V2[c["segunda"]]) is None:
            lac.append("Calagem não calculada: faltam V% (ou Ca+Mg+K+CTC) e CTC informados; nada foi estimado.")
        if fert["ausentes"]:
            lac.append("Fertilidade parcial: não informados " + ", ".join(fert["ausentes"]) + "; esses itens não entram na análise.")
        lac.append(f"Fertilidade: faixas de classe, doses, preços e V2 são estimativas (Manual de Adubação e Calagem PR/IDR-PR simplificados); "
                   f"{V2_FONTE}. Calagem e adubação da cultura de verão não entram (iguais em todas as rotações do bloco).")
        rev.append("Fertilidade: confirmar doses de calagem e adubação com o agrônomo e o laudo completo.")
    else:
        lac.append("Fertilidade não considerada (não informada): sem custo de adubação/calagem e sem penalidade ou bônus por fertilidade.")
    return dict(evidencias=ev, lacunas=lac, revisar=rev)


def ajustes_aplicados(estado: dict | None, analise_informada: bool) -> list[str]:
    """Frases de `metodologia.ajustes_aplicados` sobre o estado da área. Vazio se o produtor não informou nem problemas, nem análise
    de solo (a resposta fica idêntica à anterior; o card já diz o que não foi considerado)."""
    est = estado or {}
    probs, fert = est.get("problemas") or [], est.get("fert")
    if not (probs or fert or analise_informada):
        return []
    o = []
    if probs:
        o.append("Problemas da área informados pelo produtor (" + ", ".join(PROBLEMAS_ROTULO[p] for p in probs)
                 + ") ajustam os critérios pragas e solo por cultura (tabela EFEITOS_PROBLEMAS; " + FONTE_ESTIMATIVA + ").")
    else:
        o.append("Problemas da área não informados: não considerados.")
    if fert:
        o.append("Fertilidade informada pelo produtor (" + ", ".join(fert["informados"]) + "): custo de calagem (saturação por bases) e de "
                 "adubação P/K por cultura na margem, penalidade no critério solo para cultura sensível em solo ácido/pobre e bônus para "
                 "cobertura recicladora (nabo, braquiária) e crotalária; itens não informados não entram (" + FONTE_ESTIMATIVA + ").")
    else:
        o.append("Fertilidade não considerada (não informada).")
    return o
