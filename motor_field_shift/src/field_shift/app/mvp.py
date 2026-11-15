"""Field Shift MVP (teaching version). Run: uv run streamlit run src/field_shift/app/mvp.py"""
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))
import engine as E  # noqa: E402
from field_shift.income import load_reference, cost_source, price_source  # noqa: E402
from field_shift.income.income import LABEL  # noqa: E402

st.set_page_config(page_title="Field Shift — MVP", layout="wide")
st.title("Field Shift — apoio à decisão de rotação de culturas")
st.caption("MVP didático. Dados NASA + regras legais + catálogo de estimativas de referência. Não substitui o agrônomo.")


@st.cache_data
def _field(): return E.load_field()
@st.cache_data
def _ndvi(): return E.load_ndvi()
@st.cache_data(show_spinner="Consultando o clima (lookup do Oeste do PR; fora dele, NASA POWER ao vivo)…")
def _climate(lat, lon, sowing): return E.get_climate(lat, lon, sowing)


@st.cache_data(show_spinner="Lendo solo (SoilGrids) e produtividade (IBGE PAM)…")
def _enrich(rk, lat, lon): return E.enrich(rk, _field())


def source(text): st.caption(f"**Por quê / fonte:** {text}")


# Local
st.header("1. Local")
t = _field()
c1, c2 = st.columns([1, 2])
c1.metric("Talhão", t["id"]); c1.metric("Área", f"{t['area_ha']:.1f} ha")
c1.write(f"Centróide: **{t['lat']:.5f}, {t['lon']:.5f}** (Toledo/PR, Oeste do PR)")
if t["declividade"] is not None:
    c1.write(f"Declividade média: **{t['declividade']:.1f}%** (p90 {t['declividade_p90']:.1f}%) · classe Embrapa: **{t['classe_embrapa']}** "
             f"· altitude **{t['altitude']:.0f} m** (NASADEM)")
else:
    c1.write("Declividade / altitude: **sem dado** (polígono fora do Paraná)")
xs, ys = t["poly"].exterior.xy
fig = go.Figure(go.Scattermap(lon=list(xs), lat=list(ys), mode="lines", fill="toself", line=dict(color="#d62728")))
fig.update_layout(map=dict(style="open-street-map", center=dict(lat=t["lat"], lon=t["lon"]), zoom=13),
                  margin=dict(l=0, r=0, t=0, b=0), height=320)
c2.plotly_chart(fig, width="stretch")
source("o clima e o histórico dependem de onde está o talhão; polígono detectado pelo modelo FTW (Fields of the World) sobre Sentinel-2.")

# History
st.header("2. Passado — histórico (pré-calculado)")
st.write("**MapBiomas (uso do solo por ano):** " + " · ".join(f"{a}: {n}" for a, n in t["historico"].items()))
ndvi = _ndvi()
ranges = E.soil_ranges(ndvi)
peaks = E.peaks_by_crop_year(ndvi)
detected_rot = E.detect_rotation(peaks)
figN = go.Figure(go.Scatter(x=ndvi.index, y=ndvi.values, name="NDVI suavizado", line=dict(color="#2ca02c")))
for start, end in ranges:
    figN.add_vrect(x0=start, x1=end, fillcolor="#8c564b", opacity=0.25, line_width=0)
figN.add_hline(y=E.SOIL_THRESHOLD, line_dash="dot", annotation_text="NDVI 0,35")
figN.update_layout(height=320, margin=dict(t=10, b=10), yaxis_title="NDVI", xaxis_title=None)
st.plotly_chart(figN, width="stretch")
st.write(f"Faixas marrons = solo descoberto/baixa cobertura (NDVI<{E.SOIL_THRESHOLD}): "
         f"**~{E.bare_soil_days_by_year(ndvi):.0f} dias/ano**. Picos por ano agrícola (set–ago): {peaks}.")
st.success(f"Rotação detectada: **{detected_rot}** ({'2 safras por ano agrícola' if detected_rot.endswith('safrinha') else '1 safra por ano'}).")
source("MapBiomas Coleção 10 (classe por ano) e NDVI do HLS Sentinel-2/Landsat (NASA), filtrado por fração de pixels limpos ≥ 70%. Dois picos de verde no ano = duas safras.")

# Clima
st.header("3. Passado — clima (NASA POWER)")
sow_date = st.selectbox("Data de semeadura do milho safrinha", E.SOWINGS_2ND, index=E.SOWINGS_2ND.index(E.DEFAULT_SOWING),
                   help="Define a janela de geada no florescimento/enchimento do milho (indicador pré-calculado).")
try:
    rk, origin = _climate(round(t["lat"], 4), round(t["lon"], 4), sow_date)
except Exception as e:
    st.error(f"Não foi possível obter o clima: {e}")
    st.stop()
rk = _enrich(rk, t["lat"], t["lon"])  # + soil (SoilGrids), water-balance context and municipality PAM
if rk["modo"] == "reduzido":
    st.warning("Modo reduzido: o talhão está fora do Paraná. Clima pelo NASA POWER ao vivo (ponto do centróide); "
               "sem tabela por data de semeadura nem diagnóstico ampliado.")
    st.caption(f"Origem dos dados: {origin} · período {rk['periodo']} ({rk['n_anos']} anos)")
else:
    cell, mun = rk["celula"], rk["municipio"]
    st.caption(f"Fonte: NASA POWER, {rk['periodo']} ({rk['n_anos']} anos), célula ~50 km {cell['ponto_id']} "
               f"(centro {cell['lat']:.2f}, {cell['lon']:.2f}; elev. {cell['elev']:.0f} m). "
               f"Contexto: município de {mun['nome']} (indicadores da célula, não do município).")
m1, m2, m3 = st.columns(3)
m1.metric(f"Geada no milho safrinha (semeadura {sow_date})" if rk["semeadura"] else "Geada no milho safrinha", f"{rk['geada_safrinha']:.0%} dos anos")
m1.caption("T mínima ≤ 3 °C no florescimento/enchimento do milho." if rk["semeadura"] else "T mínima ≤ 3 °C em junho–julho.")
m2.metric("Geada no trigo (florescimento)", f"{rk['geada_trigo']:.0%} dos anos")
m2.caption("T mínima ≤ 3 °C no florescimento do trigo (limiar ≤ 3 °C: o POWER subestima geada vs. INMET).")
m3.metric("Veranico no safrinha", f"{rk['veranico_safrinha']:.0%} dos anos")
m3.caption("≥ 15 dias seguidos com chuva < 1 mm em março–abril, fase crítica do safrinha.")
if rk["geada_tabela"]:
    st.markdown("**Geada (≤ 3 °C) no safrinha conforme a data de semeadura**")
    df_g = pd.DataFrame(rk["geada_tabela"])
    df_g["Probabilidade"] = df_g["prob"].map("{:.0%}".format)
    df_g["Anos com geada"] = df_g.apply(lambda r: f"{r['anos']} de {r['n_anos']}", axis=1)
    df_g["1991–2020"] = df_g["prob_1991_2020"].map("{:.0%}".format)
    st.dataframe(df_g.rename(columns={"semeadura": "Semeadura"})[["Semeadura", "Probabilidade", "Anos com geada", "1991–2020"]],
                 width="stretch", hide_index=True)
    st.caption("Quanto mais tarde a semeadura do safrinha, maior a chance de geada no enchimento. "
               "Linha selecionada acima entra na nota de risco.")
if rk["diagnostico"]:
    st.markdown("**Diagnóstico do clima** (só informativo; não entra na nota)")
    st.markdown("\n".join(f"- {x}" for x in E.fmt_diagnosis(rk["diagnostico"])))
rain = rk["chuva_mensal"]
months = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
figC = go.Figure(go.Bar(x=months, y=rain.values, marker_color="#1f77b4"))
figC.add_annotation(x="jun", y=rain[6], text=f"geada safrinha<br>{rk['geada_safrinha']:.0%}", showarrow=True, ay=-50)
figC.add_annotation(x="set", y=rain[9], text=f"geada trigo<br>{rk['geada_trigo']:.0%}", showarrow=True, ay=-50)
figC.add_annotation(x="mar", y=rain[3], text=f"veranico<br>{rk['veranico_safrinha']:.0%}", showarrow=True, ay=-50)
figC.update_layout(height=300, margin=dict(t=10, b=10), yaxis_title="Chuva média mensal (mm)")
st.plotly_chart(figC, width="stretch")
source(f"{rk['fonte']}. A frequência é a fração de anos em que o evento ocorreu.")

# Solo e produtividade local
if rk["solo"]:
    s = rk["solo"]
    st.subheader("Solo (SoilGrids/ISRIC, média no talhão)")
    cs1, cs2, cs3, cs4, cs5 = st.columns(5)
    cs1.metric("Argila 0–30 cm", f"{s['p30']['clay']:.0f}%"); cs2.metric("Areia 0–30 cm", f"{s['p30']['sand']:.0f}%")
    cs3.metric("C orgânico 0–30 cm", f"{s['p30']['soc']:.1f} g/kg"); cs4.metric("pH 0–30 cm", f"{s['p30']['phh2o']:.1f}")
    cs5.metric("CAD (0–60 cm)", f"{s['cad_mm_0_60']:.0f} mm", help=f"{s['cad_mm_cm']['0-30']:.2f} mm/cm em 0–30 cm")
    st.caption(f"Textura: {s['classe_textura']}. CAD (água disponível) por pedotransferência de Saxton & Rawls (2006), "
               "que pode errar em latossolos tropicais; o SoilGrids não traz umidade a 33/1500 kPa. Alimenta o balanço hídrico do critério Água.")
else:
    st.info("Solo (SoilGrids): sem dado fora do Paraná; o critério Água usa só chuva × demanda do ciclo.")
if rk["pam"]:
    st.subheader("Produtividade do município (IBGE PAM)")
    st.write(E.fmt_pam(rk))
    st.caption("Média dos últimos 10 anos com dado (SIDRA tabelas 1612 e 839); sacas de 60 kg. Alimenta a margem (critério renda).")

# Operador
st.header("4. Situação do operador")
names = list(E.CATALOG)
current = st.selectbox("Rotação atual (pré-preenchida pelo histórico, editável)", names, index=names.index(detected_rot))
cols = st.columns(5)
pesos = {k: cols[i].slider(nome, 0, 5, E.DEFAULT_WEIGHTS[k]) for i, (k, nome) in enumerate(E.CRITERIA.items())}
st.caption("Risco climático = aversão: peso alto penaliza candidatas expostas a geada/veranico.")
source("a decisão depende do que o produtor valoriza; os pesos viram a média ponderada da nota.")

# Motor
st.header("5. Motor")
REF = load_reference()
st.subheader("Renda: preços e custos (valores de referência editáveis)")
line = st.radio("Linha de custo CONAB (soja, milho, trigo)", ["coe", "cot"], horizontal=True,
                 format_func=lambda k: {"coe": "Custo variável (≈COE: desembolso)", "cot": "COT (inclui depreciação e custos fixos)"}[k],
                 index=["coe", "cot"].index(REF["default_cost_line"]),
                 help="O custo operacional total (COT) inclui depreciação e custos fixos que o produtor não decide por cultura.")
cp, cc = st.columns(2)
adjustments = {"linha_custo": line, "preco": {}, "custo": {}}
for k, nome in [("soja", "soja"), ("milho", "milho"), ("trigo", "trigo")]:
    ref_v = REF["prices"][k]["value"]
    v = cp.number_input(f"Preço {nome} (R$/saca 60 kg)", min_value=0.0, value=float(ref_v), step=1.0, key=f"preco_{k}")
    if abs(v - ref_v) > 1e-9:
        adjustments["preco"][k] = v
for k in REF["costs"]:
    ref_v = REF["costs"][k][line]
    v = cc.number_input(f"Custo {LABEL[k]} (R$/ha)", min_value=0.0, value=float(ref_v), step=50.0, key=f"custo_{k}_{line}")
    if abs(v - ref_v) > 1e-9:
        adjustments["custo"][k] = v
res = E.score_rotation(pesos, rk, adjustments)
st.markdown("**Regras duras** (eliminam): soja sobre soja no mesmo ano agrícola; soja viva no vazio sanitário (02/06–31/08, Oeste PR); "
            "semeadura de soja só entre 01/09 e 31/12.")
st.warning(E.ZARC_WARNING)
st.caption("As portarias (SDA/MAPA 1.124/2024 e vazio sanitário do PR) ainda precisam ser conferidas nas fontes oficiais. "
           "Preço (SEAB/DERAL) e custo (CONAB) vêm de fontes reais; custos de cobertura/pousio, Kc e bônus de palhada/N são estimativas de referência — validar com agrônomo/Embrapa.")
source("catálogo fixo de 7 candidatas; todos os critérios em escala absoluta 0–1: renda = margem incremental da 2ª safra (PAM × preço − custo, mais bônus na soja seguinte) na escala S fixa de R$ 1.110/ha (0,5 + 0,5·tanh(incremental/S)); "
     "solo e pragas do catálogo; água = ETa/ETc na fase crítica pelo balanço hídrico diário (NASA POWER + solo SoilGrids; muda com a data de semeadura); risco = 1 − probabilidade; nota = Σ peso × critério. Pesos padrão: renda 5, demais 3.")

# Resultado
st.header("6. Resultado")
tab = res["tabela"]
shown = tab.drop(columns=["contrib"]).rename(columns={"candidata": "Candidata", "nota": "Nota", **E.CRITERIA})
st.dataframe(shown.round(2), width="stretch", hide_index=True)
if res["aviso_renda"]:
    st.warning(res["aviso_renda"])
st.subheader("Renda por cultura: preço, custo, rendimento e margem")
_seen = {}
for _m in res["margens"].values():
    for _i in _m["itens"]:
        _seen.setdefault(_i["chave"], (_i, _m["linha_custo"]))
st.dataframe(pd.DataFrame([{
    "Cultura": i["rotulo"], "Rendimento (sc/ha)": i["sc_ha"], "CV rend.": i["cv"], "Preço (R$/sc)": i["preco"],
    "Custo (R$/ha)": i["custo"], "Margem (R$/ha)": i["margem"], "Margem ano ruim (p20)": i["margem_ano_ruim"],
    "Fonte do preço": price_source(i), "Fonte do custo": cost_source(i, ln)} for i, ln in _seen.values()]),
    width="stretch", hide_index=True,
    column_config={"Rendimento (sc/ha)": st.column_config.NumberColumn(format="%.0f"), "CV rend.": st.column_config.NumberColumn(format="%.0f%%"),
                   "Preço (R$/sc)": st.column_config.NumberColumn(format="%.2f"), "Custo (R$/ha)": st.column_config.NumberColumn(format="%.0f"),
                   "Margem (R$/ha)": st.column_config.NumberColumn(format="%.0f"), "Margem ano ruim (p20)": st.column_config.NumberColumn(format="%.0f")})
_any = next(iter(_seen.values()))[0]
if rk["rend"]["_origem"].startswith("média"):
    st.warning("Sem município/PAM para este talhão: usando " + rk["rend"]["_origem"] + ".")
st.caption(f"Rendimento: {rk['rend']['_origem']}, média dos últimos 10 anos ({_any['anos']}); CV e p20 (ano ruim) usam a mesma janela. "
           f"Preços consultados em {REF['queried_on']}. Margem = rendimento × preço − custo; cobertura/pousio = − custo (estimativa de referência, validar). "
           "(CONAB não cobre o Oeste do PR em empresarial: custo de Londrina/Ponta Grossa).")
if res["eliminadas"]:
    st.subheader("Eliminadas")
    for n, reasons in res["eliminadas"].items():
        st.error(f"**{n}** — " + " ".join(reasons))
ndvi_days = E.bare_soil_days_by_year(ndvi)


def card(col, title, line, is_current):
    with col.container(border=True):
        st.subheader(title)
        st.markdown(f"**{line['candidata']}**")
        st.metric("Nota", f"{line['nota']:.2f}")
        d = E.build_card(line, is_current, rk, ndvi_days, res["margens"][line["candidata"]],
                         E.why_compared(res, line["candidata"], current))
        st.markdown("**Por que foi sugerida**"); st.write(d["por_que"])
        for title2, key in [("Evidência", "evidencia"), ("Benefícios", "beneficios"),
                               ("Lacunas de informação", "lacunas"), ("Riscos para revisar com agrônomo", "revisar")]:
            st.markdown(f"**{title2}**")
            st.markdown("\n".join(f"- {x}" for x in d[key]))


st.subheader("Rotação atual e as 3 melhores alternativas")
cs = st.columns(4)
if current in res["eliminadas"]:
    with cs[0].container(border=True):
        st.subheader("Rotação atual"); st.markdown(f"**{current}**")
        st.error("Eliminada pelas regras duras: " + " ".join(res["eliminadas"][current]))
else:
    card(cs[0], "Rotação atual", tab[tab.candidata == current].iloc[0], True)
for col, (_, line) in zip(cs[1:], tab[tab.candidata != current].head(3).iterrows()):
    card(col, f"Alternativa #{list(tab[tab.candidata != current].candidata).index(line['candidata']) + 1}", line, False)

st.info("**Próximos dados:** SMAP (umidade do solo), GPM (chuva satelital), "
        "IBGE PAM (área e valor) e CONAB (calendário); custos regionais do Oeste do PR para soja e milho.")
