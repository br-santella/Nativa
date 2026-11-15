"""Field Shift MVP (teaching app). Run: uv run streamlit run src/field_shift/app/mvp.py"""
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))
import engine as E  # noqa: E402
from field_shift.renda import carregar_referencia, fonte_custo, fonte_preco  # noqa: E402
from field_shift.renda.renda import LINHA_NOME, ROTULO  # noqa: E402

st.set_page_config(page_title="Field Shift — MVP", layout="wide")
st.title("Field Shift — crop-rotation decision support")
st.caption("Teaching MVP. NASA data + legal rules + a catalog of reference estimates. It does not replace the agronomist.")


@st.cache_data
def _talhao(): return E.carregar_talhao()
@st.cache_data
def _ndvi(): return E.carregar_ndvi()
@st.cache_data(show_spinner="Querying the climate (Western Paraná lookup; outside it, live NASA POWER)…")
def _clima(lat, lon, semeadura): return E.obter_clima(lat, lon, semeadura)


@st.cache_data(show_spinner="Reading soil (SoilGrids) and yield (IBGE PAM)…")
def _enriquecer(rk, lat, lon): return E.enriquecer(rk, _talhao())


def fonte(texto): st.caption(f"**Why / source:** {texto}")


# ------------------------------------------------------------------ 1. Location
st.header("1. Location")
t = _talhao()
c1, c2 = st.columns([1, 2])
c1.metric("Field", t["id"]); c1.metric("Area", f"{t['area_ha']:.1f} ha")
c1.write(f"Centroid: **{t['lat']:.5f}, {t['lon']:.5f}** (Toledo/PR, Western Paraná)")
if t["declividade"] is not None:
    c1.write(f"Mean slope: **{t['declividade']:.1f}%** (p90 {t['declividade_p90']:.1f}%) · Embrapa class: **{t['classe_embrapa']}** "
             f"· elevation **{t['altitude']:.0f} m** (NASADEM)")
else:
    c1.write("Slope / elevation: **no data** (polygon outside Western Paraná)")
xs, ys = t["poly"].exterior.xy
fig = go.Figure(go.Scattermap(lon=list(xs), lat=list(ys), mode="lines", fill="toself", line=dict(color="#d62728")))
fig.update_layout(map=dict(style="open-street-map", center=dict(lat=t["lat"], lon=t["lon"]), zoom=13),
                  margin=dict(l=0, r=0, t=0, b=0), height=320)
c2.plotly_chart(fig, width="stretch")
fonte("climate and history depend on where the field is; polygon detected by the FTW (Fields of the World) model on Sentinel-2.")

# ------------------------------------------------------------------ 2. History
st.header("2. Past — history (pre-computed)")
st.write("**MapBiomas (land use per year):** " + " · ".join(f"{a}: {n}" for a, n in t["historico"].items()))
ndvi = _ndvi()
faixas = E.faixas_solo(ndvi)
picos = E.picos_por_ano_agricola(ndvi)
rot_detectada = E.detectar_rotacao(picos)
figN = go.Figure(go.Scatter(x=ndvi.index, y=ndvi.values, name="Smoothed NDVI", line=dict(color="#2ca02c")))
for ini, fim in faixas:
    figN.add_vrect(x0=ini, x1=fim, fillcolor="#8c564b", opacity=0.25, line_width=0)
figN.add_hline(y=E.LIMIAR_SOLO, line_dash="dot", annotation_text="NDVI 0.35")
figN.update_layout(height=320, margin=dict(t=10, b=10), yaxis_title="NDVI", xaxis_title=None)
st.plotly_chart(figN, width="stretch")
st.write(f"Brown bands = bare soil/low cover (NDVI<{E.LIMIAR_SOLO}): "
         f"**~{E.dias_solo_por_ano(ndvi):.0f} days/year**. Peaks per agricultural year (Sep–Aug): {picos}.")
st.success(f"Detected rotation: **{rot_detectada}** ({'2 seasons per agricultural year' if rot_detectada.endswith('corn') else '1 season per year'}).")
fonte("MapBiomas Collection 10 (class per year) and HLS Sentinel-2/Landsat NDVI (NASA), filtered by a clear-pixel fraction ≥ 70%. Two green peaks in the year = two seasons.")

# ------------------------------------------------------------------ 3. Climate
st.header("3. Past — climate (NASA POWER)")
sem = st.selectbox("Off-season corn sowing date", E.SEMEADURAS, index=E.SEMEADURAS.index(E.SEMEADURA_PADRAO),
                   help="Sets the frost window at corn flowering/grain fill (pre-computed indicator).")
try:
    rk, origem = _clima(round(t["lat"], 4), round(t["lon"], 4), sem)
except Exception as e:
    st.error(f"Could not get the climate: {e}")
    st.stop()
rk = _enriquecer(rk, t["lat"], t["lon"])  # + soil (SoilGrids), water-balance context and municipal PAM
if rk["modo"] == "reduzido":
    st.warning("Reduced mode: the field is outside Western Paraná. Climate from live NASA POWER (centroid point); "
               "no per-sowing-date table or extended diagnosis.")
    st.caption(f"Data origin: {origem} · period {rk['periodo']} ({rk['n_anos']} years)")
else:
    cel, mun = rk["celula"], rk["municipio"]
    st.caption(f"Source: NASA POWER, {rk['periodo']} ({rk['n_anos']} years), ~50 km cell {cel['ponto_id']} "
               f"(center {cel['lat']:.2f}, {cel['lon']:.2f}; elev. {cel['elev']:.0f} m). "
               f"Context: municipality of {mun['nome']} (cell indicators, not the municipality's).")
m1, m2, m3 = st.columns(3)
m1.metric(f"Frost on off-season corn (sowing {sem})" if rk["semeadura"] else "Frost on off-season corn", f"{rk['geada_safrinha']:.0%} of years")
m1.caption("Min T ≤ 3 °C at corn flowering/grain fill." if rk["semeadura"] else "Min T ≤ 3 °C in June–July.")
m2.metric("Wheat frost (flowering)", f"{rk['geada_trigo']:.0%} of years")
m2.caption("Min T ≤ 3 °C at wheat flowering (≤ 3 °C threshold: POWER underestimates frost vs. INMET).")
m3.metric("Off-season dry spell", f"{rk['veranico_safrinha']:.0%} of years")
m3.caption("≥ 15 consecutive days with rain < 1 mm in March–April, the off-season critical phase.")
if rk["geada_tabela"]:
    st.markdown("**Off-season frost (≤ 3 °C) by sowing date**")
    df_g = pd.DataFrame(rk["geada_tabela"])
    df_g["Probability"] = df_g["prob"].map("{:.0%}".format)
    df_g["Years with frost"] = df_g.apply(lambda r: f"{r['anos']} of {r['n_anos']}", axis=1)
    df_g["1991–2020"] = df_g["prob_1991_2020"].map("{:.0%}".format)
    st.dataframe(df_g.rename(columns={"semeadura": "Sowing"})[["Sowing", "Probability", "Years with frost", "1991–2020"]],
                 width="stretch", hide_index=True)
    st.caption("The later the off-season sowing, the higher the chance of frost during grain fill. "
               "The row selected above enters the risk score.")
if rk["diagnostico"]:
    st.markdown("**Climate diagnosis** (informational only; not part of the score)")
    st.markdown("\n".join(f"- {x}" for x in E.fmt_diagnostico(rk["diagnostico"])))
chuva = rk["chuva_mensal"]
meses = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
figC = go.Figure(go.Bar(x=meses, y=chuva.values, marker_color="#1f77b4"))
figC.add_annotation(x="jun", y=chuva[6], text=f"off-season frost<br>{rk['geada_safrinha']:.0%}", showarrow=True, ay=-50)
figC.add_annotation(x="sep", y=chuva[9], text=f"wheat frost<br>{rk['geada_trigo']:.0%}", showarrow=True, ay=-50)
figC.add_annotation(x="mar", y=chuva[3], text=f"dry spell<br>{rk['veranico_safrinha']:.0%}", showarrow=True, ay=-50)
figC.update_layout(height=300, margin=dict(t=10, b=10), yaxis_title="Mean monthly rain (mm)")
st.plotly_chart(figC, width="stretch")
fonte(f"{rk['fonte']}. The frequency is the fraction of years in which the event occurred.")

# Soil and local yield
if rk["solo"]:
    s = rk["solo"]
    st.subheader("Soil (SoilGrids/ISRIC, field mean)")
    cs1, cs2, cs3, cs4, cs5 = st.columns(5)
    cs1.metric("Clay 0–30 cm", f"{s['p30']['clay']:.0f}%"); cs2.metric("Sand 0–30 cm", f"{s['p30']['sand']:.0f}%")
    cs3.metric("Organic C 0–30 cm", f"{s['p30']['soc']:.1f} g/kg"); cs4.metric("pH 0–30 cm", f"{s['p30']['phh2o']:.1f}")
    cs5.metric("AWC (0–60 cm)", f"{s['cad_mm_0_60']:.0f} mm", help=f"{s['cad_mm_cm']['0-30']:.2f} mm/cm over 0–30 cm")
    st.caption(f"Texture: {s['classe_textura']}. AWC (available water) from the Saxton & Rawls (2006) pedotransfer, "
               "which may be wrong in tropical Latosols; SoilGrids has no moisture at 33/1500 kPa. It feeds the water balance of the Water criterion.")
else:
    st.info("Soil (SoilGrids): no data outside Western Paraná; the Water criterion only uses rain × cycle demand.")
if rk["pam"]:
    st.subheader("Municipal yield (IBGE PAM)")
    st.write(E.fmt_pam(rk))
    st.caption("Mean of the last 5 years with data (SIDRA tables 1612 and 839); 60 kg bags. It feeds the margin (income criterion).")

# ------------------------------------------------------------------ 4. Farmer
st.header("4. Farmer situation")
nomes = list(E.CATALOGO)
atual = st.selectbox("Current rotation (pre-filled from the history, editable)", nomes, index=nomes.index(rot_detectada))
cols = st.columns(5)
pesos = {k: cols[i].slider(nome, 0, 5, E.PESOS_PADRAO[k]) for i, (k, nome) in enumerate(E.CRITERIOS.items())}
st.caption("Climate risk = aversion: a high weight penalizes candidates exposed to frost/dry spells.")
fonte("the decision depends on what the farmer values; the weights become the weighted average of the score.")

# ------------------------------------------------------------------ 5. Engine
st.header("5. Engine")
REF = carregar_referencia()
st.subheader("Income: prices and costs (editable reference values)")
linha = st.radio("CONAB cost line (soybean, corn, wheat)", ["coe", "cot"], horizontal=True,
                 format_func=lambda k: {"coe": "Variable cost (≈COE: cash outlay)", "cot": "COT (includes depreciation and fixed costs)"}[k],
                 index=["coe", "cot"].index(REF["linha_custo_padrao"]),
                 help="The total operating cost (COT) includes depreciation and fixed costs that the farmer does not decide per crop.")
cp, cc = st.columns(2)
ajustes = {"linha_custo": linha, "preco": {}, "custo": {}}
for k, nome in [("soja", "soybean"), ("milho", "corn"), ("trigo", "wheat")]:
    ref_v = REF["precos"][k]["valor"]
    v = cp.number_input(f"Price {nome} (BRL/60 kg bag)", min_value=0.0, value=float(ref_v), step=1.0, key=f"preco_{k}")
    if abs(v - ref_v) > 1e-9:
        ajustes["preco"][k] = v
for k in REF["custos"]:
    ref_v = REF["custos"][k][linha]
    v = cc.number_input(f"Cost {ROTULO[k]} (BRL/ha)", min_value=0.0, value=float(ref_v), step=50.0, key=f"custo_{k}_{linha}")
    if abs(v - ref_v) > 1e-9:
        ajustes["custo"][k] = v
res = E.pontuar(pesos, rk, ajustes)
st.markdown("**Hard rules** (they eliminate): soybean after soybean in the same agricultural year; live soybean in the soybean-free period (02/06–31/08, Western Paraná); "
            "soybean sowing only between 01/09 and 31/12.")
st.warning(E.AVISO_ZARC)
st.caption("The ordinances (SDA/MAPA 1.124/2024 and the Paraná soybean-free period) still need to be checked against the official sources. "
           "Price (SEAB/DERAL) and cost (CONAB) come from real sources; cover/fallow costs, Kc and the straw/N bonus are reference estimates — validate with an agronomist/Embrapa.")
fonte("fixed catalog of candidates; every criterion on an absolute 0–1 scale: income = incremental second-season margin (PAM × price − cost, plus the bonus on the following soybean) on the scale of the municipal soybean margin (0.5 + incremental/2S, limited to 0–1); "
     "soil and pests from the catalog; water = ETa/ETc in the critical phase from the daily water balance (NASA POWER + SoilGrids soil; changes with the sowing date); risk = 1 − probability; score = Σ weight × criterion. Default weights: income 5, others 3.")

# ------------------------------------------------------------------ 6. Result
st.header("6. Result")
tab = res["tabela"]
mostra = tab.drop(columns=["contrib"]).rename(columns={"candidata": "Candidate", "nota": "Score", **E.CRITERIOS})
st.dataframe(mostra.round(2), width="stretch", hide_index=True)
if res["aviso_renda"]:
    st.warning(res["aviso_renda"])
st.subheader("Income per crop: price, cost, yield and margin")
_vistos = {}
for _m in res["margens"].values():
    for _i in _m["itens"]:
        _vistos.setdefault(_i["chave"], (_i, _m["linha_custo"]))
st.dataframe(pd.DataFrame([{
    "Crop": i["rotulo"], "Yield (bags/ha)": i["sc_ha"], "Yield CV": i["cv"], "Price (BRL/bag)": i["preco"],
    "Cost (BRL/ha)": i["custo"], "Margin (BRL/ha)": i["margem"], "Bad-year margin (p20)": i["margem_ano_ruim"],
    "Price source": fonte_preco(i), "Cost source": fonte_custo(i, ln)} for i, ln in _vistos.values()]),
    width="stretch", hide_index=True,
    column_config={"Yield (bags/ha)": st.column_config.NumberColumn(format="%.0f"), "Yield CV": st.column_config.NumberColumn(format="%.0f%%"),
                   "Price (BRL/bag)": st.column_config.NumberColumn(format="%.2f"), "Cost (BRL/ha)": st.column_config.NumberColumn(format="%.0f"),
                   "Margin (BRL/ha)": st.column_config.NumberColumn(format="%.0f"), "Bad-year margin (p20)": st.column_config.NumberColumn(format="%.0f")})
_any = next(iter(_vistos.values()))[0]
if rk["rend"]["_origem"].startswith("average"):
    st.warning("No municipality/PAM for this field: using " + rk["rend"]["_origem"] + ".")
st.caption(f"Yield: {rk['rend']['_origem']}, mean of the last 5 years ({_any['anos']}). CV and p20 (bad year): last 10 years, display only. "
           f"Prices queried on {REF['consulta']}. Margin = yield × price − cost; cover/fallow = − cost (reference estimate, to be validated). "
           "(CONAB does not cover Western Paraná for commercial farming: cost from Londrina/Ponta Grossa).")
if res["eliminadas"]:
    st.subheader("Eliminated")
    for n, motivos in res["eliminadas"].items():
        st.error(f"**{n}** — " + " ".join(motivos))
dias_ndvi = E.dias_solo_por_ano(ndvi)


def card(col, titulo, linha, eh_atual):
    with col.container(border=True):
        st.subheader(titulo)
        st.markdown(f"**{linha['candidata']}**")
        st.metric("Score", f"{linha['nota']:.2f}")
        d = E.montar_card(linha, eh_atual, rk, dias_ndvi, res["margens"][linha["candidata"]],
                         E.por_que_comparado(res, linha["candidata"], atual))
        st.markdown("**Why it was suggested**"); st.write(d["por_que"])
        for titulo2, chave in [("Evidence", "evidencia"), ("Benefits", "beneficios"),
                               ("Information gaps", "lacunas"), ("Risks to review with the agronomist", "revisar")]:
            st.markdown(f"**{titulo2}**")
            st.markdown("\n".join(f"- {x}" for x in d[chave]))


st.subheader("Current rotation and the 3 best alternatives")
cs = st.columns(4)
if atual in res["eliminadas"]:
    with cs[0].container(border=True):
        st.subheader("Current rotation"); st.markdown(f"**{atual}**")
        st.error("Eliminated by the hard rules: " + " ".join(res["eliminadas"][atual]))
else:
    card(cs[0], "Current rotation", tab[tab.candidata == atual].iloc[0], True)
for col, (_, linha) in zip(cs[1:], tab[tab.candidata != atual].head(3).iterrows()):
    card(col, f"Alternative #{list(tab[tab.candidata != atual].candidata).index(linha['candidata']) + 1}", linha, False)

st.info("**Next data:** SMAP (soil moisture), GPM (satellite rainfall), "
        "IBGE PAM (area and value) and CONAB (calendar); regional Western Paraná costs for soybean and corn.")
