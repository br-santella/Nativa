"""Rotation = (summer crop, second-window crop): calendar rules, corn after corn, `rotacoes`, old slugs, summer income.
Uses the real service and the data in data/ (run: uv run pytest tests/test_rotacoes.py)."""
import pytest

from field_shift.app import engine as E
from field_shift.motor import EntradaInvalida, opcoes, recomendar

T = {"talhao_id": "72638"}
SOJA_MILHO = {"verao": "soja", "segunda": "milho_safrinha"}


def _rec(**kw):
    kw.setdefault("incluir_diagnostico", False)
    kw.setdefault("rotacao_atual", "soja__milho_safrinha")
    return recomendar(T, **kw)


def _por_id(r):
    return {x["id"]: x for x in r["agora"]["ranking"] + r["proxima_safra"]["ranking"]}  # both blocks


def _elim(r):
    return {e["id"]: e["motivos"] for e in r["eliminadas"]}


# --------------------------------------------------------------------------- calendar and legal rules
@pytest.mark.parametrize("sem", E.SEMEADURAS)
def test_soja_na_segunda_janela_sempre_eliminada(sem):
    el = _elim(_rec(semeadura_safrinha=sem))
    assert any("Soybean after soybean" in m for m in el["soja__soja_safrinha"])
    assert any("01/09–31/12" in m for m in el["soja__soja_safrinha"])
    # after summer corn it is not soybean after soybean, but the legal soybean sowing window still applies
    assert not any("Soybean after soybean" in m for m in el["milho_verao__soja_safrinha"])
    assert any("01/09–31/12" in m for m in el["milho_verao__soja_safrinha"])
    assert any("soybean-free period" in m for m in el["milho_verao__soja_safrinha"])


def test_colheita_do_milho_verao_limita_a_segunda_cultura():
    r = _rec(semeadura_safrinha="01/02")
    el = _elim(r)
    for seg in ("milho_safrinha", "milho_braquiaria", "milheto_crotalaria", "sorgo", "feijao_safrinha"):
        assert any("summer corn harvest" in m and "01/02" in m for m in el[f"milho_verao__{seg}"]), seg
    # wheat, oat, radish and fallow have a fixed date: they do not depend on the summer harvest
    ids = _por_id(r)
    for seg in ("trigo", "aveia", "nabo_forrageiro", "aveia_nabo", "pousio"):
        assert f"milho_verao__{seg}" in ids, seg
    # (early) soybean allows every second-crop sowing date
    assert "soja__milho_safrinha" in ids
    ok = _por_id(_rec(semeadura_safrinha="01/03"))
    assert "milho_verao__milho_safrinha" in ok and "milho_verao__sorgo" in ok


def test_janela_do_feijao_safrinha():
    el = _elim(_rec(semeadura_safrinha="01/03"))
    assert any("outside the off-season beans window" in m for m in el["soja__feijao_safrinha"])
    assert "soja__feijao_safrinha" in _por_id(_rec(semeadura_safrinha="15/02"))
    assert "soja__sorgo" in _por_id(_rec(semeadura_safrinha="15/03"))


def test_semeaduras_validas_em_opcoes():
    c = {x["id"]: x for x in opcoes()["combinacoes"]}
    assert c["soja__soja_safrinha"]["valida"] is False and c["soja__soja_safrinha"]["semeaduras_validas"] == []
    assert c["milho_verao__soja_safrinha"]["valida"] is False
    assert c["milho_verao__milho_safrinha"]["semeaduras_validas"] == ["15/02", "01/03", "15/03"]
    assert c["soja__milho_safrinha"]["semeaduras_validas"] == E.SEMEADURAS
    assert c["soja__feijao_safrinha"]["semeaduras_validas"] == ["15/01", "01/02", "15/02"]
    assert c["soja__milho_safrinha"]["id_legado"] == "milho_safrinha" and "id_legado" not in c["soja__sorgo"]


# --------------------------------------------------------------------------- corn after corn
def test_milho_sobre_milho_penaliza_e_nao_elimina():
    r = _rec(semeadura_safrinha="01/03")
    ids = _por_id(r)
    mm, sm = ids["milho_verao__milho_safrinha"], ids["soja__milho_safrinha"]
    assert "milho_verao__milho_safrinha" not in _elim(r)
    assert sm["criterios"]["pragas"] == 0.5 and mm["criterios"]["pragas"] == pytest.approx(0.25)
    assert ids["milho_verao__milho_braquiaria"]["criterios"]["pragas"] == pytest.approx(0.40)
    assert any("cigarrinha" in x and "enfezamento" in x for x in mm["card"]["riscos"])
    assert any("0.25" in x and "cigarrinha" in x for x in mm["card"]["evidencias"])
    # other crops after summer corn do not get the penalty
    assert ids["milho_verao__sorgo"]["criterios"]["pragas"] == ids["soja__sorgo"]["criterios"]["pragas"]
    assert not any("cigarrinha" in x for x in ids["soja__milho_safrinha"]["card"]["riscos"])


# --------------------------------------------------------------------------- rotation benefit and summer income
def test_renda_do_milho_verao():
    r = _rec(semeadura_safrinha="01/03", rotacoes=[SOJA_MILHO, {"verao": "milho_verao", "segunda": "aveia"}, {"verao": "soja", "segunda": "aveia"}])
    ids = _por_id(r)
    mv, sa, sv = ids["milho_verao__aveia"]["margem"], ids["soja__aveia"]["margem"], ids["soja__milho_safrinha"]["margem"]
    soja, milho1 = sa["itens"][0], mv["itens"][0]
    assert soja["cultura"] == "Soybean" and milho1["cultura"] == "Summer corn (1st season)"
    assert "1st-season corn" not in milho1["fonte"] and "IBGE PAM" in milho1["fonte"] and "Ponta Grossa-PR" in milho1["fonte"]
    assert "SEAB/DERAL" in milho1["fonte"]
    # same scale S (municipal soybean margin): incomes comparable between a soybean and a corn summer
    assert mv["escala_S_r_ha"] == sa["escala_S_r_ha"] == sv["escala_S_r_ha"]
    # incremental = (summer corn − soybean) + oat + bonus (oat 2 + summer corn 3 bags/ha × soybean price)
    esperado = (milho1["margem_r_ha"] - soja["margem_r_ha"]) + (mv["itens"][1]["margem_r_ha"]) + mv["bonus_proxima_soja_r_ha"]
    assert mv["incremental_r_ha"] == pytest.approx(esperado, abs=2)
    assert mv["bonus_proxima_soja_r_ha"] - sa["bonus_proxima_soja_r_ha"] == pytest.approx(3.0 * 120.14, abs=2)  # +3 bags/ha from the catalog
    c = ids["milho_verao__aveia"]["card"]
    assert any("breaks the disease and nematode cycle" in b for b in c["beneficios"])
    assert any("Bonus on the following soybean: 5 bags/ha" in e for e in c["evidencias"])


def test_soja_no_verao_mantem_as_notas_antigas():
    todas = _rec(semeadura_safrinha="01/02")
    antigas = {x["id"]: x["nota"] for x in todas["ranking"] if "id_legado" in x}
    assert antigas == {f"soja__{k}": v for k, v in {"milho_braquiaria": 0.814, "milho_safrinha": 0.757, "milheto_crotalaria": 0.756,
                                                     "aveia": 0.698, "pousio": 0.547, "trigo": 0.466}.items()}


# --------------------------------------------------------------------------- new crops
def test_culturas_novas_tem_agua_renda_e_fonte():
    r = _rec(semeadura_safrinha="15/02")
    ids = _por_id(r)
    for seg in ("sorgo", "feijao_safrinha", "nabo_forrageiro", "aveia_nabo"):
        x = ids[f"soja__{seg}"]
        assert 0 < x["criterios"]["agua"] <= 1 and 0 <= x["criterios"]["renda"] <= 1
        assert any(e.startswith("Water: in the critical phase") for e in x["card"]["evidencias"]), seg
    sorgo = ids["soja__sorgo"]["margem"]["itens"][1]
    assert sorgo["cultura"] == "Sorghum" and "estimate — to be validated" in sorgo["fonte"] and sorgo["rendimento_sc_ha"] > 0
    feijao = ids["soja__feijao_safrinha"]["margem"]["itens"][1]
    assert "SEAB/DERAL" in feijao["fonte"] and "Francisco Beltrão" in feijao["fonte"]
    for seg in ("nabo_forrageiro", "aveia_nabo"):  # cover: income = −cost
        item = ids[f"soja__{seg}"]["margem"]["itens"][1]
        assert item["rendimento_sc_ha"] is None and item["margem_r_ha"] < 0 and "estimativa" in item["fonte"]


def test_culturas_novas_nas_entradas_do_produtor():
    r = _rec(semeadura_safrinha="15/02", ajustes={"precos": {"sorgo": 60, "feijao": 250}, "custos": {"sorgo": 2000, "feijao": 4000, "milho_verao": 6000},
                                                  "produtividade": {"sorgo": 70, "feijao": 30, "milho_verao": 160}},
             rotacoes=[{"verao": "milho_verao", "segunda": "sorgo"}, {"verao": "soja", "segunda": "feijao_safrinha"}])
    ids = _por_id(r)
    assert ids["milho_verao__sorgo"]["margem"]["itens"][0]["rendimento_sc_ha"] == 160
    assert ids["milho_verao__sorgo"]["margem"]["itens"][1]["margem_r_ha"] == 70 * 60 - 2000
    assert ids["soja__feijao_safrinha"]["margem"]["itens"][1]["margem_r_ha"] == 30 * 250 - 4000
    with pytest.raises(EntradaInvalida):
        _rec(ajustes={"produtividade": {"milho_verao": 100, "milho_1safra": 100}})


def test_sem_comprador_de_sorgo_e_feijao():
    el = _elim(_rec(semeadura_safrinha="15/02", restricoes={"sem_comprador": ["sorgo", "feijao"]}))
    assert "No local buyer, as reported by the farmer (sorgo)" in el["soja__sorgo"][0]
    assert "No local buyer, as reported by the farmer (feijao)" in el["milho_verao__feijao_safrinha"][0]


# --------------------------------------------------------------------------- rotacoes
def test_rotacoes_avalia_so_as_pedidas():
    pedidas = [{"verao": "milho_verao", "segunda": "aveia_nabo"}, SOJA_MILHO, {"verao": "soja", "segunda": "sorgo"},
               {"verao": "soja", "segunda": "soja_safrinha"}, {"verao": "milho_verao", "segunda": "milho_safrinha"}]
    r = _rec(rotacoes=pedidas)  # default sowing 01/02: summer corn → off-season corn is eliminated by the harvest
    assert set(_por_id(r)) == {"milho_verao__aveia_nabo", "soja__milho_safrinha", "soja__sorgo"}
    assert set(_elim(r)) == {"soja__soja_safrinha", "milho_verao__milho_safrinha"}  # eliminated = result, not an error
    assert r["entrada"]["rotacoes"] == pedidas
    assert r["atual"]["id"] == "soja__milho_safrinha" and r["atual"]["atual"]
    # the score does not depend on the other rotations evaluated
    todas = _por_id(_rec())
    assert {k: v["nota"] for k, v in _por_id(r).items()} == {k: todas[k]["nota"] for k in _por_id(r)}
    # without `rotacoes`, the whole catalog is evaluated
    assert len(todas) + len(_elim(_rec())) == len(E.CATALOGO) == 22
    assert "rotacoes" not in _rec()["entrada"]


def test_rotacoes_so_eliminadas_nao_e_erro():
    r = _rec(rotacoes=[{"verao": "soja", "segunda": "soja_safrinha"}], rotacao_atual="milho_verao__aveia")
    assert r["ranking"] == [] and r["alternativas"] == [] and set(_elim(r)) == {"soja__soja_safrinha"}
    assert r["atual"]["avaliada"] is False and any("eliminadas" in a for a in r["avisos"])


def test_rotacoes_atual_fora_da_selecao():
    r = _rec(rotacoes=[{"verao": "soja", "segunda": "sorgo"}], rotacao_atual="milho_safrinha")
    assert r["atual"]["id"] == "soja__milho_safrinha" and r["atual"]["avaliada"] is False
    assert [x["id"] for x in r["alternativas"]] == ["soja__sorgo"]
    assert "Compared with the current rotation" not in r["ranking"][0]["card"]["por_que"]


@pytest.mark.parametrize("rotacoes", [
    [], [SOJA_MILHO, SOJA_MILHO], [{"verao": "soja", "segunda": "girassol"}], [{"verao": "trigo", "segunda": "pousio"}],
    [{"verao": "soja"}], [{"verao": "soja", "segunda": "pousio", "x": 1}], ["soja__pousio"], "soja__pousio",
])
def test_rotacoes_invalidas(rotacoes):
    with pytest.raises(EntradaInvalida):
        _rec(rotacoes=rotacoes)


# --------------------------------------------------------------------------- old slugs and ids
def test_slugs_antigos_equivalem_aos_ids_novos():
    a = _rec(rotacao_atual="milho_safrinha", restricoes={"culturas_excluidas": ["trigo"]})
    b = _rec(rotacao_atual="soja__milho_safrinha", restricoes={"culturas_excluidas": ["soja__trigo"]})
    assert [(x["id"], x["nota"]) for x in a["ranking"]] == [(x["id"], x["nota"]) for x in b["ranking"]]
    assert a["entrada"]["rotacao_atual"] == "soja__milho_safrinha" == b["entrada"]["rotacao_atual"]
    assert {x["id"] for x in a["eliminadas"]} == {x["id"] for x in b["eliminadas"]}
    top = a["ranking"][0]
    assert top["id"] == "soja__milho_braquiaria" and top["id_legado"] == "milho_braquiaria"
    assert top["verao"] == {"id": "soja", "nome": "Soybean"} and top["segunda"] == {"id": "milho_braquiaria", "nome": "Off-season corn + brachiaria"}
    for ruim in ("milho", "soja__milho", "milho_verao__soja", "x__y"):
        with pytest.raises(EntradaInvalida):
            _rec(rotacao_atual=ruim)


def test_opcoes_culturas_e_combinacoes():
    o = opcoes()
    assert [c["id"] for c in o["culturas_verao"]] == ["soja", "milho_verao"]
    seg = {c["id"]: c for c in o["culturas_segunda"]}
    assert set(seg) == set(E.SEGUNDA) and len(seg) == 11
    assert seg["sorgo"]["tipo"] == "grão" and seg["aveia_nabo"]["tipo"] == "cobertura" and seg["nabo_forrageiro"]["tipo"] == "cobertura"
    assert all(c["nome"] and c["descricao_curta"] for c in [*o["culturas_verao"], *seg.values()])
    assert len(o["combinacoes"]) == 22 and {c["id"] for c in o["combinacoes"]} == set(E.NOME_DE)
    assert {r["id"] for r in o["rotacoes"]} == set(E.NOME_DE)
    fontes = {f["item"]: f for f in o["renda_referencia"]["fontes"]}
    assert fontes["price sorgo"]["estimativa"] is True and fontes["cost sorgo"]["estimativa"] is True
    assert fontes["price feijao"]["estimativa"] is False and "cost milho_1safra" in fontes
