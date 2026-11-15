"""Rotação = (cultura de verão, cultura da 2ª janela): regras de calendário, milho sobre milho, `rotacoes`, slugs antigos, renda do verão.
Usa o serviço real e os dados em data/ (rodar: uv run pytest tests/test_rotacoes.py)."""
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
    return {x["id"]: x for x in r["agora"]["ranking"] + r["proxima_safra"]["ranking"]}  # os dois blocos


def _elim(r):
    return {e["id"]: e["motivos"] for e in r["eliminadas"]}


# --------------------------------------------------------------------------- regras de calendário e legais
@pytest.mark.parametrize("sem", E.SEMEADURAS)
def test_soja_na_segunda_janela_sempre_eliminada(sem):
    el = _elim(_rec(semeadura_safrinha=sem))
    assert any("Soja sobre soja" in m for m in el["soja__soja_safrinha"])
    assert any("01/09–31/12" in m for m in el["soja__soja_safrinha"])
    # depois de milho verão não é soja sobre soja, mas a janela legal de semeadura da soja continua valendo
    assert not any("Soja sobre soja" in m for m in el["milho_verao__soja_safrinha"])
    assert any("01/09–31/12" in m for m in el["milho_verao__soja_safrinha"])
    assert any("vazio sanitário" in m for m in el["milho_verao__soja_safrinha"])


def test_colheita_do_milho_verao_limita_a_segunda_cultura():
    r = _rec(semeadura_safrinha="01/02")
    el = _elim(r)
    for seg in ("milho_safrinha", "milho_braquiaria", "milheto_crotalaria", "sorgo", "feijao_safrinha"):
        assert any("colheita de milho verão" in m and "01/02" in m for m in el[f"milho_verao__{seg}"]), seg
    # trigo, aveia, nabo e pousio têm data fixa: não dependem da colheita do verão
    ids = _por_id(r)
    for seg in ("trigo", "aveia", "nabo_forrageiro", "aveia_nabo", "pousio"):
        assert f"milho_verao__{seg}" in ids, seg
    # a soja (precoce) libera todas as semeaduras da 2ª cultura
    assert "soja__milho_safrinha" in ids
    ok = _por_id(_rec(semeadura_safrinha="01/03"))
    assert "milho_verao__milho_safrinha" in ok and "milho_verao__sorgo" in ok


def test_janela_do_feijao_safrinha():
    el = _elim(_rec(semeadura_safrinha="01/03"))
    assert any("fora da janela de feijão safrinha" in m for m in el["soja__feijao_safrinha"])
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


# --------------------------------------------------------------------------- milho sobre milho
def test_milho_sobre_milho_penaliza_e_nao_elimina():
    r = _rec(semeadura_safrinha="01/03")
    ids = _por_id(r)
    mm, sm = ids["milho_verao__milho_safrinha"], ids["soja__milho_safrinha"]
    assert "milho_verao__milho_safrinha" not in _elim(r)
    assert sm["criterios"]["pragas"] == 0.5 and mm["criterios"]["pragas"] == pytest.approx(0.25)
    assert ids["milho_verao__milho_braquiaria"]["criterios"]["pragas"] == pytest.approx(0.40)
    assert any("cigarrinha" in x and "enfezamento" in x for x in mm["card"]["riscos"])
    assert any("0.25" in x and "cigarrinha" in x for x in mm["card"]["evidencias"])
    # outras culturas depois do milho verão não levam a penalidade
    assert ids["milho_verao__sorgo"]["criterios"]["pragas"] == ids["soja__sorgo"]["criterios"]["pragas"]
    assert not any("cigarrinha" in x for x in ids["soja__milho_safrinha"]["card"]["riscos"])


# --------------------------------------------------------------------------- benefício de rotação e renda do verão
def test_renda_do_milho_verao():
    r = _rec(semeadura_safrinha="01/03", rotacoes=[SOJA_MILHO, {"verao": "milho_verao", "segunda": "aveia"}, {"verao": "soja", "segunda": "aveia"}])
    ids = _por_id(r)
    mv, sa, sv = ids["milho_verao__aveia"]["margem"], ids["soja__aveia"]["margem"], ids["soja__milho_safrinha"]["margem"]
    soja, milho1 = sa["itens"][0], mv["itens"][0]
    assert soja["cultura"] == "Soja" and milho1["cultura"] == "Milho verão (1ª safra)"
    assert "milho 1ª safra" not in milho1["fonte"] and "IBGE PAM" in milho1["fonte"] and "Ponta Grossa-PR" in milho1["fonte"]
    assert "SEAB/DERAL" in milho1["fonte"]
    # mesma escala S (margem da soja do município): rendas comparáveis entre verão soja e milho verão
    assert mv["escala_S_r_ha"] == sa["escala_S_r_ha"] == sv["escala_S_r_ha"]
    # incremental = (milho verão − soja) + aveia + bônus (aveia 2 + milho verão 3 sc/ha × preço da soja)
    esperado = (milho1["margem_r_ha"] - soja["margem_r_ha"]) + (mv["itens"][1]["margem_r_ha"]) + mv["bonus_proxima_soja_r_ha"]
    assert mv["incremental_r_ha"] == pytest.approx(esperado, abs=2)
    assert mv["bonus_proxima_soja_r_ha"] - sa["bonus_proxima_soja_r_ha"] == pytest.approx(3.0 * 120.14, abs=2)  # +3 sc/ha de catálogo
    c = ids["milho_verao__aveia"]["card"]
    assert any("quebra ciclo de doença e nematoide" in b for b in c["beneficios"])
    assert any("Bônus na soja seguinte: 5 sc/ha" in e for e in c["evidencias"])


def test_soja_no_verao_mantem_as_notas_antigas():
    todas = _rec(semeadura_safrinha="01/02")
    antigas = {x["id"]: x["nota"] for x in todas["ranking"] if "id_legado" in x}
    assert antigas == {f"soja__{k}": v for k, v in {"milho_braquiaria": 0.821, "milho_safrinha": 0.774, "milheto_crotalaria": 0.757,
                                                     "aveia": 0.7, "pousio": 0.55, "trigo": 0.466}.items()}


# --------------------------------------------------------------------------- culturas novas
def test_culturas_novas_tem_agua_renda_e_fonte():
    r = _rec(semeadura_safrinha="15/02")
    ids = _por_id(r)
    for seg in ("sorgo", "feijao_safrinha", "nabo_forrageiro", "aveia_nabo"):
        x = ids[f"soja__{seg}"]
        assert 0 < x["criterios"]["agua"] <= 1 and 0 <= x["criterios"]["renda"] <= 1
        assert any(e.startswith("Água: na fase crítica") for e in x["card"]["evidencias"]), seg
    sorgo = ids["soja__sorgo"]["margem"]["itens"][1]
    assert sorgo["cultura"] == "Sorgo" and "estimativa — validar" in sorgo["fonte"] and sorgo["rendimento_sc_ha"] > 0
    feijao = ids["soja__feijao_safrinha"]["margem"]["itens"][1]
    assert "SEAB/DERAL" in feijao["fonte"] and "Francisco Beltrão" in feijao["fonte"]
    for seg in ("nabo_forrageiro", "aveia_nabo"):  # cobertura: renda = −custo
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
    assert "Sem comprador local informado pelo produtor (sorgo)" in el["soja__sorgo"][0]
    assert "Sem comprador local informado pelo produtor (feijao)" in el["milho_verao__feijao_safrinha"][0]


# --------------------------------------------------------------------------- rotacoes
def test_rotacoes_avalia_so_as_pedidas():
    pedidas = [{"verao": "milho_verao", "segunda": "aveia_nabo"}, SOJA_MILHO, {"verao": "soja", "segunda": "sorgo"},
               {"verao": "soja", "segunda": "soja_safrinha"}, {"verao": "milho_verao", "segunda": "milho_safrinha"}]
    r = _rec(rotacoes=pedidas)  # semeadura padrão 01/02: milho verão → milho safrinha cai pela colheita
    assert set(_por_id(r)) == {"milho_verao__aveia_nabo", "soja__milho_safrinha", "soja__sorgo"}
    assert set(_elim(r)) == {"soja__soja_safrinha", "milho_verao__milho_safrinha"}  # eliminada = resultado, não erro
    assert r["entrada"]["rotacoes"] == pedidas
    assert r["atual"]["id"] == "soja__milho_safrinha" and r["atual"]["atual"]
    # a nota não depende das outras rotações avaliadas
    todas = _por_id(_rec())
    assert {k: v["nota"] for k, v in _por_id(r).items()} == {k: todas[k]["nota"] for k in _por_id(r)}
    # sem `rotacoes`, tudo do catálogo é avaliado
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
    assert "Em relação à atual" not in r["ranking"][0]["card"]["por_que"]


@pytest.mark.parametrize("rotacoes", [
    [], [SOJA_MILHO, SOJA_MILHO], [{"verao": "soja", "segunda": "girassol"}], [{"verao": "trigo", "segunda": "pousio"}],
    [{"verao": "soja"}], [{"verao": "soja", "segunda": "pousio", "x": 1}], ["soja__pousio"], "soja__pousio",
])
def test_rotacoes_invalidas(rotacoes):
    with pytest.raises(EntradaInvalida):
        _rec(rotacoes=rotacoes)


# --------------------------------------------------------------------------- slugs antigos e ids
def test_slugs_antigos_equivalem_aos_ids_novos():
    a = _rec(rotacao_atual="milho_safrinha", restricoes={"culturas_excluidas": ["trigo"]})
    b = _rec(rotacao_atual="soja__milho_safrinha", restricoes={"culturas_excluidas": ["soja__trigo"]})
    assert [(x["id"], x["nota"]) for x in a["ranking"]] == [(x["id"], x["nota"]) for x in b["ranking"]]
    assert a["entrada"]["rotacao_atual"] == "soja__milho_safrinha" == b["entrada"]["rotacao_atual"]
    assert {x["id"] for x in a["eliminadas"]} == {x["id"] for x in b["eliminadas"]}
    top = a["ranking"][0]
    assert top["id"] == "soja__milho_braquiaria" and top["id_legado"] == "milho_braquiaria"
    assert top["verao"] == {"id": "soja", "nome": "Soja"} and top["segunda"] == {"id": "milho_braquiaria", "nome": "Milho safrinha + braquiária"}
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
    assert fontes["preço sorgo"]["estimativa"] is True and fontes["custo sorgo"]["estimativa"] is True
    assert fontes["preço feijao"]["estimativa"] is False and "custo milho_1safra" in fontes


def test_p20_never_above_mean():
    """Regression: the bad-year (p20) yield must not exceed the mean yield (same 10-year window for both)."""
    from field_shift.renda.renda import rendimentos
    for cod in ("4127700", "4104808", "4105805", "4115200"):  # Toledo, Cascavel, Corbelia, Marechal C. Rondon
        for cult, r in rendimentos(cod).items():
            if cult.startswith("_") or r["p20_sc_ha"] is None or r["sc_ha"] is None:
                continue
            assert r["p20_sc_ha"] <= r["sc_ha"], (cod, cult, r)
