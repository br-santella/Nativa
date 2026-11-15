import { t as __text, t, locale, useLanguage, LanguageProvider, LanguageSwitcher } from "./i18n";
import React, { useState, useEffect, useRef, createContext, useContext, } from "react";
import { createRoot } from "react-dom/client";
import { motion, useReducedMotion } from "motion/react";
import assets from "./assets.json";
import { months, initialFarm, initialCrops, series, scenarios, profiles, score, info, } from "./data";
import type { Farm, Crop } from "./data";
import "./styles.css";
import MotorPanel from "./MotorPanel";
import ClimateStory from "./ClimateStory";
import SolutionStory from "./SolutionStory";
const A = assets.overview, L = assets["13:16"];
const path = (file: string) => "/assets/" + file;
type Page = "landing" | "signup" | "onboard" | "overview" | "farm" | "history" | "climate" | "rotation" | "settings";
type Modal = null | "sources" | "indicators" | "help" | "technology" | "addCrop" | "account" | "property" | "login" | "contact" | "map" | number;
const pages: Page[] = [
    "landing",
    "signup",
    "onboard",
    "overview",
    "farm",
    "history",
    "climate",
    "rotation",
    "settings",
];
function currentPage(): Page {
    const p = location.hash.slice(1) as Page;
    return pages.includes(p) ? p : "landing";
}
const DraftContext = createContext<{
    draft: Farm;
    setDraft: React.Dispatch<React.SetStateAction<Farm>>;
}>({ draft: initialFarm, setDraft: () => { } });
function Field({ label, name, type = "text", options, min, max, step, }: {
    label: string;
    name: keyof Farm;
    type?: string;
    options?: string[];
    min?: number;
    max?: number;
    step?: string;
}) {
    const { draft, setDraft } = useContext(DraftContext);
    return (<label className="field">
      <span>{__text(label)}</span>
      {__text(options ? (<select value={draft[name]} onChange={(e) => setDraft((v) => ({ ...v, [name]: e.target.value }))}>
          {__text(options.map((o) => (<option key={o} value={o}>{__text(o)}</option>)))}
        </select>) : (<input type={type} value={draft[name]} onChange={(e) => setDraft((v) => ({ ...v, [name]: e.target.value }))} min={min} max={max} step={step} required={name === "name" || name === "area"}/>))}
    </label>);
}
function App() {
    useLanguage();
    const [page, setPage] = useState<Page>(currentPage), [modal, setModal] = useState<Modal>(null), [farm, setFarm] = useState<Farm>({ ...initialFarm }), [draft, setDraft] = useState<Farm>({ ...initialFarm }), [crops, setCrops] = useState<Crop[]>(initialCrops), [year, setYear] = useState("2025"), [period, setPeriod] = useState("12"), [layer, setLayer] = useState("Vegetação (NDVI)"), [zoom, setZoom] = useState(1), [menu, setMenu] = useState(false), [notice, setNotice] = useState(""), [weights, setWeights] = useState<number[]>(profiles.soil), [applied, setApplied] = useState<number[]>(profiles.soil), [busy, setBusy] = useState(false), [slide, setSlide] = useState(0), [carouselPaused, setCarouselPaused] = useState(false), [carouselFocused, setCarouselFocused] = useState(false), [report, setReport] = useState<File | null>(null), [calendar, setCalendar] = useState(false), [explain, setExplain] = useState(false), [userName, setUserName] = useState("Marina Silva"), [settings, setSettings] = useState({
        temperature: "Graus Celsius (°C)",
    });
    const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
    const reduced = useReducedMotion();
    useEffect(() => {
        if (page !== "landing" || reduced || carouselPaused || carouselFocused)
            return;
        const interval = window.setInterval(() => {
            if (!document.hidden)
                setSlide((current) => (current + 1) % 3);
        }, 6000);
        return () => window.clearInterval(interval);
    }, [page, reduced, carouselPaused, carouselFocused, slide]);
    useEffect(() => {
        const h = () => {
            setPage(currentPage());
            setMenu(false);
            setModal(null);
            window.scrollTo(0, 0);
        };
        addEventListener("hashchange", h);
        return () => removeEventListener("hashchange", h);
    }, []);
    useEffect(() => {
        if (!notice)
            return;
        const t = setTimeout(() => setNotice(""), 4500);
        return () => clearTimeout(t);
    }, [notice]);
    useEffect(() => () => {
        if (timer.current)
            clearTimeout(timer.current);
    }, []);
    function go(p: Page) {
        location.hash = p;
        if (page === p) {
            setMenu(false);
            setModal(null);
            window.scrollTo(0, 0);
        }
    }
    function toast(s: string) {
        setNotice(s);
    }
    function saveFarm(e: React.FormEvent) {
        e.preventDefault();
        setFarm({ ...draft });
        toast("Alterações aplicadas nesta sessão.");
    }
    function compare() {
        if (!weights.some(Boolean)) {
            toast("Defina pelo menos uma prioridade maior que zero.");
            return;
        }
        setBusy(true);
        timer.current = setTimeout(() => {
            setApplied([...weights]);
            setBusy(false);
            toast("Comparação demonstrativa atualizada.");
        }, 600);
    }
    const chosen = scenarios.map((s) => score(s.notes, applied));
    const winner = chosen.indexOf(Math.max(...chosen));
    const navItems: [
        Page,
        string,
        string
    ][] = [
        ["overview", "Visão Geral", A.imgIconeDeNavegacao],
        ["farm", "Minha Propriedade", A.imgIconeDeNavegacao1],
        ["climate", "Análise Climática", A.imgIconeDeNavegacao3],
        ["history", "Histórico de Cultivo", A.imgIconeDeNavegacao2],
        ["rotation", "Estratégias de Rotação", A.imgIconeDeNavegacao4],
    ];
    const open = (m: Modal) => setModal(m);
    function Logo() {
        return (<button className="brand" onClick={() => go("landing")} aria-label={__text("NATIVA \u2014 in\u00EDcio")}>
        <img src={A.imgLogoNativaEnviada} alt={__text("")}/>
        <strong>{__text("NATIVA")}</strong>
      </button>);
    }
    function Demo() {
        return (<p className="demo">{__text("DADOS DEMONSTRATIVOS")}{__text(" ")}
        <span>{__text("\u2022 Propriedade fict\u00EDcia. Valores ilustrativos, n\u00E3o s\u00E3o medi\u00E7\u00F5es reais nem recomenda\u00E7\u00F5es validadas.")}</span>
      </p>);
    }
    function Btn({ children, onClick, secondary = false, type = "button", }: {
        children: React.ReactNode;
        onClick?: () => void;
        secondary?: boolean;
        type?: "button" | "submit";
    }) {
        return (<button type={type} className={secondary ? "button secondary" : "button"} onClick={onClick}>
        {__text(children)}
      </button>);
    }
    function LinkButton({ children, onClick, }: {
        children: React.ReactNode;
        onClick: () => void;
    }) {
        return (<button className="text-link" onClick={onClick}>
        {__text(children)}
      </button>);
    }
    function Chart({ kind = "temperature", large = false, }: {
        kind?: keyof typeof series;
        large?: boolean;
    }) {
        const vals = series[kind]
            .slice(period === "6" ? 6 : 0)
            .map((x) => year === "2024" ? x * 0.93 : year === "2023" ? x * 1.04 : x);
        const color = {
            temperature: "#efae38",
            rain: "#8ebdc6",
            moisture: "#a8c9a3",
            ndvi: "#8ca53b",
        }[kind];
        const max = { temperature: 35, rain: 300, moisture: 60, ndvi: 1 }[kind];
        const minimum = kind === "temperature" ? 15 : 0;
        const plotY = (v: number) => 125 - ((v - minimum) / (max - minimum)) * 110;
        const positions = vals
            .map((v, i) => `${(i / (vals.length - 1)) * 300},${plotY(v)}`)
            .join(" ");
        return (<div className={"chart " + (large ? "chart-large" : "")}>
        <svg viewBox="0 0 350 174" role="img" aria-label={__text(`${kind === "rain" ? t("Precipitação") : kind === "temperature" ? t("Temperatura") : kind === "moisture" ? t("Umidade do solo") : "NDVI"} ${t("— valores demonstrativos de")} ${year}`)}>
          <g transform="translate(34 8)">
            {__text([15, 70, 125].map((y, i) => (<g key={y}>
                <line x1="0" x2="306" y1={y} y2={y} stroke="#28464b"/>
                <text x="-12" y={y + 3} textAnchor="end">
                  {__text(kind === "temperature"
                    ? [35, 25, 15][i]
                    : i === 2
                        ? "0"
                        : (max * (1 - i * 0.5)).toLocaleString(locale()))}
                </text>
              </g>)))}
            {__text(kind === "rain" ? (vals.map((v, i) => (<rect key={i} x={(i * 300) / vals.length + 2} y={plotY(v)} width={vals.length === 6 ? 13 : 9} height={(v / max) * 110} rx="3" fill={color}>
                  <title>
                    {__text(months[(period === "6" ? 6 : 0) + i])}{__text(":")}{__text(v.toFixed(0))}{__text("mm")}</title>
                </rect>))) : period === "12" &&
                year === "2025" &&
                !large &&
                kind !== "ndvi" ? (<image href={kind === "temperature"
                    ? A.imgCurvaDeTemperatura
                    : A.imgCurvaDeUmidadeDoSolo} x="0" y={kind === "temperature" ? 55 : 54} width="306" height={kind === "temperature" ? 43 : 33}/>) : (<polyline points={positions} fill="none" stroke={color} strokeWidth="2.2"/>))}
            {__text(large && (<>
                <rect x="275" y="20" width="31" height="100" fill="#9aadb0" opacity=".08"/>
                <path d={`M 250 ${plotY(vals[vals.length - 1])} L 300 28`} stroke={color} strokeDasharray="3 4" fill="none" opacity=".6"/>
              </>))}
            {__text((period === "6"
                ? ["Jul", "Ago", "Set", "Out", "Nov", "Dez"]
                : ["Jan", "Abr", "Jul", "Out", "Dez"]).map((m, i, arr) => (<text key={m} x={(i * 300) / (arr.length - 1)} y="151" textAnchor="middle">
                {__text(m)}
              </text>)))}
          </g>
        </svg>
        <small>{__text("\u25CF NASA")}{__text(" ")}
          {__text(kind === "moisture" ? "SMAP" : kind === "ndvi" ? "MODIS" : "POWER")}{__text("\u00B7 s\u00E9rie fict\u00EDcia")}</small>
      </div>);
    }
    function Map({ expanded = false }: {
        expanded?: boolean;
    }) {
        return (<div className={"farm-map " + (expanded ? "expanded" : "")}>
        <div className="map-image" style={{ transform: `scale(${zoom})` }}>
          <img src={A.imgPlanoGeografico} alt={__text("Vista a\u00E9rea ilustrativa de campos agr\u00EDcolas")}/>
          <img className="field-boundary" src={A.imgLimiteFicticio} alt={__text("Limite fict\u00EDcio da propriedade")}/>
        </div>
        <select className="map-layer" aria-label={__text("Camada do mapa")} value={layer} onChange={(e) => setLayer(e.target.value)}>
          {__text([
                "Vegetação (NDVI)",
                "Umidade do solo",
                "Precipitação",
                "Temperatura",
            ].map((x) => (<option key={x} value={x}>{__text(x)}</option>)))}
        </select>
        <div className="map-controls">
          <button aria-label={__text("Aproximar mapa")} onClick={() => setZoom((v) => Math.min(2.4, v + 0.2))}>{__text("+")}</button>
          <button aria-label={__text("Afastar mapa")} onClick={() => setZoom((v) => Math.max(1, v - 0.2))}>{__text("\u2212")}</button>
          <button aria-label={__text("Centralizar propriedade")} onClick={() => setZoom(1)}>{__text("\u2316")}</button>
        </div>
        <div className="map-farm">
          <strong>{__text(farm.name)}</strong>
          <small>{__text(farm.area)}{__text("ha \u2022 limite fict\u00EDcio")}</small>
        </div>
        <small className="map-disclaimer">{__text("Imagem ilustrativa \u2022 limites fict\u00EDcios, sem georreferenciamento")}</small>
        <div className="map-legend">
          <span>
            {__text(layer === "Vegetação (NDVI)"
                ? "NDVI · 0,2–0,9"
                : layer + " · exemplo")}
          </span>
          <div>
            {__text(["#c4ad70", "#c3d58b", "#90b66c", "#4d8153", "#315b3d"].map((c) => (<i key={c} style={{ background: c }}/>)))}
          </div>
        </div>
        <button className="map-fullscreen" aria-label={__text(expanded ? "Fechar mapa ampliado" : "Ampliar mapa")} onClick={() => open(expanded ? null : "map")}>
          <img src={A.imgTelaCheia} alt={__text("")}/>
        </button>
      </div>);
    }
    function ClimateSummary() {
        return (<section className="panel climate-summary">
        <div className="section-heading">
          <div>
            <h2>{__text("Como o clima est\u00E1 mudando?")}</h2>
            <p>{__text("Jan\u2013Dez")}{__text(year)}{__text("\u00B7 compara\u00E7\u00E3o entre meses \u00B7 valores demonstrativos")}</p>
          </div>
          <select aria-label={__text("Per\u00EDodo dos gr\u00E1ficos")} value={period} onChange={(e) => setPeriod(e.target.value)}>
            <option value="12">{__text("\u00DAltimos 12 meses")}</option>
            <option value="6">{__text("\u00DAltimos 6 meses")}</option>
          </select>
        </div>
        <div className="charts-three">
          {__text((["temperature", "rain", "moisture"] as const).map((kind, i) => (<div key={kind}>
              <div className="chart-title">
                <strong>
                  {__text(["Temperatura", "Precipitação", "Umidade do solo"][i])}
                </strong>
                <small>{__text(["°C", "mm/mês", "%"][i])}</small>
              </div>
              <Chart kind={kind}/>
            </div>)))}
        </div>
      </section>);
    }
    function MetricCards() {
        return (<div className="metrics">
        {__text([
                [
                    "Temperatura média",
                    settings.temperature.startsWith("Graus Fahrenheit")
                        ? "76,6"
                        : "24,8",
                    settings.temperature.startsWith("Graus Fahrenheit") ? "°F" : "°C",
                    "↗ +1,2 °C no histórico",
                    "POWER",
                ],
                [
                    "Precipitação acumulada",
                    "142",
                    "mm",
                    "↘ −18% no histórico",
                    "POWER",
                ],
                ["Umidade do solo", "32", "%", "↗ +4 p.p. no mês", "SMAP"],
                ["Índice de vegetação", "0,76", "NDVI", "↗ +0,08 no mês", "MODIS"],
            ].map((m, i) => (<button className="metric panel" key={m[0]} onClick={() => open("indicators")}>
            <span className="metric-title">{__text(m[0])}</span>
            <div className="metric-value">
              <motion.strong data-node-id={["3:330", "3:336", "3:342", "3:348"][i]} initial={reduced ? false : { opacity: 0.8, y: 3 }} animate={reduced
                    ? { opacity: 1, y: 0 }
                    : { opacity: [0.8, 1, 1], y: [3, 0, 0] }} transition={{
                    duration: 2,
                    times: [0, 0.325, 1],
                    ease: ["easeOut", "linear"],
                    repeat: Infinity,
                }}>
                {__text(m[1])}
              </motion.strong>
              <small>{__text(m[2])}</small>
            </div>
            <span className={"delta " + (i < 2 ? "warm" : "")}>{__text(m[3])}</span>
            <small className="metric-source">{__text("NASA")}{__text(m[4])}{__text("\u2022 exemplo")}</small>
            {__text(i === 0 ? (<img className="metric-spark" src={A.imgMinigraficoDeTemperatura} alt={__text("")}/>) : i === 1 ? (<div className="mini-bars">
                {__text([14, 24, 18, 35, 27, 42, 33].map((v, n) => (<i key={n} style={{ height: v }}/>)))}
              </div>) : i === 2 ? (<div className="metric-ring">
                <img src={A.imgUmidadeCircular} alt={__text("")}/>
                <img src={A.img32DeUmidade} alt={__text("")}/>
              </div>) : (<div className="ndvi-bars">
                {__text(Array.from({ length: 9 }, (_, n) => (<i key={n} style={{ opacity: n > 6 ? 0.25 : 1 }}/>)))}
              </div>))}
          </button>)))}
      </div>);
    }
    function Overview() {
        return (<>
        <div className="page-heading overview-heading">
          <div>
            <h1>{__text("Sua propriedade, uma nova perspectiva.")}</h1>
            <p>{__text("Explore sua fazenda com dados da NASA e descubra oportunidades para suas pr\u00F3ximas safras.")}</p>
          </div>
          <Btn onClick={() => go("rotation")}>{__text("\uFF0B Nova An\u00E1lise")}</Btn>
        </div>
        <Demo />
        <div className="overview-map">
          <Map />
          <aside className="farm-context">
            <h2>{__text(farm.name)}</h2>
            <p>
              {__text(farm.city)}{__text("\u00B7")}{__text(farm.country)}
            </p>
            <small>
              {__text(farm.latitude)}{__text("/")}{__text(farm.longitude)}{__text("\u2022 coordenadas fict\u00EDcias")}</small>
            <div className="current-context">
              <small>{__text("CULTIVO ATUAL")}</small>
              <strong>{__text(farm.crop)}</strong>
              <span>{__text("Talh\u00E3o 01 \u00B7")}{__text(farm.area)}{__text("ha")}</span>
            </div>
            <hr />
            <h3>{__text("Um novo olhar para o pr\u00F3ximo ciclo.")}</h3>
            <LinkButton onClick={() => go("farm")}>{__text("Ver minha propriedade \u2192")}</LinkButton>
            <LinkButton onClick={() => open("sources")}>{__text("Fontes e limita\u00E7\u00F5es \u2192")}</LinkButton>
          </aside>
        </div>
        <MetricCards />
        <button className="disclosure" aria-expanded={explain} onClick={() => setExplain(!explain)}>{__text("Entenda os indicadores")}<span>{__text(explain ? "−" : "⌄")}</span>
        </button>
        {__text(explain && (<div className="panel inline-info">
            {__text(info.indicators.items.map(([t, d]) => (<div key={t}>
                <h3>{__text(t)}</h3>
                <p>{__text(d)}</p>
              </div>)))}
          </div>))}
        <section className="plan-banner">
          <div>
            <h2>{__text("Planeje sua pr\u00F3xima safra.")}</h2>
            <p>{__text("Compare estrat\u00E9gias de rota\u00E7\u00E3o considerando o clima, o solo e as prioridades da sua propriedade.")}</p>
            <button className="button lime" onClick={() => go("rotation")}>{__text("Comparar estrat\u00E9gias \u2192")}</button>
          </div>
          <div className="banner-art">
            {__text([A.imgRotation, A.imgFieldRows, A.imgSprout, A.imgWarmAccent].map((src, i) => (<img key={src} className={"art-" + i} src={src} alt={__text("")}/>)))}
          </div>
        </section>
        <ClimateSummary />
        <button className="disclosure" aria-expanded={calendar} onClick={() => setCalendar(!calendar)}>{__text("Calend\u00E1rio agr\u00EDcola")}<span>{__text(calendar ? "−" : "⌄")}</span>
        </button>
        {__text(calendar && <Timeline />)}
      </>);
    }
    function FarmPage() {
        return (<form onSubmit={saveFarm}>
        <div className="page-heading">
          <div>
            <h1>{__text("Minha Propriedade")}</h1>
            <p>{__text("As caracter\u00EDsticas da sua terra s\u00E3o o ponto de partida.")}</p>
          </div>
          <Btn type="submit">{__text("Salvar altera\u00E7\u00F5es")}</Btn>
        </div>
        <Demo />
        <div className="two-col">
          <div className="stack">
            <section className="panel">
              <h2>{__text("01 Localiza\u00E7\u00E3o")}</h2>
              <p>{__text("Informe onde voc\u00EA cultiva. Os campos marcados s\u00E3o opcionais.")}</p>
              <div className="fields-grid">
                <Field label={__text("Nome da propriedade")} name="name"/>
                <Field label={__text("Pa\u00EDs")} name="country" options={[
                "Brasil",
                "Argentina",
                "Uruguai",
                "Paraguai",
                "Outro",
            ]}/>
                <div className="fields-grid">
                  <Field label={__text("Latitude")} name="latitude" type="number" min={-90} max={90} step="any"/>
                  <Field label={__text("Longitude")} name="longitude" type="number" min={-180} max={180} step="any"/>
                </div>
                <Field label={__text("\u00C1rea da propriedade (ha)")} name="area" type="number" min={0.01} step="any"/>
              </div>
              <div className="location-preview">
                <img src={assets["13:478"].imgLocalizacaoDemonstrativa} alt={__text("Localiza\u00E7\u00E3o ilustrativa da fazenda")}/>
                <span>{__text("\u2316")}{__text(draft.latitude)}{__text(",")}{__text(draft.longitude)}{__text("\u2022 exemplo")}</span>
              </div>
            </section>
            <section className="panel">
              <h2>{__text("02 Caracter\u00EDsticas do solo")}</h2>
              <div className="fields-grid">
                <Field label={__text("Textura do solo")} name="texture" options={[
                "Argiloso",
                "Arenoso",
                "Franco",
                "Siltoso",
                "Não informado",
            ]}/>
                <Field label={__text("pH do solo \u24D8")} name="ph" type="number" min={0} max={14} step=".1"/>
                <Field label={__text("Drenagem")} name="drainage" options={["Moderada", "Boa", "Baixa", "Não informado"]}/>
                <Field label={__text("Mat\u00E9ria org\u00E2nica (%) \u2022 opcional")} name="organic" type="number" min={0} max={100} step=".1"/>
              </div>
            </section>
            <section className="panel">
              <h2>{__text("03 Recursos h\u00EDdricos")}</h2>
              <div className="fields-grid">
                <Field label={__text("Disponibilidade de irriga\u00E7\u00E3o")} name="irrigation" options={["Sim", "Não", "Não informado"]}/>
                <Field label={__text("Tipo de irriga\u00E7\u00E3o")} name="irrigationType" options={[
                "Pivô central",
                "Gotejamento",
                "Aspersão",
                "Não se aplica",
                "Outro",
            ]}/>
                <div className="full">
                  <Field label={__text("Restri\u00E7\u00F5es de \u00E1gua \u2022 opcional")} name="waterRestriction"/>
                </div>
              </div>
            </section>
          </div>
          <aside className="stack">
            <section className="panel">
              <h2>{__text("Sua terra, em contexto")}</h2>
              <h3 className="farm-name">{__text(farm.name)}</h3>
              <p>
                {__text(farm.city)}{__text("\u2022")}{__text(farm.country)}
              </p>
              <dl>
                <div>
                  <dt>{__text("\u00C1rea total")}</dt>
                  <dd>{__text(farm.area)}{__text("ha")}</dd>
                </div>
                <div>
                  <dt>{__text("Talh\u00F5es cadastrados")}</dt>
                  <dd>{__text("1 talh\u00E3o")}</dd>
                </div>
                <div>
                  <dt>{__text("Informa\u00E7\u00F5es preenchidas")}</dt>
                  <dd>{__text(Object.values(draft).filter(Boolean).length)}{__text("campos")}</dd>
                </div>
              </dl>
            </section>
            <section className="panel">
              <h3>{__text("Por que pedimos estes dados?")}</h3>
              <p>{__text("Solo, \u00E1gua e localiza\u00E7\u00E3o ajudam a contextualizar os cen\u00E1rios de rota\u00E7\u00E3o.")}</p>
              <p>{__text("Voc\u00EA pode come\u00E7ar com o que sabe e completar os campos opcionais depois.")}</p>
              <small>{__text("\u24D8 Altera\u00E7\u00F5es mantidas somente nesta sess\u00E3o.")}</small>
            </section>
            <section className="panel">
              <h2>{__text("An\u00E1lise de solo")}</h2>
              <h3>{__text(report ? report.name : "Nenhum laudo anexado")}</h3>
              <p>{__text("Se tiver um laudo recente, adicione-o para consultar junto ao cadastro.")}</p>
              <label className="button upload">
                {__text(report ? "Substituir laudo" : "Adicionar laudo")}
                <input type="file" accept=".pdf,.png,.jpg,.jpeg" onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) {
                    setReport(f);
                    toast("Laudo selecionado localmente. Nenhum arquivo foi enviado.");
                }
            }}/>
              </label>
              {__text(report && (<button className="text-link" type="button" onClick={() => setReport(null)}>{__text("Remover arquivo")}</button>))}
              <small>{__text("Arquivo local \u2022 n\u00E3o enviado nem analisado automaticamente.")}</small>
            </section>
          </aside>
        </div>
        <p className="footnote">{__text("Seus dados ajudam a explorar possibilidades; n\u00E3o substituem uma avalia\u00E7\u00E3o agron\u00F4mica local.")}</p>
      </form>);
    }
    function Timeline() {
        return (<section className="panel timeline-panel">
        <div className="section-heading">
          <div>
            <h2>{__text("Uma vis\u00E3o de cada safra")}</h2>
            <p>{__text("Talh\u00E3o 01 \u2022")}{__text(farm.area)}{__text("ha \u2022 plantio, desenvolvimento e colheita")}</p>
          </div>
          <select aria-label={__text("Ano do calend\u00E1rio")} value={year} onChange={(e) => setYear(e.target.value)}>
            {__text(["2025", "2024", "2023"].map((y) => (<option key={y} value={y}>{__text(y)}</option>)))}
          </select>
        </div>
        <div className="timeline-scroll">
          <div className="timeline">
            <div className="timeline-labels">
              <span />
              {__text(months.map((m) => (<span key={m}>{__text(m)}</span>)))}
            </div>
            <div className="timeline-row">
              <strong>{__text("Soja")}{__text(Number(year) - 1)}{__text("/")}{__text(year.slice(2))}
              </strong>
              <div className="timeline-track">
                <span style={{ gridColumn: "1/3" }}>{__text("Desenvolvimento")}</span>
                <span className="harvest" style={{ gridColumn: "3/4" }}>{__text("Colheita")}</span>
                <span style={{ gridColumn: "10/11" }}>{__text("Plantio")}</span>
                <span style={{ gridColumn: "11/13" }}>{__text("Soja")}{__text(year)}{__text("/")}{__text(String(Number(year) + 1).slice(2))}
                </span>
              </div>
            </div>
            <div className="timeline-row">
              <strong>{__text("Milho safrinha")}</strong>
              <div className="timeline-track">
                <span style={{ gridColumn: "3/4" }}>{__text("Plantio")}</span>
                <span style={{ gridColumn: "4/7" }}>{__text("Desenvolvimento")}</span>
                <span className="harvest" style={{ gridColumn: "7/8" }}>{__text("Colheita")}</span>
                <span className="bare" style={{ gridColumn: "8/10" }}>{__text("Solo descoberto")}</span>
              </div>
            </div>
          </div>
        </div>
        <div className="legend">
          <span>{__text("\u25CF Plantio")}</span>
          <span>{__text("\u25CF Desenvolvimento")}</span>
          <span className="warm">{__text("\u25CF Colheita")}</span>
          <span>{__text("\u25CF Solo descoberto")}</span>
        </div>
      </section>);
    }
    function History() {
        const fmt = (s: string) => new Date(s + "T12:00:00").toLocaleDateString(locale());
        return (<>
        <div className="page-heading">
          <div>
            <h1>{__text("Hist\u00F3rico de Cultivo")}</h1>
            <p>{__text("Cada safra conta uma parte da hist\u00F3ria da sua terra.")}</p>
          </div>
          <Btn onClick={() => open("addCrop")}>{__text("\uFF0B Adicionar cultivo")}</Btn>
        </div>
        <Demo />
        <div className="grid-two">
          <section className="panel current-crop">
            <small>{__text("CULTIVO ATUAL \u2022 TALH\u00C3O 01")}</small>
            <div>
              <h2>{__text(farm.crop)}</h2>
              <span>{__text("Em crescimento")}</span>
            </div>
            <p>{__text("Plantio: 15 out 2025 \u2192 Colheita prevista: 20 fev 2026")}</p>
          </section>
          <section className="panel">
            <h2>{__text("Seu hist\u00F3rico em n\u00FAmeros")}</h2>
            <div className="numbers">
              <div>
                <strong>{__text(crops.length + 2)}</strong>
                <small>{__text("cultivos registrados")}</small>
              </div>
              <div>
                <strong>{__text("3")}</strong>
                <small>{__text("anos de hist\u00F3rico")}</small>
              </div>
              <div>
                <strong>{__text("2")}</strong>
                <small>{__text("cultivos por ano")}</small>
              </div>
            </div>
          </section>
        </div>
        <Timeline />
        <section className="panel">
          <h2>{__text("Cultivos registrados")}</h2>
          <p>{__text("Valores demonstrativos \u2022 produtividade informada em sacas de 60 kg por hectare")}</p>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  {__text([
                "Cultura / safra",
                "Plantio",
                "Colheita",
                "Área",
                "Produtividade",
                "Situação",
            ].map((t) => (<th key={t}>{__text(t)}</th>)))}
                </tr>
              </thead>
              <tbody>
                {__text(crops.map((c) => (<tr key={c.id}>
                    <td>
                      {__text(c.crop)}{__text("\u2022")}{__text(c.season)}
                    </td>
                    <td>{__text(fmt(c.plant))}</td>
                    <td>
                      {__text(fmt(c.harvest))}
                      {__text(c.status !== "Concluído" ? "*" : "")}
                    </td>
                    <td>{__text(c.area)}{__text("ha")}</td>
                    <td>
                      {__text(c.yield ? c.yield + " sc/ha" : "Ainda não colhida")}
                    </td>
                    <td>
                      <span className="status">{__text(c.status)}</span>
                    </td>
                  </tr>)))}
              </tbody>
            </table>
          </div>
          <small>{__text("* Data prevista, n\u00E3o observada. Mostrando")}{__text(crops.length)}{__text("de")}{__text(" ")}
            {__text(crops.length + 2)}{__text("cultivos.")}</small>
        </section>
        <section className="callout">
          <div>
            <h3>{__text("O pr\u00F3ximo ciclo come\u00E7a com o que voc\u00EA j\u00E1 aprendeu.")}</h3>
            <p>{__text("Use seu hist\u00F3rico para explorar estrat\u00E9gias de rota\u00E7\u00E3o.")}</p>
          </div>
          <Btn onClick={() => go("rotation")}>{__text("Explorar estrat\u00E9gias \u2192")}</Btn>
        </section>
      </>);
    }
    function Climate() {
        return (<>
        <div className="page-heading">
          <div>
            <h1>{__text("An\u00E1lise Clim\u00E1tica")}</h1>
            <p>{__text("Do hist\u00F3rico ao planejamento: entenda os sinais do clima.")}</p>
          </div>
        </div>
        <Demo />
        <div className="period-bar">
          <span>{__text("Per\u00EDodo de an\u00E1lise")}</span>
          <div>
            {__text(["2023", "2024", "2025"].map((y) => (<button key={y} className={year === y ? "active" : ""} onClick={() => {
                    setYear(y);
                    setPeriod("12");
                }}>
                {__text(y)}
              </button>)))}
          </div>
          <small>{__text("\u25CF Hist\u00F3rico ilustrativo")}</small>
          <small className="warm">{__text("Estimativa ilustrativa")}</small>
          <small>{__text("Proje\u00E7\u00E3o ilustrativa")}</small>
        </div>
        <div className="grid-two climate-grid">
          {__text((["temperature", "rain", "moisture", "ndvi"] as const).map((kind, i) => (<section className="panel" key={kind}>
                <div className="section-heading">
                  <div>
                    <h2>
                      {__text([
                    "Temperatura média",
                    "Precipitação acumulada",
                    "Umidade do solo ⓘ",
                    "Vigor da vegetação ⓘ",
                ][i])}
                    </h2>
                    <p>{__text("NASA")}{__text(i === 2 ? "SMAP" : i === 3 ? "MODIS" : "POWER")}{__text("\u2022 exemplo de s\u00E9rie hist\u00F3rica")}</p>
                  </div>
                  <strong className={"climate-number n" + i}>
                    {__text([
                    year === "2025"
                        ? "24,8 °C"
                        : year === "2024"
                            ? "23,1 °C"
                            : "25,8 °C",
                    year === "2025"
                        ? "142 mm"
                        : year === "2024"
                            ? "132 mm"
                            : "148 mm",
                    "32%",
                    "0,76",
                ][i])}
                  </strong>
                </div>
                <Chart kind={kind} large/>
                <p>
                  {__text([
                    "Meses mais quentes podem aumentar a demanda por água.",
                    "A chuva se concentra entre outubro e março neste exemplo.",
                    "Água na camada superficial; não representa toda a zona de raízes.",
                    "NDVI indica atividade da vegetação, não rendimento da safra.",
                ][i])}
                </p>
              </section>)))}
        </div>
        <div className="two-col">
          <section className="panel">
            <h2>{__text("Planeje com a sazonalidade")}</h2>
            <p>{__text("Padr\u00E3o ilustrativo \u2022 n\u00E3o \u00E9 previs\u00E3o meteorol\u00F3gica")}</p>
            <div className="season wet">
              <strong>{__text("Out\u2013Mar")}</strong>
              <div>{__text("Per\u00EDodo mais chuvoso")}<small>{__text("Aten\u00E7\u00E3o \u00E0 drenagem e \u00E0 janela de plantio.")}</small>
              </div>
            </div>
            <div className="season dry">
              <strong>{__text("Mai\u2013Ago")}</strong>
              <div>{__text("Per\u00EDodo mais seco")}<small>{__text("Cobertura do solo ajuda a reduzir evapora\u00E7\u00E3o.")}</small>
              </div>
            </div>
          </section>
          <section className="panel">
            <h2>{__text("Antes de decidir")}</h2>
            <h3>{__text("Hist\u00F3rico")}</h3>
            <p>{__text("Observa\u00E7\u00F5es passadas, aqui representadas por exemplos fict\u00EDcios.")}</p>
            <h3 className="warm">{__text("Estimativas e proje\u00E7\u00F5es")}</h3>
            <p>{__text("S\u00E3o aproxima\u00E7\u00F5es com incerteza. Linhas tracejadas n\u00E3o s\u00E3o observa\u00E7\u00F5es.")}</p>
          </section>
        </div>
        <section className="callout">
          <div>
            <h3>{__text("\u24D8 Fontes, resolu\u00E7\u00E3o e limita\u00E7\u00F5es dos indicadores")}</h3>
            <p>{__text("Explore a diferen\u00E7a entre a escala do sat\u00E9lite e a escala do talh\u00E3o.")}</p>
          </div>
          <LinkButton onClick={() => open("sources")}>{__text("Ver detalhes \u2192")}</LinkButton>
        </section>
      </>);
    }
    function Radar() {
        const R = assets["3:218"];
        return (<div className="radar-assets" role="img" aria-label={__text("Compara\u00E7\u00E3o ilustrativa dos quatro crit\u00E9rios")}>
        <div className="radar-shapes">
          {__text([
                R.imgEixoDeComparacao,
                R.imgEixoDeComparacao1,
                R.imgEixoDeComparacao2,
                R.imgEixoDeComparacao3,
                R.imgEixoDeComparacao4,
            ].map((src, i) => (<img key={src} className={"radar-axis axis-" + i} src={src} alt={__text("")}/>)))}
          <img className="radar-current" src={R.imgAreaDoCenario} alt={__text("")}/>
          <img className="radar-soil" src={R.imgAreaDoCenario1} alt={__text("")}/>
          <img className="radar-climate" src={R.imgAreaDoCenario2} alt={__text("")}/>
        </div>
        <span className="radar-water">{__text("\u00C1gua")}</span>
        <span className="radar-soil-label">{__text("Solo")}</span>
        <span className="radar-profit">{__text("Rentabilidade")}</span>
        <span className="radar-resilience">{__text("Resili\u00EAncia")}</span>
      </div>);
    }
    function Rotation() {
        return (<>
        <div className="page-heading">
          <div>
            <h1>{__text("Estrat\u00E9gias de Rota\u00E7\u00E3o")}</h1>
            <p>{__text("Compare caminhos para a pr\u00F3xima safra, com as suas prioridades.")}</p>
          </div>
        </div>
        <Demo />
        <section className="panel priorities">
          <h2>{__text("01 O que importa mais para a sua pr\u00F3xima safra?")}</h2>
          <p>{__text("Ajuste os controles ou explore os tr\u00EAs perfis predefinidos de prioridade.")}</p>
          <div className="sliders">
            {__text([
                "Economia de água",
                "Saúde do solo",
                "Rentabilidade",
                "Resiliência climática",
            ].map((label, i) => (<label key={label}>
                <span>
                  {__text(label)}
                  <strong>{__text(weights[i])}{__text("%")}</strong>
                </span>
                <input type="range" min="0" max="100" value={weights[i]} aria-label={__text(label)} onChange={(e) => setWeights((prev) => prev.map((v, n) => (n === i ? +e.target.value : v)))}/>
                <small>{__text("Menor")}<span>{__text("Maior")}</span>
                </small>
              </label>)))}
          </div>
          <div className="profile-buttons">
            {__text(([
                ["soil", "Solo equilibrado"],
                ["water", "Água e clima"],
                ["profit", "Rentabilidade"],
            ] as const).map(([key, label]) => (<button key={key} className={weights.every((v, i) => v === profiles[key][i])
                    ? "active"
                    : ""} onClick={() => setWeights([...profiles[key]])}>
                {__text(label)}
              </button>)))}
          </div>
        </section>
        <div className="section-heading scenarios-heading">
          <div>
            <h2>{__text("02 Compare os cen\u00E1rios")}</h2>
            <p>{__text("Pontua\u00E7\u00F5es ilustrativas ponderadas pelos objetivos acima.")}</p>
          </div>
          <button className="button" onClick={compare} disabled={busy}>
            {__text(busy ? "Comparando…" : "Comparar Estratégias")}
          </button>
        </div>
        <div className="scenario-grid">
          {__text(scenarios.map((s, i) => (<article className={"scenario panel " + (winner === i ? "recommended" : "")} key={s.name}>
              <div className="scenario-ribbon">
                {__text(winner === i
                    ? "MAIOR ADERÊNCIA AOS SEUS PESOS"
                    : i === 0
                        ? "Referência de comparação"
                        : "Alternativa para explorar")}
              </div>
              <h2>{__text(s.name)}</h2>
              <div className="score">
                <strong style={{ color: s.color }}>{__text(chosen[i])}</strong>
                <small>{__text("/ 100")}</small>
                <small>{__text("ader\u00EAncia ilustrativa \u24D8")}</small>
              </div>
              <h3>{__text(s.sequence)}</h3>
              <small>{__text("CALEND\u00C1RIO DO CEN\u00C1RIO \u2022 12 MESES")}</small>
              <div className="mini-calendar">
                {__text(months.map((m, n) => (<div key={n}>
                    <span>{__text(m[0])}</span>
                    <i style={{
                        background: n === 7 || n === 8
                            ? i === 0
                                ? "#e8e4d7"
                                : i === 2
                                    ? "#e9bc6c"
                                    : "#a8c477"
                            : "#365f44",
                    }}/>
                  </div>)))}
              </div>
              <small>{__text(s.calendar)}</small>
              <dl>
                <div>
                  <dt>{__text("\u00C1gua")}</dt>
                  <dd>{__text(s.water)}</dd>
                </div>
                <div>
                  <dt>{__text("Solo")}</dt>
                  <dd>{__text(s.soil)}</dd>
                </div>
                <div>
                  <dt>{__text("Clima")}</dt>
                  <dd>{__text(s.climate)}</dd>
                </div>
              </dl>
              <div className="benefit">
                <small>{__text("BENEF\u00CDCIO POTENCIAL")}</small>
                <p>{__text(s.benefit)}</p>
              </div>
              <div className="risk">
                <small>{__text("PONTO DE ATEN\u00C7\u00C3O")}</small>
                <p>{__text(s.risk)}</p>
              </div>
              <Btn onClick={() => open(i)} secondary={winner !== i}>{__text("Entender este cen\u00E1rio \u2192")}</Btn>
            </article>)))}
        </div>
        <div className="grid-two compare-bottom">
          <section className="panel">
            <h2>{__text("Os objetivos, lado a lado")}</h2>
            <p>{__text("Escala relativa: 0\u2013100 \u2022 maior = maior ader\u00EAncia")}</p>
            <Radar />
            <div className="legend">
              {__text(scenarios.map((s) => (<span key={s.name} style={{ color: s.color }}>{__text("\u25A0")}{__text(s.name)}
                </span>)))}
            </div>
          </section>
          <section className="panel green-panel">
            <h2>{__text("Por que esta estrat\u00E9gia foi sugerida?")}</h2>
            <p className="body-text">
              {__text(scenarios[winner].name)}{__text("teve maior ader\u00EAncia aos pesos deste exemplo.")}</p>
            <p>{__text(scenarios[winner].detail)}</p>
            <h3>{__text("Como a pontua\u00E7\u00E3o funciona")}</h3>
            <p>{__text("M\u00E9dia ponderada das quatro notas do cen\u00E1rio. Notas e pesos s\u00E3o demonstrativos e n\u00E3o representam um modelo validado.")}</p>
            <LinkButton onClick={() => open("sources")}>{__text("Ver premissas e limita\u00E7\u00F5es \u2192")}</LinkButton>
          </section>
        </div>
        <MotorPanel weights={applied} latitude={farm.latitude} longitude={farm.longitude} />
        <p className="footnote">{__text("Nenhum cen\u00E1rio \u00E9 uma recomenda\u00E7\u00E3o absoluta. Confirme a viabilidade com assist\u00EAncia agron\u00F4mica e dados locais antes de decidir.")}</p>
      </>);
    }
    function Settings() {
        return (<>
        <div className="page-heading">
          <div>
            <h1>{__text("Configura\u00E7\u00F5es")}</h1>
            <p>{__text("Controle suas prefer\u00EAncias e a origem dos dados.")}</p>
          </div>
          <Btn onClick={() => toast("Preferências aplicadas nesta sessão.")}>{__text("Salvar ajustes")}</Btn>
        </div>
        <Demo />
        <div className="two-col">
          <div className="stack">
            <section className="panel">
              <h2>{__text("Prefer\u00EAncias de leitura")}</h2>
              <dl className="preferences">
                <div>
                  <dt>{__text("Idioma")}</dt>
                  <dd><LanguageSwitcher /></dd>
                </div>
                <div>
                  <dt>{__text("Temperatura")}</dt>
                  <dd>
                    <select aria-label={__text("Unidade de temperatura")} value={settings.temperature} onChange={(e) => setSettings((v) => ({
                ...v,
                temperature: e.target.value,
            }))}>
                      <option value={"Graus Celsius (\u00B0C)"}>{__text("Graus Celsius (\u00B0C)")}</option>
                      <option value={"Graus Fahrenheit (\u00B0F)"}>{__text("Graus Fahrenheit (\u00B0F)")}</option>
                    </select>
                  </dd>
                </div>
                <div>
                  <dt>{__text("\u00C1rea e produtividade")}</dt>
                  <dd>{__text("Hectares \u2022 sacas de 60 kg / ha")}</dd>
                </div>
                <div>
                  <dt>{__text("Precipita\u00E7\u00E3o")}</dt>
                  <dd>{__text("Mil\u00EDmetros (mm)")}</dd>
                </div>
              </dl>
            </section>
            <section className="panel">
              <h2>{__text("Fontes de refer\u00EAncia")}</h2>
              <p className="warm">{__text("Nenhuma fonte est\u00E1 conectada nesta vers\u00E3o.")}</p>
              <dl className="source-list">
                <div>
                  <dt>{__text("NASA POWER")}</dt>
                  <dd>{__text("Clima \u2022 temperatura e precipita\u00E7\u00E3o")}</dd>
                </div>
                <div>
                  <dt>{__text("NASA SMAP")}</dt>
                  <dd>{__text("Umidade superficial do solo")}</dd>
                </div>
                <div>
                  <dt>{__text("NASA MODIS")}</dt>
                  <dd>{__text("Vegeta\u00E7\u00E3o \u2022 exemplo de \u00EDndice NDVI")}</dd>
                </div>
              </dl>
              <LinkButton onClick={() => open("sources")}>{__text("Consultar documenta\u00E7\u00E3o e limita\u00E7\u00F5es \u2192")}</LinkButton>
            </section>
          </div>
          <aside className="stack">
            <section className="panel green-panel">
              <h2>{__text("Voc\u00EA est\u00E1 no controle")}</h2>
              <p>{__text("Este \u00E9 um ambiente demonstrativo. A fazenda, os cultivos, os indicadores e os cen\u00E1rios s\u00E3o fict\u00EDcios.")}</p>
              <p>{__text("As altera\u00E7\u00F5es ficam apenas na mem\u00F3ria desta sess\u00E3o. N\u00E3o h\u00E1 conta real, sincroniza\u00E7\u00E3o ou envio de documentos.")}</p>
              <small>{__text("NASA Space Apps Challenge 2026")}<br />{__text("Projeto NATIVA")}</small>
            </section>
            <section className="panel">
              <h2>{__text("Come\u00E7ar de novo")}</h2>
              <p>{__text("Volte \u00E0 vis\u00E3o geral para explorar o fluxo.")}</p>
              <LinkButton onClick={() => go("overview")}>{__text("Voltar \u00E0 vis\u00E3o geral \u2192")}</LinkButton>
            </section>
          </aside>
        </div>
      </>);
    }
    function Landing() {
        const heroImgs = [
            L.imgFotografiaComZoomSuave,
            L.imgFotografiaComZoomSuave1,
            L.imgFotografiaComZoomSuave2,
        ];
        return (<div className="landing">
        <nav className="landing-nav">
          <Logo />
          <LanguageSwitcher />
          <div>
            <a href="#como-funciona" onClick={(e) => {
                e.preventDefault();
                document.getElementById("como-funciona")?.scrollIntoView({
                    behavior: reduced ? "instant" : "smooth",
                });
            }}>{__text("Como funciona")}</a>
            <a href="#tecnologia" onClick={(e) => {
                e.preventDefault();
                document.getElementById("tecnologia")?.scrollIntoView({
                    behavior: reduced ? "instant" : "smooth",
                });
            }}>{__text("Tecnologia")}</a>
            <button onClick={() => open("technology")}>{__text("Sobre n\u00F3s")}</button>
          </div>
        </nav>
        <section className="hero" aria-label={__text("Destaques NATIVA")} aria-roledescription={__text("carrossel")} onFocusCapture={() => setCarouselFocused(true)} onBlurCapture={(event) => {
                if (!event.currentTarget.contains(event.relatedTarget as Node | null))
                    setCarouselFocused(false);
            }}>
          {__text(heroImgs.map((src, index) => (<img key={src} className={`hero-photo${slide === index ? " hero-photo-active" : ""}`} src={src} alt={__text(slide === index ? "Paisagem agrícola em destaque" : "")} aria-hidden={slide !== index} fetchPriority={index === 0 ? "high" : "auto"} decoding="async"/>)))}
          <div className="hero-shade"/>
          <div className="hero-content">
            <small>{__text("INTELIG\u00CANCIA QUE VEM DO ESPA\u00C7O")}</small>
            <h1>
              {__text([
                "O futuro da sua\nlavoura começa aqui.",
                "Um novo olhar\npara a sua terra.",
                "Da observação\nà próxima safra.",
            ][slide])}
            </h1>
            <p>{__text("Transforme dados espaciais em decis\u00F5es inteligentes para sua propriedade.")}</p>
            <div>
              <button className="button yellow" onClick={() => go("signup")}>{__text("Come\u00E7ar gratuitamente \u2192")}</button>
              <button className="button outline" onClick={() => go("overview")}>{__text("Conhecer a plataforma")}</button>
            </div>
          </div>
          <div className="carousel-controls">
            <div>
              {__text(heroImgs.map((_, i) => (<button key={i} aria-label={__text("Ir para imagem " + (i + 1))} aria-pressed={slide === i} className={slide === i ? "active" : ""} onClick={() => setSlide(i)}/>)))}
              <small>{__text("0")}{__text(slide + 1)}{__text("/ 03")}</small>
            </div>
            <div>
              {__text(!reduced && <button aria-label={__text(carouselPaused ? "Retomar troca automática de imagens" : "Pausar troca automática de imagens")} aria-pressed={carouselPaused} onClick={() => { setCarouselPaused((paused) => !paused); setCarouselFocused(false); }}>{__text(carouselPaused ? "▶" : "Ⅱ")}</button>)}
              <button aria-label={__text("Imagem anterior")} onClick={() => setSlide((current) => (current + 2) % 3)}>{__text("\u2039")}</button>
              <button aria-label={__text("Pr\u00F3xima imagem")} onClick={() => setSlide((current) => (current + 1) % 3)}>{__text("\u203A")}</button>
            </div>
          </div>
        </section>
        <ClimateStory calmImage={L.imgFotografiaComZoomSuave}/>
        <SolutionStory earth={L.imgFotografiaComZoomSuave1} field={L.imgFotografiaComZoomSuave2} onExplore={() => go("overview")}/>
        <section className="how-it-works" id="como-funciona">
          <small>{__text("SIMPLES DE USAR. AMPLO EM POSSIBILIDADES.")}</small>
          <h2>{__text("Da observa\u00E7\u00E3o \u00E0 decis\u00E3o.")}</h2>
          <div className="steps">
            {__text([
                [
                    "Localize sua propriedade.",
                    "Comece pela sua terra. Informe onde você cultiva e o seu contexto.",
                    L.imgIconeDoPasso1,
                ],
                [
                    "Explore as condições ambientais.",
                    "Veja clima, umidade e vegetação com uma nova perspectiva.",
                    L.imgIconeDoPasso2,
                ],
                [
                    "Compare estratégias de rotação.",
                    "Explore caminhos para o próximo ciclo com as suas prioridades.",
                    L.imgIconeDoPasso3,
                ],
            ].map(([t, d, img], i) => (<article key={t}>
                <span>{__text("0")}{__text(i + 1)}</span>
                <img src={img} alt={__text("")}/>
                <h3>{__text(t)}</h3>
                <p>{__text(d)}</p>
              </article>)))}
          </div>
          <LinkButton onClick={() => go("overview")}>{__text("Comece pela nossa propriedade \u2192")}</LinkButton>
        </section>
        <section className="space-section" id="tecnologia">
          <img src={L.imgFotografiaComZoomSuave1} alt={__text("A Terra vista do espa\u00E7o")}/>
          <div>
            <small>{__text("TECNOLOGIA NASA. CONTEXTO LOCAL.")}</small>
            <h2>{__text("Uma nova perspectiva")}<br />{__text("sobre sua lavoura.")}</h2>
            <h3>{__text("A observa\u00E7\u00E3o da Terra nos ajuda a enxergar al\u00E9m do que est\u00E1 \u00E0 vista.")}</h3>
            <p>{__text("A NATIVA utiliza dados de observa\u00E7\u00E3o da NASA para explorar condi\u00E7\u00F5es ambientais e apoiar decis\u00F5es agr\u00EDcolas, integrando o espa\u00E7o, o contexto e a realidade da sua propriedade.")}</p>
            <LinkButton onClick={() => open("technology")}>{__text("Conhe\u00E7a nossa tecnologia \u2192")}</LinkButton>
            <div className="source-chips">
              {__text(["POWER", "SMAP", "MODIS"].map((s) => (<span key={s}>
                  {__text(s)}
                  <small>{__text("NASA \u00B7 refer\u00EAncia")}</small>
                </span>)))}
            </div>
          </div>
        </section>
        <section className="about-section">
          <div>
            <small>{__text("SOBRE O PROJETO")}</small>
            <h2>{__text("Tecnologia espacial.")}<br />{__text("Prop\u00F3sito no campo.")}</h2>
          </div>
          <div>
            <p>{__text("Desenvolvido para o NASA Space Apps Challenge 2026, a NATIVA explora novas formas de usar dados de observa\u00E7\u00E3o da Terra para ampliar as possibilidades do produtor rural.")}</p>
            <LinkButton onClick={() => open("technology")}>{__text("Ci\u00EAncia aberta. Possibilidades para o campo.")}</LinkButton>
          </div>
        </section>
        <section className="landing-cta">
          <img src={L.imgFotografiaComZoomSuave2} alt={__text("Campos de cultivo")}/>
          <div>
            <small>{__text("DO SEU CAMPO PARA O FUTURO.")}</small>
            <h2>{__text("Sua pr\u00F3xima safra come\u00E7a")}<br />{__text("com uma decis\u00E3o.")}</h2>
            <p>{__text("Descubra novas possibilidades para sua propriedade.")}</p>
            <button className="button yellow" onClick={() => go("signup")}>{__text("Come\u00E7ar gratuitamente \u2192")}</button>
            <small>{__text("Explore a demonstra\u00E7\u00E3o gratuitamente.")}</small>
          </div>
        </section>
        <footer>
          <Logo />
          <div>
            <button onClick={() => open("technology")}>{__text("Sobre o projeto")}</button>
            <button onClick={() => open("technology")}>{__text("Tecnologia")}</button>
            <button onClick={() => open("contact")}>{__text("Contato")}</button>
          </div>
          <small>{__text("NASA Space Apps Challenge 2026")}</small>
          <small>{__text("Prot\u00F3tipo demonstrativo \u2022 dados fict\u00EDcios e cen\u00E1rios sem valida\u00E7\u00E3o local.")}</small>
        </footer>
      </div>);
    }
    function Signup() {
        return (<div className="signup">
        <section className="signup-photo">
          <img src={L.imgFotografiaComZoomSuave2} alt={__text("Fazenda ao amanhecer")}/>
          <Logo />
          <div>
            <h1>{__text("Sua terra merece")}<br />{__text("um novo olhar.")}</h1>
            <p>{__text("Da observa\u00E7\u00E3o do espa\u00E7o \u00E0s possibilidades")}<br />{__text("da sua pr\u00F3xima safra.")}</p>
          </div>
        </section>
        <section className="signup-form">
          <div className="signup-language"><LanguageSwitcher /></div>
          <button className="back-link" onClick={() => go("landing")}>{__text("Voltar ao in\u00EDcio")}</button>
          <small>{__text("01 / 02 \u2022 SEU CADASTRO")}</small>
          <h1>{__text("Comece pela sua")}<br />{__text("propriedade.")}</h1>
          <p>{__text("Uma vis\u00E3o mais ampla come\u00E7a com o seu contexto.")}</p>
          <form onSubmit={(e) => {
                e.preventDefault();
                go("onboard");
            }}>
            <label className="field">
              <span>{__text("Seu nome")}</span>
              <input value={userName} onChange={(e) => setUserName(e.target.value)} required/>
            </label>
            <label className="field">
              <span>{__text("E-mail")}</span>
              <input type="email" placeholder={__text("produtor@example.com")}/>
            </label>
            <Field label={__text("Nome da propriedade")} name="name"/>
            <div className="signup-location">
              <Field label={__text("Cidade / UF")} name="city"/>
              <Field label={__text("\u00C1rea (ha) \u2022 opcional")} name="area" type="number" min={0.01} step="any"/>
            </div>
            <button className="button yellow" type="submit">{__text("Continuar \u2192")}</button>
            <small>{__text("Ambiente demonstrativo. Nenhuma conta ser\u00E1 criada ou armazenada.")}</small>
          </form>
          <LinkButton onClick={() => open("login")}>{__text("J\u00E1 conhece a NATIVA? Entrar")}</LinkButton>
        </section>
      </div>);
    }
    function Onboard() {
        return (<div className="onboard">
        <header>
          <Logo />
          <LanguageSwitcher />
          <LinkButton onClick={() => go("signup")}>{__text("Voltar ao cadastro")}</LinkButton>
        </header>
        <div className="onboard-grid">
          <section>
            <small>{__text("02 / 02 \u2022 SUA PROPRIEDADE")}</small>
            <h1>{__text("Vamos conhecer")}<br />{__text("a sua terra.")}</h1>
            <p>{__text("Confirme o contexto para explorar a plataforma.")}</p>
            <div className="onboard-map">
              <img src={assets["13:478"].imgLocalizacaoDemonstrativa} alt={__text("Localiza\u00E7\u00E3o demonstrativa")}/>
              <span>{__text("\u2316")}{__text(draft.name)}
                <small>
                  {__text(draft.city)}{__text("\u00B7")}{__text(draft.area)}{__text("ha \u00B7 exemplo")}</small>
              </span>
            </div>
          </section>
          <form onSubmit={(e) => {
                e.preventDefault();
                setFarm({ ...draft });
                go("overview");
                toast(`${t("Bem-vinda")}, ${userName.split(" ")[0]}. ${t("Explore sua propriedade!")}`);
            }}>
            <Field label={__text("Cultura atual")} name="crop" options={["Soja", "Milho", "Sorgo", "Café", "Trigo", "Outra"]}/>
            <Field label={__text("Textura do solo")} name="texture" options={["Argiloso", "Arenoso", "Franco", "Não informado"]}/>
            <Field label={__text("Disponibilidade de irriga\u00E7\u00E3o")} name="irrigation" options={["Sim", "Não", "Não informado"]}/>
            <button className="button yellow" type="submit">{__text("Explorar plataforma \u2192")}</button>
            <small>{__text("Fluxo demonstrativo. As condi\u00E7\u00F5es n\u00E3o representam uma fazenda real.")}</small>
          </form>
        </div>
      </div>);
    }
    function AddCrop() {
        const [value, setValue] = useState({
            crop: "Milho",
            plant: "2026-03-05",
            harvest: "2026-07-28",
            area: farm.area,
            yield: "",
        });
        const [error, setError] = useState("");
        return (<form onSubmit={(e) => {
                e.preventDefault();
                if (value.harvest < value.plant) {
                    setError("A colheita deve ocorrer após o plantio.");
                    return;
                }
                setCrops((p) => [
                    {
                        ...value,
                        id: Date.now(),
                        season: value.plant.slice(0, 4),
                        status: value.yield ? "Concluído" : "Planejado",
                    },
                    ...p,
                ]);
                setModal(null);
                toast("Cultivo adicionado nesta sessão.");
            }}>
        <h2>{__text("Adicionar cultivo")}</h2>
        <p>{__text("Registre um exemplo para explorar o hist\u00F3rico da propriedade.")}</p>
        <div className="fields-grid">
          <label className="field">
            <span>{__text("Cultura")}</span>
            <select value={value.crop} onChange={(e) => setValue((v) => ({ ...v, crop: e.target.value }))}>
              {__text([
                "Milho",
                "Soja",
                "Sorgo",
                "Crotalária",
                "Braquiária",
                "Trigo",
            ].map((c) => (<option key={c} value={c}>{__text(c)}</option>)))}
            </select>
          </label>
          <label className="field">
            <span>{__text("Talh\u00E3o")}</span>
            <select>
              <option value={"Talh\u00E3o 01"}>{__text("Talh\u00E3o 01")}</option>
            </select>
          </label>
          {__text((["plant", "harvest", "area", "yield"] as const).map((key, i) => (<label className="field" key={key}>
              <span>
                {__text([
                    "Data de plantio",
                    "Data de colheita • prevista",
                    "Área cultivada (ha)",
                    "Produtividade (sc/ha) • opcional",
                ][i])}
              </span>
              <input type={i < 2 ? "date" : "number"} min={i > 1 ? 0 : undefined} step={i > 1 ? "any" : undefined} value={value[key]} required={key !== "yield"} onChange={(e) => setValue((v) => ({ ...v, [key]: e.target.value }))}/>
            </label>)))}
        </div>
        {__text(error && (<p className="error" role="alert">
            {__text(error)}
          </p>))}
        <p>{__text("As datas podem coexistir com outros cultivos no mesmo ano.")}</p>
        <button type="submit" className="button">{__text("Salvar cultivo")}</button>
        <small>{__text("Dados mantidos somente nesta sess\u00E3o.")}</small>
      </form>);
    }
    function ModalContent() {
        if (modal === "addCrop")
            return <AddCrop />;
        if (modal === "map")
            return (<>
          <h2>{__text("Mapa \u2022")}{__text(layer)}</h2>
          <p>{__text("Camada demonstrativa \u2022 valores e \u00E1reas sem georreferenciamento.")}</p>
          <Map expanded/>
        </>);
        if (typeof modal === "number") {
            const s = scenarios[modal];
            return (<>
          <h2>{__text(s.name)}</h2>
          <h3>{__text(s.sequence)}</h3>
          <h3>{__text("Fundamento agron\u00F4mico")}</h3>
          <p>{__text(s.detail)}</p>
          <h3>{__text("Benef\u00EDcio potencial")}</h3>
          <p>{__text(s.benefit)}</p>
          <h3>{__text("Riscos e condi\u00E7\u00F5es")}</h3>
          <p>{__text(s.risk)}</p>
          <small>{__text("Hip\u00F3teses gerais, sem valida\u00E7\u00E3o para esta propriedade fict\u00EDcia.")}</small>
          <Btn onClick={() => open(null)}>{__text("Voltar")}</Btn>
        </>);
        }
        if (modal === "account")
            return (<>
          <h2>{__text("Sua conta")}</h2>
          <h3>{__text("Perfil de demonstra\u00E7\u00E3o")}</h3>
          <p>{__text("Explore a experi\u00EAncia sem criar uma conta real. As altera\u00E7\u00F5es ficam somente nesta sess\u00E3o.")}</p>
          <LinkButton onClick={() => go("settings")}>{__text("Configura\u00E7\u00F5es da conta \u2192")}</LinkButton>
        </>);
        if (modal === "property")
            return (<>
          <h2>{__text("Selecionar propriedade")}</h2>
          <button className="property-choice" onClick={() => open(null)}>
            <strong>{__text(farm.name)}{__text("\u2713")}</strong>
            <small>
              {__text(farm.city)}{__text("\u2022")}{__text(farm.area)}{__text("ha")}</small>
          </button>
          <p>{__text("Uma propriedade est\u00E1 dispon\u00EDvel nesta demonstra\u00E7\u00E3o.")}</p>
          <LinkButton onClick={() => go("farm")}>{__text("Editar propriedade \u2192")}</LinkButton>
        </>);
        if (modal === "login")
            return (<>
          <h2>{__text("Bem-vinda \u00E0 NATIVA")}</h2>
          <p>{__text("Entre na experi\u00EAncia demonstrativa. Nenhuma autentica\u00E7\u00E3o ou conta real \u00E9 necess\u00E1ria.")}</p>
          <form onSubmit={(e) => {
                    e.preventDefault();
                    go("overview");
                }}>
            <label className="field">
              <span>{__text("E-mail \u2022 opcional")}</span>
              <input type="email" placeholder={__text("produtor@example.com")}/>
            </label>
            <button type="submit" className="button yellow">{__text("Explorar demonstra\u00E7\u00E3o \u2192")}</button>
          </form>
        </>);
        if (modal === "contact")
            return (<>
          <h2>{__text("Vamos conversar?")}</h2>
          <p>{__text("Formul\u00E1rio demonstrativo: esta vers\u00E3o n\u00E3o envia mensagens.")}</p>
          <form onSubmit={(e) => {
                    e.preventDefault();
                    toast("Demonstração concluída. Nenhuma mensagem foi enviada.");
                    open(null);
                }}>
            <label className="field">
              <span>{__text("Seu nome")}</span>
              <input required placeholder={__text("Seu nome")}/>
            </label>
            <label className="field">
              <span>{__text("Seu e-mail")}</span>
              <input required type="email" placeholder={__text("produtor@example.com")}/>
            </label>
            <label className="field">
              <span>{__text("Sua mensagem")}</span>
              <textarea required placeholder={__text("Quero conhecer a NATIVA.")}/>
            </label>
            <button className="button yellow" type="submit">{__text("Concluir demonstra\u00E7\u00E3o")}</button>
          </form>
        </>);
        if (modal && modal in info) {
            const data = info[modal as keyof typeof info];
            return (<>
          <h2>{__text(data.title)}</h2>
          <p>{__text(data.subtitle)}</p>
          {__text(data.items.map(([t, d]) => (<section className="info-item" key={t}>
              <h3>{__text(t)}</h3>
              <p>{__text(d)}</p>
            </section>)))}
          <Btn onClick={() => open(null)}>{__text("Entendi")}</Btn>
        </>);
        }
        return null;
    }
    const inDashboard = !["landing", "signup", "onboard"].includes(page);
    return (<DraftContext.Provider value={{ draft, setDraft }}>
      {__text(page === "landing" ? (Landing()) : page === "signup" ? (Signup()) : page === "onboard" ? (Onboard()) : (<div className="dashboard">
          {__text(menu && (<button className="nav-shade" aria-label={__text("Fechar navega\u00E7\u00E3o")} onClick={() => setMenu(false)}/>))}
          <aside className={"sidebar " + (menu ? "shown" : "")}>
            <Logo />
            <small className="nav-section">{__text("PRINCIPAL")}</small>
            <nav>
              {__text(navItems.map(([id, label, img], i) => (<React.Fragment key={id}>
                  {__text(i === 3 && (<small className="nav-section planning">{__text("PLANEJAMENTO")}</small>))}
                  <button className={page === id ? "selected" : ""} onClick={() => go(id)}>
                    <img src={img} alt={__text("")}/>
                    {__text(label)}
                  </button>
                </React.Fragment>)))}
            </nav>
            <div className="sidebar-bottom">
              <button className={page === "settings" ? "selected" : ""} onClick={() => go("settings")}>
                <img src={A.imgIconeDeNavegacao5} alt={__text("")}/>{__text("Configura\u00E7\u00F5es")}</button>
              <button onClick={() => open("help")}>
                <img src={A.imgIconeAjuda} alt={__text("")}/>{__text("Ajuda")}</button>
              <LinkButton onClick={() => go("landing")}>{__text("Voltar ao in\u00EDcio \u2197")}</LinkButton>
            </div>
          </aside>
          <header className="topbar">
            <LanguageSwitcher />
            <button className="mobile-menu" aria-label={__text("Abrir navega\u00E7\u00E3o")} onClick={() => setMenu(true)}>{__text("\u2630")}</button>
            <span className="mobile-brand">{__text("NATIVA")}</span>
            <button className="property-select" onClick={() => open("property")}>
              {__text(farm.name)}{__text("\u2304")}</button>
            <button className="account" aria-label={__text("Minha conta")} onClick={() => open("account")}>
              <img src={A.imgIconeDeConta} alt={__text("")}/>
            </button>
          </header>
          <main className="main-content">
            {__text(page === "overview"
                ? Overview()
                : page === "farm"
                    ? FarmPage()
                    : page === "history"
                        ? History()
                        : page === "climate"
                            ? Climate()
                            : page === "rotation"
                                ? Rotation()
                                : Settings())}
          </main>
        </div>))}
      {__text(modal !== null && (<Dialog onClose={() => open(null)} wide={modal === "map"}>
          <ModalContent />
        </Dialog>))}
      {__text(notice && (<div className="toast" role="status">{__text("\u2713")}{__text(notice)}
          <button aria-label={__text("Fechar notifica\u00E7\u00E3o")} onClick={() => setNotice("")}>{__text("\u00D7")}</button>
        </div>))}
      {__text(inDashboard && <span className="sr-only">{__text("Demonstra\u00E7\u00E3o NATIVA")}</span>)}
    </DraftContext.Provider>);
}
function Dialog({ children, onClose, wide, }: {
    children: React.ReactNode;
    onClose: () => void;
    wide: boolean;
}) {
    const ref = useRef<HTMLDialogElement>(null);
    useEffect(() => {
        const d = ref.current;
        d?.showModal();
        return () => {
            d?.close();
        };
    }, []);
    return (<dialog ref={ref} className={"modal " + (wide ? "modal-wide" : "")} aria-label={__text("Detalhes NATIVA")} onCancel={(e) => {
            e.preventDefault();
            onClose();
        }} onClick={(e) => {
            if (e.target === e.currentTarget) {
                const r = e.currentTarget.getBoundingClientRect();
                if (e.clientX < r.left ||
                    e.clientX > r.right ||
                    e.clientY < r.top ||
                    e.clientY > r.bottom)
                    onClose();
            }
        }}>
      <button className="close-modal" aria-label={__text("Fechar")} onClick={onClose}>{__text("\u00D7")}</button>
      {__text(children)}
    </dialog>);
}
createRoot(document.getElementById("root")!).render(<React.StrictMode>
    <LanguageProvider><App /></LanguageProvider>
  </React.StrictMode>);
