"""Field state reported by the farmer: area problems and soil fertility (both OPTIONAL).

Hard rule: without the farmer's input NOTHING enters the analysis (no estimate, no default value). With it, the effect is
declarative and auditable in the tables below and uses the scales the engine already has (additive deltas on the `pragas` and
`solo` criteria, 0-1, plus extra cost items in the margin).

Sourcing policy (see docs/fontes_estado_area.md for URL, title, year and the excerpt each number came from):
- every number with a source we opened and read carries a short source label in the code and in the card;
- every number WITHOUT a confirmed source is marked "no confirmed source" here and says so in the card / ajustes_aplicados
  (`ESTIMATE_SOURCE`) and in docs/pendencias.md.

State = {"problemas": [slugs], "fert": dict from `prepare_fertility` | None}, stored in rk["estado_area"].
User-facing texts and API field names stay in Portuguese; identifiers and comments are in English.
"""
from __future__ import annotations

import math
from pathlib import Path

import yaml

from field_shift.i18n import Join, Msg

ESTIMATE_SOURCE = "estimativa, sem fonte confirmada; validar com agrônomo/Embrapa"
_NO_SOURCE = "no confirmed source"

# Vocabulary (catalog/vocabulario.yaml)
_PROBLEMS_FALLBACK = ("nematoide", "mofo_branco", "cigarrinha", "compactacao")


def _load_problems() -> tuple[str, ...]:
    p = Path(__file__).resolve().parents[4] / "catalog" / "vocabulario.yaml"
    try:
        return tuple(yaml.safe_load(p.read_text(encoding="utf-8"))["problemas_area"])
    except (OSError, KeyError, TypeError, yaml.YAMLError):
        return _PROBLEMS_FALLBACK  # catalog missing (engine-only deploy); a test checks that both lists match


PROBLEMS = _load_problems()
PROBLEM_LABELS = {"nematoide": "nematoide", "mofo_branco": "mofo-branco", "cigarrinha": "cigarrinha-do-milho",
                    "compactacao": "compactação"}

# Source registry
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
    "resende2021": dict(label="Resende et al. 2021 (Embrapa Milho e Sorgo, CT 277)", year="2021",
                        title="Créditos de nutrientes e matéria orgânica no solo pela inserção do capim-braquiária em sistemas de culturas anuais",
                        url="https://www.infoteca.cnptia.embrapa.br/infoteca/bitstream/doc/1135669/1/CIRC-TEC-277-Creditos-nutrientes-materia-organica-solo-capim-braquiaria.pdf"),
    "betta2008": dict(label="Betta et al. 2008 (FESURV/Embrapa Solos)", year="2008",
                      title="Efeito da Brachiaria ruziziensis sobre a ciclagem do P, K e produtividade da soja",
                      url="https://www.infoteca.cnptia.embrapa.br/infoteca/bitstream/doc/339765/1/Efeito-da-Brachiaria-ruziziensis-sobre-a-ciclagem-do-P-K-e-produtividade-da-soja-2008.pdf"),
    "viola2013": dict(label="Viola et al. 2013 (Bragantia 72, Pato Branco-PR)", year="2013",
                      title="Adubação verde e nitrogenada na cultura do trigo em plantio direto",
                      url="https://www.redalyc.org/pdf/908/90826421010.pdf"),
    "bertin2005": dict(label="Bertin et al. 2005 (Acta Sci. Biol. Sci. 27)", year="2005",
                       title="Plantas de cobertura em pré-safra ao milho em plantio direto",
                       url="https://www.redalyc.org/pdf/1871/187117381001.pdf"),
    "manual_pr": dict(label="Manual de Adubação e Calagem do Paraná (Pauletti & Motta 2019, via SENAR-AR/PR PR.0420)", year="2019",
                      title="Interpretação dos parâmetros químicos no solo para o estado do Paraná (Quadro 4: classes de C orgânico)",
                      url="https://www.sistemafaep.org.br/wp-content/uploads/2026/04/PR.0420-Nutrientes-e-Teores-de-Referencia_web.pdf"),
    "pr0404": dict(label="Manual PR via SENAR-AR/PR PR.0404 (2025), tolerância à acidez", year="2025",
                   title="Amostragem e calagem do solo (milho, trigo, feijão, sorgo e soja na classe de tolerância à acidez 'baixa', V 51–70%)",
                   url="https://www.sistemafaep.org.br/wp-content/uploads/2026/02/PR.0404-Amostragem-e-calagem-do-solo_web.pdf"),
}

# A) area problems: qualitative levels
# Our modelling choice, not from the literature: the literature gives direction (host / non-host, suppresses / favours), not a
# number on our 0-1 criteria. Each (problem, crop) cell gets one of three levels and one declared magnitude for all of them.
LEVEL_MAGNITUDE = 0.15
LEVEL_DELTA = {"favorece": +LEVEL_MAGNITUDE, "neutro": 0.0, "penaliza": -LEVEL_MAGNITUDE}

# problem -> target -> dict(level, criterion, sources, motive, caveat). Target: "segunda:<slug>" (2nd-window crop),
# "verao:<slug>" (summer crop) or "milho_sobre_milho". The rotation adds the summer and 2nd-window effects (the summer soybean
# weighs the same in every rotation of the block). A non-neutral cell requires at least one entry in `sources` (a test enforces it);
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

# Plausible effects for which we found no source: treated as neutral (neither penalise nor favour) and reported in the card and in
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


def _problem_effects(c: dict, problems) -> list[dict]:
    keys = _target_keys(c)
    out = []
    for p in problems:
        for target, e in PROBLEM_EFFECTS[p].items():
            if target in keys and e["level"] != "neutro":
                out.append(dict(problema=p, alvo=target, nivel=e["level"], criterio=e["criterion"], delta=LEVEL_DELTA[e["level"]],
                                motivo=e["motive"], ressalva=e.get("caveat"), fontes=[SOURCES[s]["label"] for s in e["sources"]]))
    return out


def _unsourced_neutrals(c: dict, problems) -> list[str]:
    keys = _target_keys(c)
    return [f"{PROBLEM_LABELS[p]} × {t.split(':')[-1].replace('_', ' ')}: efeito sem fonte confirmada, tratado como neutro ({why})"
            for (p, t), why in NEUTRAL_NO_SOURCE.items() if p in problems and t in keys]


# B) fertility
# Fields (all optional; units of the Brazilian soil report): P Mehlich-1 mg/dm3, K/Ca/Mg/Al/CEC cmolc/dm3, V%.
FERTILITY_FIELDS = {  # field: (min, max) plausible-value validation
    "p_mg_dm3": (0, 500), "k_cmolc_dm3": (0, 10), "ca_cmolc_dm3": (0, 40), "mg_cmolc_dm3": (0, 20),
    "al_cmolc_dm3": (0, 15), "v_pct": (0, 100), "ctc_cmolc_dm3": (0, 60),
}

MANUAL_SOURCE = ("Manual de Adubação e Calagem para o Estado do Paraná (SBCS/NEPAR, Pauletti & Motta), Quadros 4–6 "
                "reproduzidos em SENAR-AR/PR, PR.0420 (2026)")
MANUAL_SOURCE_URL = "https://www.sistemafaep.org.br/wp-content/uploads/2026/04/PR.0420-Nutrientes-e-Teores-de-Referencia_web.pdf"
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
CONSERVATIVE_CLAY_BAND = "<250"  # used when the farmer gives no clay: its limits are the highest, so a given P is read as the lowest class


def clay_band(clay_pct: float | None) -> tuple[str, str]:
    """(band, origin) for the P table. argila_pct (%) -> g/kg; no clay -> the most demanding band, with a warning origin."""
    if clay_pct is None:
        return CONSERVATIVE_CLAY_BAND, "não informada: usada a faixa de argila mais exigente (< 250 g/kg)"
    g = float(clay_pct) * 10.0
    return ("<250" if g < 250 else "250-400" if g <= 400 else ">400"), "informada"


def _classify(x: float, limits: list[tuple[float, str]]) -> str:
    return next(name for lim, name in limits if x < lim)


def _p_class(p: float, band: str) -> str:
    return "condicao_evitar" if p > P_AVOID_ABOVE[band] else _classify(p, P_CLASSES[band])


# Liming by base saturation (Manual PR method, SENAR-AR/PR PR.0404, pp. 78-79): NC (t/ha) = (V2 - V1) x CEC / PRNT, CEC in cmolc/dm3
# (pH 7.0) and PRNT in %; "when the PRNT is unknown use 100". We use the CBPTT (2020) reference for ground limestone instead:
# f = 100/PRNT = 1.3 when the PRNT is unknown, i.e. PRNT = 76.9% (Informações Técnicas para Trigo e Triticale, safra 2020, eq. 1).
PRNT = 100.0 / 1.3 / 100.0  # fraction
PRNT_SOURCE = "CBPTT 2020 (Trigo e Triticale), f = 1,3 para calcário moído de PRNT desconhecido"
NC_MAX_T_HA = 6.0  # cap of one application (above this, split it): no confirmed source
LIME_R_T = 220.0  # R$/t applied (product + freight + spreading): no confirmed source (no public regional price found)
LIMING_YEARS = 3  # lime cost is spread over this many years; only partial support: CBPTT 2020 says "reanalisar o solo após três anos"
# V2 (target base saturation) per 2nd-window crop. The Manual PR puts corn, wheat, beans, sorghum and soybean in the same acid-tolerance
# class "baixa" (V 51-70%), so we use one value inside that range. Soybean: 60% (Manual PR, via Embrapa Soja Doc. 417, 2019);
# wheat: V2 = 60% in the CBPTT 2020 equation. Corn, beans, sorghum: only the class range is confirmed; 60 is our pick inside it.
V2 = {"milho_safrinha": 60.0, "milho_braquiaria": 60.0, "trigo": 60.0, "feijao_safrinha": 60.0, "sorgo": 60.0}
# Liming corrects the acidity of the area, not of one crop: covers and fallow are charged with it too (with the same V2), otherwise they
# would look ~R$ 550/ha better than grain crops on an acid soil. Modelling premise, to be confirmed by an agronomist.
V2_AREA = 60.0
V2_SHORT_SOURCE = "60% (faixa 51–70% do Manual PR; soja 60% e trigo 60% em Embrapa Soja Doc. 417 e CBPTT 2020)"
V2_SOURCE = ("V2 de 60% (faixa 51–70% do Manual PR para milho, trigo, feijão, sorgo e soja: SENAR-AR/PR PR.0404; soja 60% e trigo 60%: "
            "Embrapa Soja Doc. 417 e CBPTT 2020; a Embrapa Soja cita também 70% para a soja nas 'Tecnologias de Produção' de 2013, "
            "então o valor exato para milho, feijão e sorgo é escolha nossa dentro da faixa)")

# P2O5/K2O doses (kg/ha). The margin already carries the CONAB reference fertilization, which we assume equals the "medio" class
# (no source for what CONAB embeds); the extra cost is (dose of the class - dose of "medio") x price, negative (saving) on rich soil.
# Corn: Manual PR 2nd ed. 2017 Tabelas 2 and 3 (reproduced in Los 2025, UEPG TCC), expected yield < 8 Mg/ha column (safrinha
# premise: confirm against the farm's yield expectation); we take the midpoint of each published range.
DOSE_P2O5_CORN = {"muito_baixo": 120.0, "baixo": 100.0, "medio": 80.0, "alto": 60.0, "muito_alto": 40.0, "condicao_evitar": 0.0}
DOSE_K2O_CORN = {"muito_baixo": 115.0, "baixo": 90.0, "medio": 55.0, "alto": 30.0, "muito_alto": 20.0}
CORN_DOSE_SOURCE = "Manual PR 2017 (Tab. 2 e 3, expectativa < 8 t/ha, ponto médio da faixa)"
# Wheat: CBPTT 2020 (Informações Técnicas para Trigo e Triticale, Tabelas 7 e 8), by soil value (not by class); midpoint of the range.
WHEAT_P2O5 = [(5.0, 75.0), (_NEXT(9.0, _INF), 50.0), (_INF, 30.0)]  # P mg/dm3: < 5 -> 60-90; 5-9 -> 40-60; > 9 -> 20-40
WHEAT_K2O = [(0.10, 70.0), (_NEXT(0.30, _INF), 50.0), (_INF, 35.0)]  # K cmolc/dm3: < 0.10 -> 60-80; 0.10-0.30 -> 40-60; > 0.30 -> 30-40
WHEAT_BASELINE = dict(p2o5=50.0, k2o=50.0)  # the 5-9 mg/dm3 and 0.10-0.30 cmolc/dm3 bands, taken as the CONAB reference
WHEAT_DOSE_SOURCE = "CBPTT 2020 (Tab. 7 e 8, ponto médio da faixa)"
# Beans and sorghum: no confirmed source for P/K doses; our old class table, scaled by crop demand (kept as estimate).
P2O5_DOSE_ESTIMATE = {"muito_baixo": 90.0, "baixo": 70.0, "medio": 50.0, "alto": 30.0, "muito_alto": 0.0, "condicao_evitar": 0.0}
K2O_DOSE_ESTIMATE = {"muito_baixo": 80.0, "baixo": 80.0, "medio": 50.0, "alto": 30.0, "muito_alto": 30.0}
PK_DEMAND = {"feijao_safrinha": 1.0, "sorgo": 0.6}  # demand factor for the estimate tables: no confirmed source
# Prices: CNA/Cepea Campo Futuro, average of MT and PR, 19/09/2025 ("CNA Insumos Agropecuários", ed. Set/25): SSP R$ 2,104.7/t and
# KCl R$ 2,898.8/t. The nutrient grades (SSP 18% P2O5, KCl 58% K2O) are assumed, not from that report.
PRICE_SOURCE = "CNA/Cepea Campo Futuro (média MT e PR) em 19/09/2025: SSP R$ 2.104,7/t e KCl R$ 2.898,8/t; teores 18% P2O5 e 58% K2O assumidos"
P2O5_PRICE_R_KG = 2104.7 / (1000.0 * 0.18)
K2O_PRICE_R_KG = 2898.8 / (1000.0 * 0.58)

# Organic matter (optional): Corg classes of the Manual PR Quadro 4 (g/dm3): MB < 4, B 4-8, M 9-14, A 15-20, MA > 20; MO = Corg x 1.72
# (PR.0420, section 5.3). Decimals between published integers go to the lower class, as for P/K. The API takes MO (%) or C (g/kg);
# the report unit is g/dm3 and we read g/kg as g/dm3 (no density correction: premise, stated in the card).
CORG_CLASSES = [(4.0, "muito_baixo"), (9.0, "baixo"), (15.0, "medio"), (_NEXT(20.0, _INF), "alto"), (_INF, "muito_alto")]
MO_FACTOR = 1.72
LOW = ("muito_baixo", "baixo")

# C) fertility and organic-matter effects on the `solo` criterion
# Same scheme as the area problems: the literature gives the direction (which crop helps or hurts under that soil condition), the
# magnitude is the declared LEVEL_MAGNITUDE (our modelling choice). Condition -> target -> dict(level, sources, motive, caveat).
# A non-neutral cell needs at least one source (a test enforces it). "acidez" is graded by severity (1 = half, 2 = full magnitude).
FERTILITY_EFFECTS: dict[str, dict[str, dict]] = {
    "acidez": {  # Al or V% outside the target (severity > 0)
        **{f"segunda:{k}": dict(level="penaliza", sources=["pr0404"],
                                motive=Msg("{0} está na classe de tolerância à acidez 'baixa' do Manual PR (V% alvo 51–70%)", n),
                                caveat="a calagem corrige; o custo dela entra na margem")
           for k, n in (("milho_safrinha", "o milho"), ("milho_braquiaria", "o milho"), ("trigo", "o trigo"),
                        ("feijao_safrinha", "o feijão"), ("sorgo", "o sorgo"), ("soja_safrinha", "a soja"))},
    },
    "pk_baixo": {  # P or K in the low classes
        "segunda:milho_braquiaria": dict(level="favorece", sources=["resende2021", "betta2008"],
                                         motive="a braquiária recicla K e P de camadas profundas: até 40 kg/ha de K2O a mais na camada 0–5 cm "
                                                "para a cultura seguinte (Resende et al.); palhada com P e K equivalentes à adubação regional (Betta et al.)",
                                         caveat="ensaios no Cerrado (MG/GO); recicla o que está no perfil, não repõe o que falta"),
        "segunda:nabo_forrageiro": dict(level="favorece", sources=["viola2013"],
                                        motive="o nabo forrageiro acumulou das maiores quantidades de K, P e N e as liberou rápido para o trigo (Pato Branco-PR)",
                                        caveat="recicla o que está no perfil, não repõe o que falta"),
    },
    "mo_baixa": {  # organic carbon in the low classes
        "segunda:milho_braquiaria": dict(level="favorece", sources=["resende2021"],
                                         motive="plantio direto com braquiária aumentou a matéria orgânica na camada superficial após 9 anos",
                                         caveat="efeito de longo prazo: um ciclo de braquiária não mudou a MO no ensaio"),
        "segunda:milheto_crotalaria": dict(level="favorece", sources=["bertin2005", "resende2021"],
                                           motive="o milheto foi a cobertura de maior fitomassa e gramíneas (alta relação C/N) mantêm mais MO; "
                                                  "aumentar a MO exige alto aporte de palhada",
                                           caveat="sem medição de MO no consórcio; efeito de anos, não de uma safra"),
        "segunda:pousio": dict(level="penaliza", sources=["resende2021"],
                               motive="sem aporte de palhada na 2ª janela; o aumento de MO no plantio direto exige diversificação e elevado aporte de resíduos",
                               caveat="inferência a partir da fonte (ela não mediu pousio)"),
    },
}
FERTILITY_LABEL = {"acidez": "solo ácido", "pk_baixo": "P ou K baixos", "mo_baixa": "matéria orgânica baixa"}
FERTILITY_NEUTRAL_NO_SOURCE: dict[tuple[str, str], str] = {
    ("pk_baixo", "segunda:aveia_nabo"): "o nabo recicla K e P (Viola et al. 2013), mas não há fonte para o mix aveia + nabo",
    ("pk_baixo", "segunda:milheto_crotalaria"): "o milheto recicla nutrientes, mas não achamos fonte de P/K para o consórcio",
    ("mo_baixa", "segunda:aveia_nabo"): "não achamos fonte de efeito na MO para o mix aveia + nabo",
}


def prepare_fertility(f: dict | None, clay_pct: float | None = None, corg_g_dm3: float | None = None) -> dict | None:
    """Interprets the informed fertility (dict with a subset of FERTILITY_FIELDS, already validated) into classes.
    `clay_pct` (the farmer's clay %, optional) selects the P table by clay band; `corg_g_dm3` (organic carbon from the farmer's
    report, optional) gets the Corg class. None if nothing was informed.
    Nothing is estimated: V% is only derived when Ca, Mg, K and CEC come together (V = (Ca+Mg+K)/CEC)."""
    f = {k: float(v) for k, v in (f or {}).items() if k in FERTILITY_FIELDS and v is not None}
    if not f and corg_g_dm3 is None:
        return None
    v_source = "informada" if "v_pct" in f else None
    if v_source is None and all(k in f for k in ("ca_cmolc_dm3", "mg_cmolc_dm3", "k_cmolc_dm3", "ctc_cmolc_dm3")) and f["ctc_cmolc_dm3"] > 0:
        f["v_pct"] = min(100.0, 100 * (f["ca_cmolc_dm3"] + f["mg_cmolc_dm3"] + f["k_cmolc_dm3"]) / f["ctc_cmolc_dm3"])
        v_source = "derivada de (Ca+Mg+K)/CTC"
    band, band_source = clay_band(clay_pct)
    classes = {}
    if "p_mg_dm3" in f: classes["p"] = _p_class(f["p_mg_dm3"], band)
    if "k_cmolc_dm3" in f: classes["k"] = _classify(f["k_cmolc_dm3"], CLASSES["k"])
    if "v_pct" in f: classes["v"] = "condicao_evitar" if f["v_pct"] > V_AVOID_ABOVE else _classify(f["v_pct"], CLASSES["v"])
    if "al_cmolc_dm3" in f: classes["al"] = _classify(f["al_cmolc_dm3"], CLASSES["al"])
    if corg_g_dm3 is not None:
        classes["mo"] = _classify(float(corg_g_dm3), CORG_CLASSES)
    sev = max([{"muito_baixo": 0, "baixo": 0, "medio": 1, "alto": 2, "muito_alto": 2}[classes["al"]] if "al" in classes else 0,
               {"muito_baixo": 2, "baixo": 2, "medio": 1}.get(classes.get("v"), 0)])
    pk_low = classes.get("p") in LOW or classes.get("k") in LOW
    mo_low = classes.get("mo") in LOW
    return dict(valores=f, classes=classes, v_origem=v_source, severidade_acidez=sev, pk_baixo=pk_low, mo_baixa=mo_low,
                corg_g_dm3=None if corg_g_dm3 is None else float(corg_g_dm3),
                pobre=pk_low or sev > 0 or mo_low, informados=[k for k in FERTILITY_FIELDS if k in f],
                ausentes=[k for k in FERTILITY_FIELDS if k not in f],
                argila_faixa_g_kg=band if "p" in classes else None, argila_origem=band_source if "p" in classes else None)


def _nc_t_ha(fert: dict, v2: float) -> float | None:
    """Liming requirement (t/ha of limestone at the reference PRNT); None if V% or CEC is missing (nothing is estimated)."""
    v, ctc = fert["valores"].get("v_pct"), fert["valores"].get("ctc_cmolc_dm3")
    if v is None or ctc is None:
        return None
    return min(NC_MAX_T_HA, max(0.0, (v2 - v) / 100.0 * ctc / PRNT))


def _midpoint_dose(value: float, table: list[tuple[float, float]]) -> float:
    return next(d for lim, d in table if value < lim)


def _dose_delta(sec_: str, fert: dict) -> tuple[float, float, list[str], str] | None:
    """(extra kg P2O5/ha, extra kg K2O/ha, text parts, source) of the 2nd-window crop vs the assumed 'medio' reference; None if no dose model."""
    cl, v = fert["classes"], fert["valores"]
    if sec_ in ("milho_safrinha", "milho_braquiaria"):
        dp = (DOSE_P2O5_CORN[cl["p"]] - DOSE_P2O5_CORN["medio"]) if "p" in cl else None
        dk = (DOSE_K2O_CORN[cl["k"]] - DOSE_K2O_CORN["medio"]) if "k" in cl else None
        src = CORN_DOSE_SOURCE
    elif sec_ == "trigo":
        dp = (_midpoint_dose(v["p_mg_dm3"], WHEAT_P2O5) - WHEAT_BASELINE["p2o5"]) if "p_mg_dm3" in v else None
        dk = (_midpoint_dose(v["k_cmolc_dm3"], WHEAT_K2O) - WHEAT_BASELINE["k2o"]) if "k_cmolc_dm3" in v else None
        src = WHEAT_DOSE_SOURCE
    elif sec_ in PK_DEMAND:
        ex = PK_DEMAND[sec_]
        dp = (P2O5_DOSE_ESTIMATE[cl["p"]] - P2O5_DOSE_ESTIMATE["medio"]) * ex if "p" in cl else None
        dk = (K2O_DOSE_ESTIMATE[cl["k"]] - K2O_DOSE_ESTIMATE["medio"]) * ex if "k" in cl else None
        src = Msg("doses {0} ({1})", _NO_SOURCE, ESTIMATE_SOURCE)
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


def costs(c: dict, state: dict | None) -> list[dict]:
    """Extra cost items from fertility (liming and P/K fertilization) in the `extras_custo` format. [] without fertility."""
    fert = (state or {}).get("fert")
    if not fert:
        return []
    out, sec_ = [], c["segunda"]
    v2 = V2.get(sec_, V2_AREA)
    nc = _nc_t_ha(fert, v2)
    if nc:
        annual_value = nc * LIME_R_T / LIMING_YEARS
        area_note = "" if sec_ in V2 else ("; calagem é necessidade da área e também é cobrada em cobertura/pousio, para não favorecê-las "
                                          "(premissa de modelagem, validar com agrônomo)")
        out.append(dict(chave="calagem", rotulo="Calagem", custo=annual_value,
                        detalhe=f"NC = ({v2:g} − V% {fert['valores']['v_pct']:.0f})/100 × CTC {fert['valores']['ctc_cmolc_dm3']:g} / PRNT "
                                f"{PRNT:.0%} = {nc:.1f} t/ha × R$ {LIME_R_T:g}/t, diluída em {LIMING_YEARS} anos; fórmula do Manual PR "
                                f"(SENAR-AR/PR PR.0404) com PRNT de referência da {PRNT_SOURCE}; V2: {V2_SHORT_SOURCE}; "
                                f"preço do calcário, teto de 6 t/ha e diluição em 3 anos: {ESTIMATE_SOURCE}{area_note}"))
    dd = _dose_delta(sec_, fert)
    if dd:
        dp, dk, parts, src = dd
        delta = dp * P2O5_PRICE_R_KG + dk * K2O_PRICE_R_KG
        out.append(dict(chave="adubacao_pk", rotulo="Adubação P/K acima/abaixo da referência" if delta >= 0 else "Economia de adubação P/K",
                        custo=delta, detalhe=Msg("{0} em relação à classe média, que ASSUMIMOS embutida no custo CONAB (premissa "
                                                 "sem fonte); doses: {1}; preços: {2}", Join(parts, ", "), src, PRICE_SOURCE)))
    return out


def fertility_conditions(fert: dict | None) -> dict[str, float]:
    """Active soil conditions of the informed fertility -> weight (acidity: severity/2; the others: 1)."""
    if not fert:
        return {}
    out = {}
    if fert.get("severidade_acidez"):
        out["acidez"] = fert["severidade_acidez"] / 2.0
    if fert.get("pk_baixo"):
        out["pk_baixo"] = 1.0
    if fert.get("mo_baixa"):
        out["mo_baixa"] = 1.0
    return out


def _cond_detail(cond: str, fert: dict) -> str:
    cl = fert["classes"]
    if cond == "acidez":
        return Msg("Al {0}, V% {1}; severidade {2} de 2", cl.get("al", "n/i").replace("_", " "), cl.get("v", "n/i").replace("_", " "),
                   str(fert["severidade_acidez"]))
    if cond == "pk_baixo":
        return Msg("P {0}, K {1}", cl.get("p", "n/i").replace("_", " "), cl.get("k", "n/i").replace("_", " "))
    corg, mo = f"{fert['corg_g_dm3']:.1f}".replace(".", ","), f"{fert['corg_g_dm3'] * MO_FACTOR / 10:.1f}".replace(".", ",")
    return Msg("C orgânico {0} g/dm³ (MO ~{1}%), classe {2}", corg, mo, cl["mo"].replace("_", " "))


def _fertility_effects(c: dict, fert: dict) -> list[dict]:
    keys = _target_keys(c)
    out = []
    for cond, wgt in fertility_conditions(fert).items():
        for target, e in FERTILITY_EFFECTS[cond].items():
            if target in keys and e["level"] != "neutro":
                out.append(dict(origem=Msg("fertilidade: {0}", FERTILITY_LABEL[cond]), condicao=cond, problema=None, alvo=target,
                                nivel=e["level"], criterio="solo", delta=LEVEL_DELTA[e["level"]] * wgt,
                                motivo=Msg("{0} ({1})", e["motive"], _cond_detail(cond, fert)), ressalva=e.get("caveat"),
                                fontes=[SOURCES[x]["label"] for x in e["sources"]]))
    return out


def _fertility_unsourced_neutrals(c: dict, fert: dict) -> list[str]:
    keys, conds = _target_keys(c), fertility_conditions(fert)
    return [Msg("{0} × {1}: efeito sem fonte confirmada, tratado como neutro ({2})", FERTILITY_LABEL[k],
                t.split(":")[-1].replace("_", " "), why)
            for (k, t), why in FERTILITY_NEUTRAL_NO_SOURCE.items() if k in conds and t in keys]


def soft_add(base: float, delta: float) -> float:
    """Adds `delta` to a 0-1 score without saturating: slope 1 at delta = 0 and the result approaches 1 (or 0) exponentially,
    so two options with different adjustments never tie at the bound (the same reason the income score uses tanh).
    No extra parameter: the gap to the bound is the scale. delta = 0 returns `base` unchanged."""
    base = min(1.0, max(0.0, float(base)))
    if delta > 0 and base < 1.0:
        return 1.0 - (1.0 - base) * math.exp(-delta / (1.0 - base))
    if delta < 0 and base > 0.0:
        return base * math.exp(delta / base)
    return base


def adjustment(c: dict, state: dict | None) -> dict:
    """Additive deltas on the candidate's criteria: {"pragas": x, "solo": y, "efeitos": [dict(origem, criterio, delta, motivo, ...)]}.
    Without state (nothing informed) it returns zeros and no effects."""
    out = dict(pragas=0.0, solo=0.0, efeitos=[])
    if not state:
        return out
    for e in _problem_effects(c, state.get("problemas") or ()):
        out[e["criterio"]] += e["delta"]
        out["efeitos"].append(dict(e, origem=f"problema da área: {PROBLEM_LABELS[e['problema']]}"))
    fert = state.get("fert")
    if fert:
        for e in _fertility_effects(c, fert):
            out["solo"] += e["delta"]
            out["efeitos"].append(e)
    return out


# D) cost of recovering the soil with each option (shown on the card; never enters the score twice)
K_CREDIT_BRACHIARIA_KG = 40.0  # "até 40 kg/ha de K2O" in the 0-5 cm layer after one brachiaria cycle (Resende et al. 2021)


def _brl(x: float) -> str:
    return f"{x:,.0f}".replace(",", ".")


def recovery(c: dict, state: dict | None, margin: dict | None, best: tuple[str, float] | None) -> dict | None:
    """What it costs to recover the informed soil with this option: liming of the area (total, once; the margin only carries
    1/LIMING_YEARS of it per year), the extra P/K of this crop (per year, already in the margin), and the income given up against the
    option with the highest incremental income (`best` = (name, incremental R$/ha)). For brachiaria on low K, the sourced K credit is
    shown as an upper bound, not subtracted. None when the farmer gave no fertility, or the soil needs no recovery."""
    fert = (state or {}).get("fert")
    if not fert:
        return None
    nc = _nc_t_ha(fert, V2_AREA)
    if not (fert["pobre"] or nc):
        return None
    lime = (nc or 0.0) * LIME_R_T
    pk = sum(i["custo"] for i in costs(c, state) if i["chave"] == "adubacao_pk")
    inc = None if margin is None else float(margin["incremental"])
    gap = None if (inc is None or best is None) else max(0.0, best[1] - inc)
    credit = (K_CREDIT_BRACHIARIA_KG * K2O_PRICE_R_KG if c["segunda"] == "milho_braquiaria" and fert["pk_baixo"] else None)
    total = lime + max(0.0, pk) + (gap or 0.0)
    parts = []
    if nc:
        parts.append(Msg("calagem R$ {0}/ha uma vez ({1} t/ha; a margem cobra 1/{2} por ano)", _brl(lime),
                         f"{nc:.1f}".replace(".", ","), str(LIMING_YEARS)))
    if pk > 0:
        parts.append(Msg("adubação P/K extra R$ {0}/ha/ano", _brl(pk)))
    if gap:
        parts.append(Msg("renda que deixa de ganhar frente a {0} R$ {1}/ha", best[0], _brl(gap)))
    what = Join(parts, " + ") if parts else "sem custo direto além da cultura"
    tail = []
    if credit:
        tail.append(Msg("crédito possível de até R$ {0}/ha em K2O reciclado pela braquiária (Resende et al. 2021, camada 0–5 cm)",
                        _brl(credit)))
    if fert["mo_baixa"]:
        tail.append("a matéria orgânica sobe em anos de palhada, não em uma safra")
    head = Msg("Recuperar o solo com esta opção: {0} ≈ R$ {1}/ha no 1º ano", what, _brl(total))
    txt = Msg("{0}.", Join([head, *tail], "; "))
    return dict(calagem_total_r_ha=lime, calagem_t_ha=nc, adubacao_pk_r_ha_ano=pk, renda_abdicada_r_ha=gap,
                referencia_renda=None if best is None else best[0], credito_k2o_ate_r_ha=credit, total_primeiro_ano_r_ha=total, texto=txt)


# Texts (card and methodology)
def _fert_txt(fert: dict) -> str:
    rot = {"p_mg_dm3": "P", "k_cmolc_dm3": "K", "ca_cmolc_dm3": "Ca", "mg_cmolc_dm3": "Mg", "al_cmolc_dm3": "Al", "v_pct": "V%",
           "ctc_cmolc_dm3": "CTC"}
    v = fert["valores"]
    return ", ".join(f"{rot[k]} {v[k]:g}" for k in fert["informados"]) + (
        f"; V% {v['v_pct']:.0f} {fert['v_origem']}" if fert["v_origem"] and fert["v_origem"] != "informada" else "")


def _short_scale_txt() -> str:
    return f"±{LEVEL_MAGNITUDE:g}, metade para acidez de severidade 1"


def _scale_txt() -> str:
    return (f"favorece +{LEVEL_MAGNITUDE:g}, penaliza −{LEVEL_MAGNITUDE:g} no critério (a direção vem da literatura; a magnitude "
            f"é escolha de modelagem nossa)")


def card(c: dict, state: dict | None) -> dict:
    """Card lines of the candidate: `evidencias`, `lacunas` (what was not considered) and `revisar`."""
    est = state or {}
    probs, fert = est.get("problemas") or [], est.get("fert")
    ev, gap, rev = [], [], []
    aj = adjustment(c, state)
    if probs:
        labels = ", ".join(PROBLEM_LABELS[p] for p in probs)
        gap.append(f"Problemas da área considerados: {labels} (efeito por cultura em três níveis: {_scale_txt()}).")
        efs = [e for e in aj["efeitos"] if e["problema"]]
        for e in efs:
            caveat = f"; ressalva: {e['ressalva']}" if e["ressalva"] else ""
            ev.append(f"Problema da área ({PROBLEM_LABELS[e['problema']]}): {e['nivel']}, critério {e['criterio']} {e['delta']:+.2f} "
                      f"({e['motivo']}; fonte: {'; '.join(e['fontes'])}{caveat}).")
        if not efs:
            ev.append(f"Problemas da área informados ({labels}): sem efeito com fonte confirmada nesta rotação (neutro).")
        gap.extend(_unsourced_neutrals(c, probs))
    else:
        gap.append("Problemas da área (nematoide, mofo-branco, cigarrinha, compactação) não informados: não considerados.")
    if fert:
        if fert["informados"]:
            classes = ", ".join(f"{k.upper()} {v.replace('_', ' ')}" for k, v in fert["classes"].items() if k != "mo")
            ev.append(f"Fertilidade informada pelo produtor ({_fert_txt(fert)}); classes: {classes} ({MANUAL_SOURCE}).")
        if fert.get("argila_faixa_g_kg"):
            ev.append(f"Classe de P pela argila {fert['argila_faixa_g_kg']} g/kg ({fert['argila_origem']}).")
        if "mo" in fert["classes"]:
            ev.append(Msg("Matéria orgânica: {0} ({1}, Quadro 4; MO = C × 1,72).", _cond_detail("mo_baixa", fert),
                          SOURCES["manual_pr"]["label"]))
        for e in (x for x in aj["efeitos"] if x.get("condicao")):
            caveat = Msg("; ressalva: {0}", e["ressalva"]) if e["ressalva"] else ""
            ev.append(Msg("Solo ({0}): {1}, critério solo {2} ({3}; fonte: {4}{5}).", FERTILITY_LABEL[e["condicao"]], e["nivel"],
                          f"{e['delta']:+.2f}", e["motivo"], Join(e["fontes"], "; "), caveat))
        gap.extend(_fertility_unsourced_neutrals(c, fert))
        for it in costs(c, state):
            ev.append(Msg("Fertilidade: {0} {1}R$ {2}/ha/ano ({3}).", it["rotulo"], "+" if it["custo"] >= 0 else "−",
                          f"{abs(it['custo']):.0f}", it["detalhe"]))
        if _nc_t_ha(fert, V2.get(c["segunda"], V2_AREA)) is None:
            gap.append("Calagem não calculada: faltam V% (ou Ca+Mg+K+CTC) e CTC informados; nada foi estimado.")
        if "mo" in fert["classes"]:
            gap.append("C orgânico lido em g/dm³ (unidade do laudo) a partir de g/kg ou MO %, sem correção de densidade (premissa).")
        if fert["ausentes"]:
            gap.append(f"Fertilidade parcial: não informados {', '.join(fert['ausentes'])}; esses itens não entram na análise.")
        if fert.get("argila_faixa_g_kg") and not fert["argila_origem"].startswith("informada"):
            gap.append("Argila não informada: a classe de P usou a faixa mais exigente do Manual PR (< 250 g/kg); informe argila_pct para a classe correta.")
        if c["segunda"] in PK_DEMAND:
            gap.append(f"Doses de P2O5/K2O de {c['segunda'].replace('_', ' ')}: {_NO_SOURCE} ({ESTIMATE_SOURCE}).")
        gap.append(f"Fertilidade: classes e fórmula de calagem confirmadas no Manual PR; {V2_SOURCE}. Preço do calcário, teto de dose e "
                   f"diluição da calagem: {ESTIMATE_SOURCE}. Efeitos no critério solo: direção com fonte, tamanho ({_short_scale_txt()}) "
                   "é escolha de modelagem nossa. "
                   "Calagem e adubação da cultura de verão não entram (iguais em todas as rotações do bloco).")
        rev.append("Fertilidade: confirmar doses de calagem e adubação com o agrônomo e o laudo completo.")
    else:
        gap.append("Fertilidade e matéria orgânica não consideradas (não informadas): sem custo de adubação/calagem e sem efeito no critério solo.")
    return dict(evidencias=ev, lacunas=gap, revisar=rev)


def applied_adjustments(state: dict | None, analysis_given: bool) -> list[str]:
    """Sentences for `metodologia.ajustes_aplicados` about the field state. Empty if the farmer informed neither problems nor soil
    analysis (the response stays identical to the previous one; the card already says what was not considered)."""
    est = state or {}
    probs, fert = est.get("problemas") or [], est.get("fert")
    if not (probs or fert or analysis_given):
        return []
    o = []
    if probs:
        labels = ", ".join(PROBLEM_LABELS[p] for p in probs)
        o.append(f"Problemas da área informados pelo produtor ({labels}) ajustam os critérios pragas e solo por cultura em três níveis "
                 f"(favorece/neutro/penaliza; {_scale_txt()}). Só há efeito onde existe fonte lida (Embrapa/artigos, listadas em "
                 "docs/fontes_estado_area.md); sem fonte, o efeito é neutro.")
    else:
        o.append("Problemas da área não informados: não considerados.")
    if fert and not fert["informados"]:  # only organic matter was informed
        o.append(Msg("Matéria orgânica informada pelo produtor: classe de C orgânico do Manual PR (Quadro 4), classe {0}; matéria "
                     "orgânica baixa favorece braquiária e milheto e penaliza o pousio no critério solo (fonte lida, tamanho ±{1}, "
                     "escolha de modelagem). Sem P, K, V%, Al e CTC: calagem e adubação não entram.",
                     fert["classes"]["mo"].replace("_", " "), f"{LEVEL_MAGNITUDE:g}"))
    elif fert:
        given = fert["informados"] + (["carbono_organico"] if "mo" in fert["classes"] else [])
        o.append(Msg("Fertilidade informada pelo produtor ({0}): classes de P (por argila), K, V% e Al do Manual de "
                     "Adubação e Calagem do Paraná; custo de calagem (saturação por bases, fórmula do Manual) e de adubação P/K por cultura na "
                     "margem (doses do Manual PR para o milho e da CBPTT 2020 para o trigo; feijão e sorgo {1}); no critério solo, "
                     "solo ácido penaliza as culturas de baixa tolerância à acidez (Manual PR), P/K baixos favorecem braquiária e nabo "
                     "(recicladores) e matéria orgânica baixa (classes de C do Manual PR) favorece braquiária e milheto e penaliza o pousio, "
                     "com fonte lida (docs/fontes_estado_area.md) e tamanho ±{2} (escolha de modelagem); os ajustes se somam sem saturar a "
                     "nota; itens não informados não entram. Preço do calcário, teto de dose e diluição da calagem: {3}.",
                     Join(given, ", "), ESTIMATE_SOURCE, f"{LEVEL_MAGNITUDE:g}", ESTIMATE_SOURCE))
    else:
        o.append("Fertilidade não considerada (não informada).")
    return o
