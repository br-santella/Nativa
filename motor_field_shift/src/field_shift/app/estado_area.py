"""Field state reported by the farmer: area problems and soil fertility (both OPTIONAL).

Hard rule: without the farmer's input NOTHING enters the analysis (no estimate, no default value). With it, the effect is
declarative and auditable in the tables below and uses the scales the engine already has (additive deltas on the `pragas` and
`solo` criteria, 0-1, plus extra cost items in the margin).

Sourcing policy (see docs/fontes_estado_area.md for URL, title, year and the excerpt each number came from):
- every number with a source we opened and read carries a short source label in the code and in the card;
- every number WITHOUT a confirmed source is marked "no confirmed source" here and says so in the card / ajustes_aplicados
  (`FONTE_ESTIMATIVA`) and in docs/pendencias.md.

State = {"problemas": [slugs], "fert": dict from `preparar_fertilidade` | None}, stored in rk["estado_area"].
User-facing texts and API field names stay in Portuguese; identifiers and comments are in English.
"""
from __future__ import annotations

import math
from pathlib import Path

import yaml

FONTE_ESTIMATIVA = "estimativa, sem fonte confirmada; validar com agrônomo/Embrapa"
_NO_SOURCE = "no confirmed source"

# --------------------------------------------------------------------------- vocabulary (catalog/vocabulario.yaml)
_PROBLEMAS_FALLBACK = ("nematoide", "mofo_branco", "cigarrinha", "compactacao")


def _carregar_problemas() -> tuple[str, ...]:
    p = Path(__file__).resolve().parents[4] / "catalog" / "vocabulario.yaml"
    try:
        return tuple(yaml.safe_load(p.read_text(encoding="utf-8"))["problemas_area"])
    except (OSError, KeyError, TypeError, yaml.YAMLError):
        return _PROBLEMAS_FALLBACK  # catalog missing (engine-only deploy); a test checks that both lists match


PROBLEMAS = _carregar_problemas()
PROBLEMAS_ROTULO = {"nematoide": "nematoide", "mofo_branco": "mofo-branco", "cigarrinha": "cigarrinha-do-milho",
                    "compactacao": "compactação"}

# --------------------------------------------------------------------------- source registry
# id -> (short label shown in the card, full reference). Only sources we actually opened and read are listed; the excerpt that
# supports each use is in docs/fontes_estado_area.md. URLs are repeated there.
SOURCES: dict[str, dict[str, str]] = {
    "brandao2008": dict(label="Brandão et al. 2008 (IAC Doc. 85)", year="2008",
                        title="Inibição da germinação carpogênica de Sclerotinia sclerotiorum em solos sob ILP com Brachiaria",
                        url="https://www.alice.cnptia.embrapa.br/alice/bitstream/doc/217679/1/159.pdf"),
    "ferro2010": dict(label="Ferro & Lobo Jr. 2010 (CONPEEX)", year="2010",
                      title="Efeito de espécies do SPD na Região Sul sobre parasitismo e germinação de escleródios de S. sclerotiorum",
                      url="https://www.alice.cnptia.embrapa.br/alice/bitstream/doc/886056/1/conpeex02.pdf"),
    "godoy2017": dict(label="Godoy 2017 (Embrapa Soja, CTC)", year="2017", title="Manejo de doenças na cultura da soja",
                      url="https://www.alice.cnptia.embrapa.br/alice/bitstream/doc/1074366/1/ID380530001.pdf"),
    "meyer2022": dict(label="Meyer & Bueno 2022 (Embrapa Soja, cap. 18)", year="2022", title="Bioinsumos na cultura da soja",
                      url="https://www.alice.cnptia.embrapa.br/alice/bitstream/doc/1147051/1/cap-18-Bioinsumos-na-cultura-da-soja.pdf"),
    "inomoto2009": dict(label="Inomoto & Asmus 2009 (Visão Agrícola 9)", year="2009",
                        title="Culturas de cobertura e de rotação devem ser plantas não hospedeiras de nematoides",
                        url="https://www.esalq.usp.br/visaoagricola/sites/default/files/VA9-Protecao04.pdf"),
    "mendes2012": dict(label="Mendes et al. 2012 (Jornada Embrapa Soja)", year="2012",
                       title="Manejo cultural do nematoide das lesões radiculares durante a entressafra da soja no Mato Grosso",
                       url="https://www.alice.cnptia.embrapa.br/alice/bitstream/doc/930216/1/ID33356.pdf"),
    "sabato2018": dict(label="Sabato 2018 (Embrapa Milho e Sorgo, CT 226)", year="2018",
                       title="Manejo do risco de enfezamentos e da cigarrinha no milho",
                       url="https://www.infoteca.cnptia.embrapa.br/infoteca/bitstream/doc/1091746/1/ct226.pdf"),
    "guia2020": dict(label="Guia de boas práticas, cigarrinha-do-milho (CropLife/Embrapa, 2020)", year="2020",
                     title="Guia de boas práticas para o manejo dos enfezamentos e da cigarrinha-do-milho",
                     url="https://www.infoteca.cnptia.embrapa.br/infoteca/bitstream/doc/1129511/1/Charles-Guia-Boas-Praticas-Cigarinha-do-Milho.pdf"),
    "franca2012": dict(label="França et al. 2012 (Embrapa Soja Doc. 312)", year="2012",
                       title="Uso de forrageiras tropicais em sistemas de sucessão com a soja e qualidade física do solo (basalto paranaense)",
                       url="https://www.alice.cnptia.embrapa.br/alice/bitstream/doc/575028/1/ID29982.pdf"),
    "torres_pd": dict(label="Torres et al., 500 Perguntas 500 Respostas: Plantio Direto (Embrapa)", year="s.d.",
                      title="Compactação do solo (cap. 8)",
                      url="https://www.alice.cnptia.embrapa.br/alice/bitstream/doc/44718/1/PROCI1998.00129.pdf"),
}

# --------------------------------------------------------------------------- A) area problems: qualitative levels
# OUR MODELLING CHOICE, NOT FROM THE LITERATURE: the literature gives direction (host / non-host, suppresses / favours), not a
# number on our 0-1 criteria. Each (problem, crop) cell gets one of three levels and ONE declared magnitude for all of them.
LEVEL_MAGNITUDE = 0.15
LEVEL_DELTA = {"favorece": +LEVEL_MAGNITUDE, "neutro": 0.0, "penaliza": -LEVEL_MAGNITUDE}

# problem -> target -> dict(level, criterion, sources, motive, caveat). Target: "segunda:<slug>" (2nd-window crop),
# "verao:<slug>" (summer crop) or "milho_sobre_milho". The rotation adds the summer and 2nd-window effects (the summer soybean
# weighs the same in every rotation of the block). A non-neutral cell REQUIRES at least one entry in `sources` (a test enforces it);
# a (problem, crop) pair that is absent here, or listed in NEUTRAL_NO_SOURCE, is neutral.
PROBLEM_EFFECTS: dict[str, dict[str, dict]] = {
    "mofo_branco": {  # Sclerotinia sclerotiorum
        "segunda:feijao_safrinha": dict(level="penaliza", criterion="pragas", sources=["brandao2008", "ferro2010"],
                                        motive="feijão comum é hospedeiro do mofo-branco"),
        "verao:soja": dict(level="penaliza", criterion="pragas", sources=["brandao2008", "godoy2017"],
                           motive="a soja é hospedeira do mofo-branco (recomenda-se rotação com espécies não hospedeiras)"),
        "segunda:soja_safrinha": dict(level="penaliza", criterion="pragas", sources=["brandao2008", "godoy2017"],
                                      motive="a soja é hospedeira do mofo-branco (recomenda-se rotação com espécies não hospedeiras)"),
        "segunda:nabo_forrageiro": dict(level="penaliza", criterion="pragas", sources=["ferro2010", "meyer2022"],
                                        motive="nabo forrageiro é hospedeiro: sofreu ataque severo em vaso e estimula a germinação dos escleródios"),
    },
    "nematoide": {
        "segunda:feijao_safrinha": dict(level="penaliza", criterion="pragas", sources=["inomoto2009"],
                                        motive="feijão comum é boa planta hospedeira de todos os nematoides da tabela (cisto, galhas, reniforme, lesões)",
                                        caveat="depende da espécie de nematoide da área"),
        "verao:soja": dict(level="penaliza", criterion="pragas", sources=["inomoto2009", "mendes2012"],
                           motive="a soja é boa hospedeira de Meloidogyne javanica e de Pratylenchus brachyurus (perdas de até 30% na soja)",
                           caveat="depende da espécie de nematoide; há resposta variável da soja a H. glycines, M. incognita e R. reniformis"),
        "segunda:soja_safrinha": dict(level="penaliza", criterion="pragas", sources=["inomoto2009", "mendes2012"],
                                      motive="a soja é boa hospedeira de Meloidogyne javanica e de Pratylenchus brachyurus",
                                      caveat="depende da espécie de nematoide da área"),
        "segunda:milheto_crotalaria": dict(level="favorece", criterion="pragas", sources=["inomoto2009", "mendes2012"],
                                           motive="Crotalaria spectabilis não é hospedeira e, sozinha ou com milheto ADR 300, reduziu o P. brachyurus na soja seguinte",
                                           caveat="vale para C. spectabilis (e C. breviflora); o milheto é má hospedeira variável conforme a cultivar e C. juncea tem resposta variável"),
    },
    "cigarrinha": {  # Dalbulus maidis
        "milho_sobre_milho": dict(level="penaliza", criterion="pragas", sources=["guia2020", "sabato2018"],
                                  motive="a semeadura sucessiva de milho mantém a cigarrinha e os enfezamentos entre safras (evitar milho sobre milho)"),
    },
    "compactacao": {  # effect on the `solo` criterion
        "segunda:milho_braquiaria": dict(level="favorece", criterion="solo", sources=["franca2012"],
                                         motive="Brachiaria ruziziensis (solteira ou com milho safrinha) reduziu a resistência à penetração na camada de 0,10–0,20 m",
                                         caveat="medido com B. ruziziensis no basalto paranaense; outras espécies/cultivares de braquiária não foram testadas"),
        "segunda:nabo_forrageiro": dict(level="favorece", criterion="solo", sources=["torres_pd"],
                                        motive="o nabo forrageiro é citado como espécie com potencial para romper camadas compactadas",
                                        caveat="indicação qualitativa; no ensaio de França et al. o consórcio aveia-preta + nabo não reduziu a compactação forte (> 6 MPa)"),
        "segunda:milheto_crotalaria": dict(level="favorece", criterion="solo", sources=["torres_pd"],
                                           motive="milheto e crotalárias são citados como espécies com potencial de descompactação",
                                           caveat="indicação qualitativa, sem medição própria"),
    },
}

# Plausible effects for which we found NO source: treated as neutral (neither penalise nor favour) and reported in the card and in
# docs/pendencias.md as "efeito plausível sem fonte". (problem, target) -> reason.
NEUTRAL_NO_SOURCE: dict[tuple[str, str], str] = {
    ("mofo_branco", "segunda:aveia_nabo"): "o nabo do mix é hospedeiro, mas não há fonte para o efeito do mix aveia + nabo",
    ("nematoide", "segunda:milho_braquiaria"): "depende da espécie: braquiária não hospeda M. javanica, M. incognita, H. glycines nem R. reniformis, "
                                               "mas hospeda P. brachyurus (Inomoto & Asmus 2009; Mendes et al. 2012); como a espécie não é informada, fica neutro",
    ("nematoide", "segunda:milho_safrinha"): "depende da espécie: o milho não hospeda H. glycines nem R. reniformis, mas hospeda M. incognita e P. brachyurus "
                                             "(Inomoto & Asmus 2009); como a espécie não é informada, fica neutro",
    ("nematoide", "segunda:nabo_forrageiro"): "o nabo hospeda M. javanica e M. incognita e não hospeda H. glycines (Inomoto & Asmus 2009); depende da espécie, fica neutro",
    ("nematoide", "verao:milho_verao"): "depende da espécie de nematoide (ver milho safrinha); fica neutro",
    ("cigarrinha", "segunda:milho_safrinha"): "o milho é o hospedeiro da cigarrinha, mas não há fonte que quantifique a penalidade do milho isolado; fica neutro",
    ("cigarrinha", "segunda:milho_braquiaria"): "o milho é o hospedeiro da cigarrinha, mas não há fonte que quantifique a penalidade do milho isolado; fica neutro",
    ("cigarrinha", "verao:milho_verao"): "o milho é o hospedeiro da cigarrinha, mas não há fonte que quantifique a penalidade do milho isolado; fica neutro",
    ("compactacao", "segunda:aveia_nabo"): "no ensaio de França et al. 2012 o consórcio aveia-preta + nabo não reduziu a compactação; fica neutro",
}


def _target_keys(c: dict) -> set[str]:
    return {f"segunda:{c['segunda']}", f"verao:{c['verao']}"} | ({"milho_sobre_milho"} if c.get("milho_sobre_milho") else set())


def _efeitos_problemas(c: dict, problemas) -> list[dict]:
    keys = _target_keys(c)
    out = []
    for p in problemas:
        for target, e in PROBLEM_EFFECTS[p].items():
            if target in keys and e["level"] != "neutro":
                out.append(dict(problema=p, alvo=target, nivel=e["level"], criterio=e["criterion"], delta=LEVEL_DELTA[e["level"]],
                                motivo=e["motive"], ressalva=e.get("caveat"), fontes=[SOURCES[s]["label"] for s in e["sources"]]))
    return out


def _neutros_sem_fonte(c: dict, problemas) -> list[str]:
    keys = _target_keys(c)
    return [f"{PROBLEMAS_ROTULO[p]} × {t.split(':')[-1].replace('_', ' ')}: efeito sem fonte confirmada, tratado como neutro ({why})"
            for (p, t), why in NEUTRAL_NO_SOURCE.items() if p in problemas and t in keys]


# --------------------------------------------------------------------------- B) fertility
# Fields (all optional; units of the Brazilian soil report): P Mehlich-1 mg/dm3, K/Ca/Mg/Al/CEC cmolc/dm3, V%.
CAMPOS_FERTILIDADE = {  # field: (min, max) plausible-value validation
    "p_mg_dm3": (0, 500), "k_cmolc_dm3": (0, 10), "ca_cmolc_dm3": (0, 40), "mg_cmolc_dm3": (0, 20),
    "al_cmolc_dm3": (0, 15), "v_pct": (0, 100), "ctc_cmolc_dm3": (0, 60),
}

FONTE_MANUAL = ("Manual de Adubação e Calagem para o Estado do Paraná (SBCS/NEPAR, Pauletti & Motta), Quadros 4–6 "
                "reproduzidos em SENAR-AR/PR, PR.0420 (2026)")
FONTE_MANUAL_URL = "https://www.sistemafaep.org.br/wp-content/uploads/2026/04/PR.0420-Nutrientes-e-Teores-de-Referencia_web.pdf"
_NEXT = math.nextafter  # "> x" classes are exclusive at x; the published tables skip decimals between integers (12 -> 13), which go to the lower class
_INF = math.inf

# P (Mehlich-1, mg/dm3) by clay class (g/kg). Exclusive upper limits per class, in order; "condicao_evitar" above the last limit.
# Source: Manual PR Quadro 5 (via SENAR-AR/PR PR.0420, p. 33).
P_CLAY_BANDS = ("<250", "250-400", ">400")
P_CLASSES = {
    "<250": [(6, "muito_baixo"), (13, "baixo"), (19, "medio"), (_NEXT(24, _INF), "alto"), (_INF, "muito_alto")],
    "250-400": [(4, "muito_baixo"), (9, "baixo"), (13, "medio"), (_NEXT(18, _INF), "alto"), (_INF, "muito_alto")],
    ">400": [(3, "muito_baixo"), (7, "baixo"), (10, "medio"), (_NEXT(12, _INF), "alto"), (_INF, "muito_alto")],
}
P_AVOID_ABOVE = {"<250": 120.0, "250-400": 90.0, ">400": 60.0}  # "Condições a evitar" (Quadro 5)
CLASSES = {  # classes that do not depend on clay; Manual PR Quadros 4 and 6 (via PR.0420, pp. 32-34)
    "k": [(0.06, "muito_baixo"), (0.13, "baixo"), (0.22, "medio"), (_NEXT(0.45, _INF), "alto"), (_INF, "muito_alto")],  # cmolc/dm3
    "v": [(21.0, "muito_baixo"), (36.0, "baixo"), (51.0, "medio"), (_NEXT(70.0, _INF), "alto"), (_INF, "muito_alto")],  # V%
    "al": [(0.3, "muito_baixo"), (0.8, "baixo"), (1.6, "medio"), (_NEXT(2.5, _INF), "alto"), (_INF, "muito_alto")],  # cmolc/dm3
}
V_AVOID_ABOVE = 90.0  # "Condições a evitar" for V% (Quadro 4)
CONSERVATIVE_CLAY_BAND = "<250"  # used when the farmer gives no clay: its limits are the highest, so a given P is read as the LOWEST class


def clay_band(argila_pct: float | None) -> tuple[str, str]:
    """(band, origin) for the P table. argila_pct (%) -> g/kg; no clay -> the most demanding band, with a warning origin."""
    if argila_pct is None:
        return CONSERVATIVE_CLAY_BAND, "não informada: usada a faixa de argila mais exigente (< 250 g/kg)"
    g = float(argila_pct) * 10.0
    return ("<250" if g < 250 else "250-400" if g <= 400 else ">400"), "informada"


def _classify(x: float, limits: list[tuple[float, str]]) -> str:
    return next(name for lim, name in limits if x < lim)


def _classe_p(p: float, band: str) -> str:
    return "condicao_evitar" if p > P_AVOID_ABOVE[band] else _classify(p, P_CLASSES[band])


# Liming by base saturation (Manual PR method, SENAR-AR/PR PR.0404, pp. 78-79): NC (t/ha) = (V2 - V1) x CEC / PRNT, CEC in cmolc/dm3
# (pH 7.0) and PRNT in %; "when the PRNT is unknown use 100". We use the CBPTT (2020) reference for ground limestone instead:
# f = 100/PRNT = 1.3 when the PRNT is unknown, i.e. PRNT = 76.9% (Informações Técnicas para Trigo e Triticale, safra 2020, eq. 1).
PRNT = 100.0 / 1.3 / 100.0  # fraction
PRNT_FONTE = "CBPTT 2020 (Trigo e Triticale), f = 1,3 para calcário moído de PRNT desconhecido"
NC_MAX_T_HA = 6.0  # cap of one application (above this, split it): no confirmed source
CALCARIO_R_T = 220.0  # R$/t applied (product + freight + spreading): no confirmed source (no public regional price found)
CALAGEM_ANOS = 3  # lime cost is spread over this many years; only partial support: CBPTT 2020 says "reanalisar o solo após três anos"
# V2 (target base saturation) per 2nd-window crop. The Manual PR puts corn, wheat, beans, sorghum and soybean in the same acid-tolerance
# class "baixa" (V 51-70%), so we use ONE value inside that range. Soybean: 60% (Manual PR, via Embrapa Soja Doc. 417, 2019);
# wheat: V2 = 60% in the CBPTT 2020 equation. Corn, beans, sorghum: only the class range is confirmed; 60 is our pick inside it.
V2 = {"milho_safrinha": 60.0, "milho_braquiaria": 60.0, "trigo": 60.0, "feijao_safrinha": 60.0, "sorgo": 60.0}
# Liming corrects the acidity of the AREA, not of one crop: covers and fallow are charged with it too (with the same V2), otherwise they
# would look ~R$ 550/ha better than grain crops on an acid soil. Modelling premise, to be confirmed by an agronomist.
V2_AREA = 60.0
V2_FONTE_CURTA = "60% (faixa 51–70% do Manual PR; soja 60% e trigo 60% em Embrapa Soja Doc. 417 e CBPTT 2020)"
V2_FONTE = ("V2 de 60% (faixa 51–70% do Manual PR para milho, trigo, feijão, sorgo e soja: SENAR-AR/PR PR.0404; soja 60% e trigo 60%: "
            "Embrapa Soja Doc. 417 e CBPTT 2020; a Embrapa Soja cita também 70% para a soja nas 'Tecnologias de Produção' de 2013, "
            "então o valor exato para milho, feijão e sorgo é escolha nossa dentro da faixa)")

# P2O5/K2O doses (kg/ha). The margin already carries the CONAB reference fertilization, which we ASSUME equals the "medio" class
# (no source for what CONAB embeds); the extra cost is (dose of the class - dose of "medio") x price, negative (saving) on rich soil.
# Corn: Manual PR 2nd ed. 2017 Tabelas 2 and 3 (reproduced in Los 2025, UEPG TCC), expected yield < 8 Mg/ha column (safrinha
# premise: confirm against the farm's yield expectation); we take the MIDPOINT of each published range.
DOSE_P2O5_CORN = {"muito_baixo": 120.0, "baixo": 100.0, "medio": 80.0, "alto": 60.0, "muito_alto": 40.0, "condicao_evitar": 0.0}
DOSE_K2O_CORN = {"muito_baixo": 115.0, "baixo": 90.0, "medio": 55.0, "alto": 30.0, "muito_alto": 20.0}
CORN_DOSE_FONTE = "Manual PR 2017 (Tab. 2 e 3, expectativa < 8 t/ha, ponto médio da faixa)"
# Wheat: CBPTT 2020 (Informações Técnicas para Trigo e Triticale, Tabelas 7 e 8), by soil value (not by class); midpoint of the range.
WHEAT_P2O5 = [(5.0, 75.0), (_NEXT(9.0, _INF), 50.0), (_INF, 30.0)]  # P mg/dm3: < 5 -> 60-90; 5-9 -> 40-60; > 9 -> 20-40
WHEAT_K2O = [(0.10, 70.0), (_NEXT(0.30, _INF), 50.0), (_INF, 35.0)]  # K cmolc/dm3: < 0.10 -> 60-80; 0.10-0.30 -> 40-60; > 0.30 -> 30-40
WHEAT_BASELINE = dict(p2o5=50.0, k2o=50.0)  # the 5-9 mg/dm3 and 0.10-0.30 cmolc/dm3 bands, taken as the CONAB reference
WHEAT_DOSE_FONTE = "CBPTT 2020 (Tab. 7 e 8, ponto médio da faixa)"
# Beans and sorghum: NO confirmed source for P/K doses; our old class table, scaled by crop demand (kept as estimate).
DOSE_P2O5_ESTIMATE = {"muito_baixo": 90.0, "baixo": 70.0, "medio": 50.0, "alto": 30.0, "muito_alto": 0.0, "condicao_evitar": 0.0}
DOSE_K2O_ESTIMATE = {"muito_baixo": 80.0, "baixo": 80.0, "medio": 50.0, "alto": 30.0, "muito_alto": 30.0}
EXIGENCIA_PK = {"feijao_safrinha": 1.0, "sorgo": 0.6}  # demand factor for the estimate tables: no confirmed source
# Prices: CNA/Cepea Campo Futuro, average of MT and PR, 19/09/2025 ("CNA Insumos Agropecuários", ed. Set/25): SSP R$ 2,104.7/t and
# KCl R$ 2,898.8/t. The nutrient grades (SSP 18% P2O5, KCl 58% K2O) are ASSUMED, not from that report.
PRECO_FONTE = "CNA/Cepea Campo Futuro (média MT e PR) em 19/09/2025: SSP R$ 2.104,7/t e KCl R$ 2.898,8/t; teores 18% P2O5 e 58% K2O assumidos"
PRECO_P2O5_R_KG = 2104.7 / (1000.0 * 0.18)
PRECO_K2O_R_KG = 2898.8 / (1000.0 * 0.58)

# Penalty on the `solo` criterion for an acid-sensitive crop: PENALIDADE_ACIDEZ x severity (0-2) x sensitivity. The Manual PR puts
# all five crops in the same tolerance class, so sensitivity is equal. The penalty size itself is our modelling choice (no source).
# Severity = max(Al: medio 1, alto/muito_alto 2; V%: medio 1, baixo/muito_baixo 2).
PENALIDADE_ACIDEZ = 0.08
SENSIBILIDADE_ACIDEZ = {"trigo": 1.0, "milho_safrinha": 1.0, "milho_braquiaria": 1.0, "feijao_safrinha": 1.0, "sorgo": 1.0}
# Bonus on `solo` for nutrient-cycling covers when P or K are low, and for crotalaria when the soil is poor: modelling choice, no source.
BONUS_RECICLAGEM = {"nabo_forrageiro": 0.10, "aveia_nabo": 0.06, "milho_braquiaria": 0.08}
BONUS_CROTALARIA = {"milheto_crotalaria": 0.05}


def preparar_fertilidade(f: dict | None, argila_pct: float | None = None) -> dict | None:
    """Interprets the informed fertility (dict with a subset of CAMPOS_FERTILIDADE, already validated) into classes.
    `argila_pct` (the farmer's clay %, optional) selects the P table by clay band. None if nothing was informed.
    Nothing is estimated: V% is only derived when Ca, Mg, K and CEC come together (V = (Ca+Mg+K)/CEC)."""
    f = {k: float(v) for k, v in (f or {}).items() if k in CAMPOS_FERTILIDADE and v is not None}
    if not f:
        return None
    v_origem = "informada" if "v_pct" in f else None
    if v_origem is None and all(k in f for k in ("ca_cmolc_dm3", "mg_cmolc_dm3", "k_cmolc_dm3", "ctc_cmolc_dm3")) and f["ctc_cmolc_dm3"] > 0:
        f["v_pct"] = min(100.0, 100 * (f["ca_cmolc_dm3"] + f["mg_cmolc_dm3"] + f["k_cmolc_dm3"]) / f["ctc_cmolc_dm3"])
        v_origem = "derivada de (Ca+Mg+K)/CTC"
    band, band_origem = clay_band(argila_pct)
    classes = {}
    if "p_mg_dm3" in f: classes["p"] = _classe_p(f["p_mg_dm3"], band)
    if "k_cmolc_dm3" in f: classes["k"] = _classify(f["k_cmolc_dm3"], CLASSES["k"])
    if "v_pct" in f: classes["v"] = "condicao_evitar" if f["v_pct"] > V_AVOID_ABOVE else _classify(f["v_pct"], CLASSES["v"])
    if "al_cmolc_dm3" in f: classes["al"] = _classify(f["al_cmolc_dm3"], CLASSES["al"])
    sev = max([{"muito_baixo": 0, "baixo": 0, "medio": 1, "alto": 2, "muito_alto": 2}[classes["al"]] if "al" in classes else 0,
               {"muito_baixo": 2, "baixo": 2, "medio": 1}.get(classes.get("v"), 0)])
    pk_baixo = classes.get("p") in ("muito_baixo", "baixo") or classes.get("k") in ("muito_baixo", "baixo")
    return dict(valores=f, classes=classes, v_origem=v_origem, severidade_acidez=sev, pk_baixo=pk_baixo,
                pobre=pk_baixo or sev > 0, informados=[k for k in CAMPOS_FERTILIDADE if k in f],
                ausentes=[k for k in CAMPOS_FERTILIDADE if k not in f],
                argila_faixa_g_kg=band if "p" in classes else None, argila_origem=band_origem if "p" in classes else None)


def _nc_t_ha(fert: dict, v2: float) -> float | None:
    """Liming requirement (t/ha of limestone at the reference PRNT); None if V% or CEC is missing (nothing is estimated)."""
    v, ctc = fert["valores"].get("v_pct"), fert["valores"].get("ctc_cmolc_dm3")
    if v is None or ctc is None:
        return None
    return min(NC_MAX_T_HA, max(0.0, (v2 - v) / 100.0 * ctc / PRNT))


def _midpoint_dose(value: float, table: list[tuple[float, float]]) -> float:
    return next(d for lim, d in table if value < lim)


def _dose_delta(seg: str, fert: dict) -> tuple[float, float, list[str], str] | None:
    """(extra kg P2O5/ha, extra kg K2O/ha, text parts, source) of the 2nd-window crop vs the assumed 'medio' reference; None if no dose model."""
    cl, v = fert["classes"], fert["valores"]
    if seg in ("milho_safrinha", "milho_braquiaria"):
        dp = (DOSE_P2O5_CORN[cl["p"]] - DOSE_P2O5_CORN["medio"]) if "p" in cl else None
        dk = (DOSE_K2O_CORN[cl["k"]] - DOSE_K2O_CORN["medio"]) if "k" in cl else None
        src = CORN_DOSE_FONTE
    elif seg == "trigo":
        dp = (_midpoint_dose(v["p_mg_dm3"], WHEAT_P2O5) - WHEAT_BASELINE["p2o5"]) if "p_mg_dm3" in v else None
        dk = (_midpoint_dose(v["k_cmolc_dm3"], WHEAT_K2O) - WHEAT_BASELINE["k2o"]) if "k_cmolc_dm3" in v else None
        src = WHEAT_DOSE_FONTE
    elif seg in EXIGENCIA_PK:
        ex = EXIGENCIA_PK[seg]
        dp = (DOSE_P2O5_ESTIMATE[cl["p"]] - DOSE_P2O5_ESTIMATE["medio"]) * ex if "p" in cl else None
        dk = (DOSE_K2O_ESTIMATE[cl["k"]] - DOSE_K2O_ESTIMATE["medio"]) * ex if "k" in cl else None
        src = f"doses {_NO_SOURCE} ({FONTE_ESTIMATIVA})"
    else:
        return None
    if dp is None and dk is None:
        return None
    parts = []
    if dp is not None:
        parts.append(f"P {cl['p'].replace('_', ' ')} ({dp:+.0f} kg P2O5/ha)")
    if dk is not None:
        parts.append(f"K {cl['k'].replace('_', ' ')} ({dk:+.0f} kg K2O/ha)")
    return dp or 0.0, dk or 0.0, parts, src


def custos(c: dict, estado: dict | None) -> list[dict]:
    """Extra cost items from fertility (liming and P/K fertilization) in the `extras_custo` format. [] without fertility."""
    fert = (estado or {}).get("fert")
    if not fert:
        return []
    out, seg = [], c["segunda"]
    v2 = V2.get(seg, V2_AREA)
    nc = _nc_t_ha(fert, v2)
    if nc:
        anual = nc * CALCARIO_R_T / CALAGEM_ANOS
        area_note = "" if seg in V2 else ("; calagem é necessidade da área e também é cobrada em cobertura/pousio, para não favorecê-las "
                                          "(premissa de modelagem, validar com agrônomo)")
        out.append(dict(chave="calagem", rotulo="Calagem", custo=anual,
                        detalhe=f"NC = ({v2:g} − V% {fert['valores']['v_pct']:.0f})/100 × CTC {fert['valores']['ctc_cmolc_dm3']:g} / PRNT "
                                f"{PRNT:.0%} = {nc:.1f} t/ha × R$ {CALCARIO_R_T:g}/t, diluída em {CALAGEM_ANOS} anos; fórmula do Manual PR "
                                f"(SENAR-AR/PR PR.0404) com PRNT de referência da {PRNT_FONTE}; V2: {V2_FONTE_CURTA}; "
                                f"preço do calcário, teto de 6 t/ha e diluição em 3 anos: {FONTE_ESTIMATIVA}{area_note}"))
    dd = _dose_delta(seg, fert)
    if dd:
        dp, dk, parts, src = dd
        delta = dp * PRECO_P2O5_R_KG + dk * PRECO_K2O_R_KG
        out.append(dict(chave="adubacao_pk", rotulo="Adubação P/K acima/abaixo da referência" if delta >= 0 else "Economia de adubação P/K",
                        custo=delta, detalhe=", ".join(parts) + f" em relação à classe média, que ASSUMIMOS embutida no custo CONAB (premissa sem fonte); "
                                                              f"doses: {src}; preços: {PRECO_FONTE}"))
    return out


def ajuste(c: dict, estado: dict | None) -> dict:
    """Additive deltas on the candidate's criteria: {"pragas": x, "solo": y, "efeitos": [dict(origem, criterio, delta, motivo, ...)]}.
    Without state (nothing informed) it returns zeros and no effects."""
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
                                       motivo=f"cultura sensível à acidez (Al {fert['classes'].get('al', 'n/i').replace('_', ' ')}, "
                                              f"V% {fert['classes'].get('v', 'n/i').replace('_', ' ')}); severidade {fert['severidade_acidez']}; "
                                              f"classes do Manual PR, tamanho da penalidade é escolha de modelagem ({FONTE_ESTIMATIVA})"))
        b = BONUS_RECICLAGEM.get(seg, 0.0) if fert["pk_baixo"] else 0.0
        if b:
            out["solo"] += b
            out["efeitos"].append(dict(origem="fertilidade", criterio="solo", delta=b, problema=None,
                                       motivo=f"recicla K/P em solo com P ou K baixos; tamanho do bônus é escolha de modelagem ({FONTE_ESTIMATIVA})"))
        b = BONUS_CROTALARIA.get(seg, 0.0) if fert["pobre"] else 0.0
        if b:
            out["solo"] += b
            out["efeitos"].append(dict(origem="fertilidade", criterio="solo", delta=b, problema=None,
                                       motivo=f"crotalária fixa N e adiciona matéria orgânica em solo pobre; tamanho do bônus é escolha de modelagem ({FONTE_ESTIMATIVA})"))
    return out


# --------------------------------------------------------------------------- texts (card and methodology)
def _txt_fert(fert: dict) -> str:
    rot = {"p_mg_dm3": "P", "k_cmolc_dm3": "K", "ca_cmolc_dm3": "Ca", "mg_cmolc_dm3": "Mg", "al_cmolc_dm3": "Al", "v_pct": "V%",
           "ctc_cmolc_dm3": "CTC"}
    v = fert["valores"]
    return ", ".join(f"{rot[k]} {v[k]:g}" for k in fert["informados"]) + (
        f"; V% {v['v_pct']:.0f} {fert['v_origem']}" if fert["v_origem"] and fert["v_origem"] != "informada" else "")


def _escala_txt() -> str:
    return (f"favorece +{LEVEL_MAGNITUDE:g}, penaliza −{LEVEL_MAGNITUDE:g} no critério (a direção vem da literatura; a magnitude "
            f"é escolha de modelagem nossa)")


def card(c: dict, estado: dict | None) -> dict:
    """Card lines of the candidate: `evidencias`, `lacunas` (what was not considered) and `revisar`."""
    est = estado or {}
    probs, fert = est.get("problemas") or [], est.get("fert")
    ev, lac, rev = [], [], []
    aj = ajuste(c, estado)
    if probs:
        lac.append("Problemas da área considerados: " + ", ".join(PROBLEMAS_ROTULO[p] for p in probs)
                   + f" (efeito por cultura em três níveis: {_escala_txt()}).")
        efs = [e for e in aj["efeitos"] if e["problema"]]
        for e in efs:
            ev.append(f"Problema da área ({PROBLEMAS_ROTULO[e['problema']]}): {e['nivel']}, critério {e['criterio']} {e['delta']:+.2f} "
                      f"({e['motivo']}; fonte: {'; '.join(e['fontes'])}" + (f"; ressalva: {e['ressalva']}" if e["ressalva"] else "") + ").")
        if not efs:
            ev.append("Problemas da área informados (" + ", ".join(PROBLEMAS_ROTULO[p] for p in probs)
                      + "): sem efeito com fonte confirmada nesta rotação (neutro).")
        lac.extend(_neutros_sem_fonte(c, probs))
    else:
        lac.append("Problemas da área (nematoide, mofo-branco, cigarrinha, compactação) não informados: não considerados.")
    if fert:
        ev.append(f"Fertilidade informada pelo produtor ({_txt_fert(fert)}); classes: "
                  + ", ".join(f"{k.upper()} {v.replace('_', ' ')}" for k, v in fert["classes"].items()) + f" ({FONTE_MANUAL}).")
        if fert.get("argila_faixa_g_kg"):
            ev.append(f"Classe de P pela argila {fert['argila_faixa_g_kg']} g/kg ({fert['argila_origem']}).")
        for e in (x for x in aj["efeitos"] if x["origem"] == "fertilidade"):
            ev.append(f"Fertilidade: critério {e['criterio']} {e['delta']:+.2f} ({e['motivo']}).")
        for it in custos(c, estado):
            ev.append(f"Fertilidade: {it['rotulo']} {'+' if it['custo'] >= 0 else '−'}R$ {abs(it['custo']):.0f}/ha/ano ({it['detalhe']}).")
        if _nc_t_ha(fert, V2.get(c["segunda"], V2_AREA)) is None:
            lac.append("Calagem não calculada: faltam V% (ou Ca+Mg+K+CTC) e CTC informados; nada foi estimado.")
        if fert["ausentes"]:
            lac.append("Fertilidade parcial: não informados " + ", ".join(fert["ausentes"]) + "; esses itens não entram na análise.")
        if fert.get("argila_faixa_g_kg") and not fert["argila_origem"].startswith("informada"):
            lac.append("Argila não informada: a classe de P usou a faixa mais exigente do Manual PR (< 250 g/kg); informe argila_pct para a classe correta.")
        if c["segunda"] in EXIGENCIA_PK:
            lac.append(f"Doses de P2O5/K2O de {c['segunda'].replace('_', ' ')}: {_NO_SOURCE} ({FONTE_ESTIMATIVA}).")
        lac.append(f"Fertilidade: classes e fórmula de calagem confirmadas no Manual PR; {V2_FONTE}. Preço do calcário, teto de dose e "
                   f"diluição da calagem: {FONTE_ESTIMATIVA}. Penalidade/bônus no critério solo: escolha de modelagem sem fonte. "
                   "Calagem e adubação da cultura de verão não entram (iguais em todas as rotações do bloco).")
        rev.append("Fertilidade: confirmar doses de calagem e adubação com o agrônomo e o laudo completo.")
    else:
        lac.append("Fertilidade não considerada (não informada): sem custo de adubação/calagem e sem penalidade ou bônus por fertilidade.")
    return dict(evidencias=ev, lacunas=lac, revisar=rev)


def ajustes_aplicados(estado: dict | None, analise_informada: bool) -> list[str]:
    """Sentences for `metodologia.ajustes_aplicados` about the field state. Empty if the farmer informed neither problems nor soil
    analysis (the response stays identical to the previous one; the card already says what was not considered)."""
    est = estado or {}
    probs, fert = est.get("problemas") or [], est.get("fert")
    if not (probs or fert or analise_informada):
        return []
    o = []
    if probs:
        o.append("Problemas da área informados pelo produtor (" + ", ".join(PROBLEMAS_ROTULO[p] for p in probs)
                 + f") ajustam os critérios pragas e solo por cultura em três níveis (favorece/neutro/penaliza; {_escala_txt()}). "
                 "Só há efeito onde existe fonte lida (Embrapa/artigos, listadas em docs/fontes_estado_area.md); sem fonte, o efeito é neutro.")
    else:
        o.append("Problemas da área não informados: não considerados.")
    if fert:
        o.append("Fertilidade informada pelo produtor (" + ", ".join(fert["informados"]) + "): classes de P (por argila), K, V% e Al do Manual de "
                 "Adubação e Calagem do Paraná; custo de calagem (saturação por bases, fórmula do Manual) e de adubação P/K por cultura na margem "
                 "(doses do Manual PR para o milho e da CBPTT 2020 para o trigo; feijão e sorgo " + FONTE_ESTIMATIVA + "), penalidade no critério solo "
                 "para cultura sensível em solo ácido/pobre e bônus para cobertura recicladora e crotalária (escolha de modelagem sem fonte); "
                 "itens não informados não entram. Preço do calcário, teto de dose e diluição da calagem: " + FONTE_ESTIMATIVA + ".")
    else:
        o.append("Fertilidade não considerada (não informada).")
    return o
