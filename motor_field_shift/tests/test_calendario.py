"""Estágio da cultura de verão -> colheita estimada -> semeadura da 2ª janela; blocos `agora`/`proxima_safra`; `ganho_vs_atual`.
Usa o serviço real e os dados em data/ (rodar: uv run pytest tests/test_calendario.py)."""
from datetime import date

import pytest

from field_shift import calendario as cal
from field_shift.motor import EntradaInvalida, opcoes, recomendar

T = {"talhao_id": "72638"}
SOJA = "soja__milho_safrinha"
REF = "2026-12-01"


def _rec(**kw):
    kw.setdefault("incluir_diagnostico", False)
    kw.setdefault("rotacao_atual", SOJA)
    return recomendar(T, **kw)


def _ids(bloco):
    return [x["id"] for x in bloco["ranking"]]


def _elim(bloco):
    return {e["id"]: e["motivos"] for e in bloco["eliminadas"]}


# --------------------------------------------------------------------------- calendário puro
def test_dias_dos_estagios():
    assert [e["dias"] for e in cal.ESTAGIOS["soja"].values()] == [90, 65, 48, 32, 10, 0]
    assert list(cal.ESTAGIOS["milho_verao"]) == ["vegetativo", "pendoamento", "grao_leitoso", "grao_farinaceo", "maturacao", "colhida"]
    assert list(cal.ESTAGIOS["milho_verao"].values())[-1]["dias"] == 0


@pytest.mark.parametrize("estagio,ref,colheita,semeadura,tarde", [
    ("enchimento_graos", "2026-12-01", "02/01", "15/01", False),
    ("floracao", "2026-12-01", "04/02", "15/02", False),
    ("vegetativo", "2026-12-01", "01/03", "01/03", False),
    ("vegetativo", "2026-12-20", "20/03", None, True),   # depois da última semeadura (15/03)
    ("colhida", "2027-02-01", "01/02", "01/02", False),  # colhida: colheita = referência
    ("colhida", "2026-11-14", "14/11", "15/01", False),
])
def test_estagio_para_colheita_e_semeadura(estagio, ref, colheita, semeadura, tarde):
    r = cal.resolver("soja", estagio, None, date.fromisoformat(ref))
    assert (r["colheita"], r["semeadura_2a"], r["tarde_demais"], r["origem"]) == (colheita, semeadura, tarde, "estagio")


def test_precedencia_e_semeadura_informada():
    ref = date(2026, 12, 1)
    r = cal.resolver("soja", "vegetativo", "20/01", ref)  # colheita_prevista vence o estágio
    assert (r["origem"], r["colheita"], r["semeadura_2a"], r["dias_ate_colheita"]) == ("informada", "20/01", "01/02", 50)
    assert cal.resolver("soja", "enchimento_graos", None, ref, "01/03")["semeadura_2a"] == "01/03"  # informada vence a derivada
    assert cal.resolver("soja", None, None, ref) is None  # premissa
    with pytest.raises(ValueError, match="anterior à colheita"):
        cal.resolver("soja", "floracao", None, ref, "15/01")  # colheita ~04/02


@pytest.mark.parametrize("verao,estagio", [("soja", "pendoamento"), ("milho_verao", "enchimento_graos"), ("soja", "xyz")])
def test_estagio_incompativel(verao, estagio):
    with pytest.raises(ValueError, match="estagio_verao"):
        cal.resolver(verao, estagio, None, date(2026, 12, 1))


@pytest.mark.parametrize("x", ["2026-01-10", "31/02", "1/1", "x"])
def test_colheita_prevista_invalida(x):
    with pytest.raises(ValueError, match="colheita_prevista"):
        cal.resolver("soja", None, x, date(2026, 12, 1))


# --------------------------------------------------------------------------- exemplo principal
def test_soja_enchimento_graos_talhao_72638():
    r = _rec(estagio_verao="enchimento_graos", data_referencia=REF)
    assert r["cultura_atual"] == {"id": "soja", "nome": "Soja"}
    assert r["estagio_verao"]["id"] == "enchimento_graos" and r["estagio_verao"]["dias_tipicos_ate_colheita"] == 32
    assert "validar com Embrapa" in r["estagio_verao"]["fonte"]
    assert r["colheita_estimada"] == {"data": "02/01", "origem": "estagio"}
    assert r["semeadura_2a"] == {"data": "15/01", "origem": "derivada"} and r["dias_ate_colheita"] == 32
    assert r["entrada"]["semeadura_safrinha"] == "15/01" and r["entrada"]["data_referencia"] == REF
    assert not r["avisos"]
    # `agora`: só soja no verão; `proxima_safra`: só milho verão; ranking e alternativas são alias de `agora`
    assert all(i.startswith("soja__") for i in _ids(r["agora"])) and all(i.startswith("milho_verao__") for i in _ids(r["proxima_safra"]))
    assert r["ranking"] == r["agora"]["ranking"] and r["alternativas"] == r["agora"]["alternativas"]
    assert [x["posicao"] for x in r["agora"]["ranking"]] == list(range(1, len(r["agora"]["ranking"]) + 1))
    assert [x["posicao"] for x in r["proxima_safra"]["ranking"]][0] == 1
    assert r["atual"]["id"] == SOJA and r["atual"]["atual"] and r["atual"]["posicao"] is not None
    assert [x["id"] for x in r["eliminadas"]] == [x["id"] for x in r["agora"]["eliminadas"] + r["proxima_safra"]["eliminadas"]]
    assert "soja__soja_safrinha" in _elim(r["agora"])
    # com semeadura em 15/01 o milho verão (colheita típica 05/02) não libera milho safrinha na próxima safra
    assert any("colheita de milho verão" in m for m in _elim(r["proxima_safra"])["milho_verao__milho_safrinha"])


def test_ganho_vs_atual():
    r = _rec(estagio_verao="enchimento_graos", data_referencia=REF)
    por_id = {x["id"]: x for x in r["agora"]["ranking"] + r["proxima_safra"]["ranking"]}
    assert por_id[SOJA]["ganho_vs_atual"] is None  # a própria atual
    g = por_id["soja__milho_braquiaria"]["ganho_vs_atual"]
    assert g["comparado_com"] == SOJA
    assert g["soja_seguinte_sc"] == 2.0  # bônus 3,0 (milho + braquiária) − 1,0 (milho safrinha)
    assert g["soja_seguinte_sc_faixa"] == [2.0, 2.0]  # por enquanto faixa = valor central
    assert g["soja_seguinte_rs"] == pytest.approx(2.0 * g["preco_soja_r_sc"], abs=1)
    assert "validar com agrônomo/Embrapa" in g["fonte"]
    assert g["renda_2a_safra"]["origem"].startswith("dado:") and g["agua"]["origem"].startswith("dado:")
    assert g["solo"]["dias_descobertos"] == 30 - 60 and g["solo"]["cobertura"] == 0.3
    # mesmo verão: margem total = renda extra da 2ª safra + valor do bônus na soja seguinte
    assert g["margem_total"]["r_ha"] == pytest.approx(g["renda_2a_safra"]["r_ha"] + g["soja_seguinte_rs"], abs=2)
    # cobertura perde renda mas ganha solo; outro verão também traz ganho (milho verão: +3 sc/ha de bônus no verão)
    c = por_id["soja__aveia"]["ganho_vs_atual"]
    assert c["renda_2a_safra"]["r_ha"] < 0 and c["solo"]["dias_descobertos"] == 40 - 60 and c["soja_seguinte_sc"] == 1.0
    p = por_id["milho_verao__aveia"]["ganho_vs_atual"]
    assert p["soja_seguinte_sc"] == 4.0 and p["comparado_com"] == SOJA
    assert all(x["ganho_vs_atual"] for x in r["proxima_safra"]["ranking"])


def test_milho_verao_atual_usa_a_colheita_do_produtor():
    base = _rec(rotacao_atual="milho_verao__milho_safrinha", semeadura_safrinha="01/02")  # premissa: colheita 05/02 > 01/02
    assert any("05/02" in m for m in _elim(base["agora"])["milho_verao__milho_safrinha"])
    assert base["colheita_estimada"] == {"data": "05/02", "origem": "premissa"} and base["atual"]["eliminada"]
    r = _rec(rotacao_atual="milho_verao__milho_safrinha", estagio_verao="grao_leitoso", data_referencia=REF)  # 60 d -> 30/01
    assert r["colheita_estimada"]["data"] == "30/01" and r["semeadura_2a"]["data"] == "01/02"
    assert "milho_verao__milho_safrinha" in _ids(r["agora"]) and r["atual"]["posicao"] is not None
    assert all(i.startswith("milho_verao__") for i in _ids(r["agora"])) and all(i.startswith("soja__") for i in _ids(r["proxima_safra"]))
    assert r["cultura_atual"]["id"] == "milho_verao"


# --------------------------------------------------------------------------- colheita tarde demais
def test_colheita_tarde_demais_elimina_so_as_que_seguem_a_semeadura():
    r = _rec(estagio_verao="vegetativo", data_referencia="2026-12-20")  # colheita ~20/03
    assert r["colheita_estimada"] == {"data": "20/03", "origem": "estagio"} and r["semeadura_2a"] is None
    assert any("tarde demais para a safrinha" in a for a in r["avisos"])
    el = _elim(r["agora"])
    for seg in ("milho_safrinha", "milho_braquiaria", "sorgo", "feijao_safrinha", "milheto_crotalaria"):
        assert any("tarde demais para a safrinha" in m for m in el[f"soja__{seg}"]), seg
    assert {"trigo", "aveia", "nabo_forrageiro", "aveia_nabo", "pousio"} == {i.split("__")[1] for i in _ids(r["agora"])}
    assert r["atual"]["eliminada"] and r["atual"]["posicao"] is None and r["atual"]["nota"] is None
    assert all(x["ganho_vs_atual"] is None for x in r["agora"]["ranking"])  # sem a atual, nada a comparar


# --------------------------------------------------------------------------- precedência e entradas
def test_colheita_prevista_vence_o_estagio_e_semeadura_vence_a_derivada():
    r = _rec(estagio_verao="vegetativo", colheita_prevista="20/01", data_referencia=REF)
    assert r["colheita_estimada"] == {"data": "20/01", "origem": "informada"} and r["dias_ate_colheita"] == 50
    assert r["semeadura_2a"] == {"data": "01/02", "origem": "derivada"} and r["estagio_verao"]["id"] == "vegetativo"
    assert any("vale a colheita_prevista" in a for a in r["avisos"])
    r = _rec(estagio_verao="enchimento_graos", data_referencia=REF, semeadura_safrinha="01/03")
    assert r["semeadura_2a"] == {"data": "01/03", "origem": "informada"} and r["colheita_estimada"]["data"] == "02/01"
    assert r["entrada"]["semeadura_safrinha"] == "01/03" and any("01/03 informada" in a for a in r["avisos"])


def test_sem_estagio_nem_colheita_usa_a_premissa_e_avisa():
    r = _rec()
    assert r["colheita_estimada"] == {"data": "10/01", "origem": "premissa"} and r["dias_ate_colheita"] is None
    assert r["semeadura_2a"] == {"data": "01/02", "origem": "premissa"} and r["estagio_verao"] is None
    assert any("Sem estagio_verao nem colheita_prevista" in a and "premissa" in a for a in r["avisos"])
    r = _rec(semeadura_safrinha="15/02")
    assert r["semeadura_2a"] == {"data": "15/02", "origem": "informada"} and r["colheita_estimada"]["origem"] == "premissa"


def test_entradas_invalidas():
    with pytest.raises(EntradaInvalida, match="rotacao_atual"):
        recomendar(T, incluir_diagnostico=False)
    with pytest.raises(EntradaInvalida, match="estagio_verao"):
        _rec(estagio_verao="pendoamento")
    with pytest.raises(EntradaInvalida, match="anterior à colheita"):
        _rec(estagio_verao="floracao", data_referencia=REF, semeadura_safrinha="15/01")
    with pytest.raises(EntradaInvalida, match="anterior à colheita"):
        _rec(colheita_prevista="20/02", semeadura_safrinha="01/02")
    with pytest.raises(EntradaInvalida, match="data_referencia"):
        _rec(data_referencia="amanhã")
    with pytest.raises(EntradaInvalida, match="colheita_prevista"):
        _rec(colheita_prevista="2027-01-20")


# --------------------------------------------------------------------------- rotacoes distribuído nos blocos
def test_rotacoes_caem_no_bloco_certo():
    pedidas = [{"verao": "soja", "segunda": "milho_safrinha"}, {"verao": "soja", "segunda": "aveia"}, {"verao": "soja", "segunda": "soja_safrinha"},
               {"verao": "milho_verao", "segunda": "aveia_nabo"}, {"verao": "milho_verao", "segunda": "milho_safrinha"}]
    r = _rec(estagio_verao="enchimento_graos", data_referencia=REF, rotacoes=pedidas)
    assert set(_ids(r["agora"])) == {SOJA, "soja__aveia"} and set(_elim(r["agora"])) == {"soja__soja_safrinha"}
    assert _ids(r["proxima_safra"]) == ["milho_verao__aveia_nabo"] and set(_elim(r["proxima_safra"])) == {"milho_verao__milho_safrinha"}
    assert r["proxima_safra"]["ranking"][0]["ganho_vs_atual"]
    # atual fora de `rotacoes`: não aparece, mas o ganho continua sendo calculado contra ela
    r = _rec(estagio_verao="enchimento_graos", data_referencia=REF, rotacoes=[{"verao": "milho_verao", "segunda": "aveia_nabo"}])
    assert r["agora"]["ranking"] == [] and r["atual"]["avaliada"] is False
    assert r["proxima_safra"]["ranking"][0]["ganho_vs_atual"]["comparado_com"] == SOJA


# --------------------------------------------------------------------------- /v1/opcoes
def test_opcoes_estagios():
    o = {c["id"]: c for c in opcoes()["culturas_verao"]}
    assert [(e["id"], e["dias_ate_colheita"]) for e in o["soja"]["estagios"]] == [
        ("vegetativo", 90), ("floracao", 65), ("formacao_vagens", 48), ("enchimento_graos", 32), ("maturacao", 10), ("colhida", 0)]
    assert [e["id"] for e in o["milho_verao"]["estagios"]][1] == "pendoamento" and o["milho_verao"]["estagios"][-1]["dias_ate_colheita"] == 0
    assert "Embrapa" in opcoes()["estagios_fonte"]
