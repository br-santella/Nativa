import { t as __text, t, locale, useLanguage, LanguageProvider, LanguageSwitcher } from "./i18n";
import React, { useState, useEffect, useMemo, useRef, } from "react";
import { createRoot } from "react-dom/client";
import { motion, useReducedMotion } from "motion/react";
import assets from "./assets.json";
import { months, initialFarm, initialCrops, series, info, } from "./data";
import type { Farm, Crop } from "./data";
import "./styles.css";
import RotationStrategies from "./RotationStrategies";
import SeasonOverview from "./SeasonOverview";
import PropertyIcon from "./PropertyIcon";
import FarmMap from "./FarmMap";
import { initialMapView, INDICATOR_LAYERS, MAP_LAYERS, selectMapLayer } from "./mapLayers";
import PropertyWizard from "./PropertyWizard";
import type { SetupInputs } from "./PropertyWizard";
import PropertySettings from "./PropertySettings";
import ClimateStory from "./ClimateStory";
import SolutionStory from "./SolutionStory";
import { loadSaved, persist, clearSaved } from "./storage";
const saved = loadSaved();
const A = assets.overview, L = assets["13:16"];
const path = (file: string) => "/assets/" + file;
type Page = "about" | "landing" | "demo" | "overview" | "farm" | "history" | "climate" | "rotation" | "settings";
type Modal = null | "sources" | "indicators" | "help" | "technology" | "addCrop" | "property" | "contact" | "map";
const pages: Page[] = [
    "about",
    "landing",
    "demo",
    "overview",
    "farm",
    "history",
    "climate",
    "rotation",
    "settings",
];
function currentPage(): Page {
    const p = location.hash.slice(1) as Page;
    if ((p as string) === "settings/property") return "settings";
    if (["signup", "onboard", "login"].includes(p)) return "demo";
    if (p === "farm") return "settings";
    return pages.includes(p) ? p : "landing";
}
function CoverageNotice() {
    return (<p className="coverage-notice" role="note">
      <strong>{__text("Cobertura: somente Paran\u00E1 (PR).")}</strong>{" "}
      {__text("Os dados de solo, relevo, clima e custos usados nas recomenda\u00E7\u00F5es foram preparados apenas para propriedades no estado.")}
    </p>);
}
function App() {
    useLanguage();
    const [page, setPage] = useState<Page>(currentPage), [modal, setModal] = useState<Modal>(null), [farm, setFarm] = useState<Farm>({ ...(saved?.farm ?? initialFarm) }), [draft, setDraft] = useState<Farm>({ ...(saved?.farm ?? initialFarm) }), [crops, setCrops] = useState<Crop[]>(saved?.crops ?? initialCrops), [year, setYear] = useState("2025"), [period, setPeriod] = useState("12"), [menu, setMenu] = useState(false), [notice, setNotice] = useState(""), [slide, setSlide] = useState(0), [carouselPaused, setCarouselPaused] = useState(false), [carouselFocused, setCarouselFocused] = useState(false), [report, setReport] = useState<File | null>(null), [settings, setSettings] = useState(saved?.settings ?? {
        temperature: "Graus Celsius (°C)",
    });
    const [sidebarPreference, setSidebarPreference] = useState<boolean | null>(null);
    const [compactViewport, setCompactViewport] = useState(() => window.matchMedia("(max-width: 1100px)").matches);
    const sidebarCollapsed = sidebarPreference ?? compactViewport;
    useEffect(() => {
        const query = window.matchMedia("(max-width: 1100px)");
        const update = () => setCompactViewport(query.matches);
        query.addEventListener("change", update);
        return () => query.removeEventListener("change", update);
    }, []);
    useEffect(() => {
        if (!menu) return;
        const previousOverflow = document.body.style.overflow;
        document.body.style.overflow = "hidden";
        const closeOnEscape = (event: KeyboardEvent) => {
            if (event.key === "Escape") setMenu(false);
        };
        const desktop = window.matchMedia("(min-width: 701px)");
        const closeOnDesktop = () => { if (desktop.matches) setMenu(false); };
        desktop.addEventListener("change", closeOnDesktop);
        window.addEventListener("keydown", closeOnEscape);
        return () => {
            document.body.style.overflow = previousOverflow;
            desktop.removeEventListener("change", closeOnDesktop);
            window.removeEventListener("keydown", closeOnEscape);
        };
    }, [menu]);
    const [mapView, setMapView] = useState(initialMapView);
    const [setupInputs, setSetupInputs] = useState<SetupInputs | undefined>(saved?.setupInputs);
    // Weights live in setupInputs.pesos (0–10). Settings and the saved state still use the four % values
    // (water, soil, income, climate risk), derived here so they always match the Rotation page.
    // Memoised: SeasonOverview re-runs the engine when this array changes.
    const weights = useMemo(() => setupInputs ? [setupInputs.pesos.agua, setupInputs.pesos.solo, setupInputs.pesos.renda, setupInputs.pesos.risco].map((w) => w * 10) : [50, 50, 50, 50], [setupInputs]);
    // Saving starts once the user completes the setup or saves the property; from then on every change is kept in this browser.
    const [persisted, setPersisted] = useState(saved !== null), [savedAt, setSavedAt] = useState<string | null>(saved?.savedAt ?? null);
    useEffect(() => {
        if (persisted)
            setSavedAt(persist({ farm, setupInputs, weights, crops, settings }));
    }, [persisted, farm, setupInputs, crops, settings]);
    function forgetProperty() {
        clearSaved();
        setPersisted(false);
        setSavedAt(null);
        setFarm({ ...initialFarm });
        setDraft({ ...initialFarm });
        setCrops(initialCrops);
        setSetupInputs(undefined);
        toast("Dados da propriedade apagados deste navegador.");
    }
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
    function go(p: Page) {
        const target = p === "farm" ? "settings" : p;
        location.hash = target;
        if (page === target) {
            setMenu(false);
            setModal(null);
            window.scrollTo(0, 0);
        }
    }
    function toast(s: string) {
        setNotice(s);
    }
    const navItems: [
        Page,
        string,
        string
    ][] = [
        ["overview", "Visão Geral", A.imgIconeDeNavegacao],
        ["climate", "Análise Climática", A.imgIconeDeNavegacao3],
        ["history", "Histórico de Cultivo", A.imgIconeDeNavegacao2],
        ["rotation", "Estratégias de Rotação", A.imgIconeDeNavegacao4],
    ];
    const open = (m: Modal) => setModal(m);
    function Logo({ toggleSidebar = false }: { toggleSidebar?: boolean } = {}) {
        const mobileSidebar = toggleSidebar && window.matchMedia("(max-width: 700px)").matches;
        const label = toggleSidebar ? (mobileSidebar ? "Fechar navegação" : sidebarCollapsed ? "Expandir menu" : "Recolher menu") : "NATIVA — início";
        return (<button className="brand" onClick={() => toggleSidebar ? (mobileSidebar ? setMenu(false) : setSidebarPreference(!sidebarCollapsed)) : go("landing")} aria-label={__text(label)} title={toggleSidebar ? __text(label) : undefined} aria-expanded={toggleSidebar ? (mobileSidebar ? menu : !sidebarCollapsed) : undefined} aria-controls={toggleSidebar ? "dashboard-sidebar" : undefined}>
        <img src={A.imgLogoNativaEnviada} alt={__text("")}/>
        <span className="brand-wordmark"><strong>{__text("NATIVA")}</strong><small className="brand-slogan">Every harvest begins with a better decision</small></span>
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
            ].map((m, i) => (<button type="button" className={"metric panel" + (mapView.layer === INDICATOR_LAYERS[i] ? " is-selected" : "")} key={m[0]} aria-pressed={mapView.layer === INDICATOR_LAYERS[i]} aria-controls="property-map" title={locale() === "en-US" ? MAP_LAYERS[INDICATOR_LAYERS[i]].en : MAP_LAYERS[INDICATOR_LAYERS[i]].pt} onClick={() => setMapView(current => selectMapLayer(current, INDICATOR_LAYERS[i]))}>
            <span className="metric-title">{__text(m[0])}</span>
            <div className="metric-value">
              <strong data-node-id={["3:330", "3:336", "3:342", "3:348"][i]}>
                {__text(m[1])}
              </strong>
              <small>{__text(m[2])}</small>
            </div>
            <span className={"delta " + (i < 2 ? "warm" : "")}>{__text(m[3])}</span>
            <small className="metric-source">{__text("NASA")}{__text(m[4])}{__text("\u2022 exemplo")}</small>
            {__text(i === 0 ? (<img className="metric-spark" src={A.imgMinigraficoDeTemperatura} alt={__text("")}/>) : i === 1 ? (<div className="mini-bars">
                {__text([14, 24, 18, 35, 27, 42, 33].map((v, n) => (<i key={n} style={{ height: v }}/>)))}
              </div>) : i === 2 ? (<div className="metric-ring" aria-hidden="true">
                <svg viewBox="0 0 64 64" fill="none">
                  <circle cx="32" cy="32" r="26" stroke="#29494d" strokeWidth="6" />
                  <circle cx="32" cy="32" r="26" stroke="#a8c9a3" strokeWidth="6" pathLength="100" strokeDasharray={`${Math.max(0, Math.min(100, Number(m[1].replace(",", "."))))} 100`} transform="rotate(-90 32 32)" />
                </svg>
              </div>) : (<div className="ndvi-bars">
                {__text(Array.from({ length: 9 }, (_, n) => (<i key={n} style={{ opacity: n > 6 ? 0.25 : 1 }}/>)))}
              </div>))}
          </button>)))}
      </div>);
    }
    function Overview() {
        return (<div className="overview-page">
        <h1 className="overview-title">{__text("Visão Geral")}</h1>
        <p className="overview-intro">{__text("Acompanhe sua propriedade, entenda o ciclo atual e explore possibilidades para a próxima safra.")}</p>
        <Demo />
        <section className="overview-current-crop" aria-labelledby="overview-current-crop-title">
          <div>
            <small id="overview-current-crop-title"><PropertyIcon kind="farm" />{__text("Nome da propriedade")}</small>
            <h2>{farm.name}</h2>
          </div>
          <dl>
            <div><dt><PropertyIcon kind="crop" />{__text("CULTIVO ATUAL")}</dt><dd>{__text(farm.crop)}</dd></div>
            <div><dt><PropertyIcon kind="location" />{__text("Localização")}</dt><dd>{farm.city} · {__text(farm.country)}</dd></div>
            <div><dt><PropertyIcon kind="area" />{__text("Área total")}</dt><dd>{farm.area} ha</dd></div>
          </dl>
        </section>
        <div className="overview-map">
          <FarmMap id="property-map" view={mapView} onViewChange={setMapView} farm={farm} area={setupInputs?.area} onExpand={() => open("map")} />
          <aside className="overview-indicators" aria-label={__text("Indicadores")}>
            {MetricCards()}
          </aside>
        </div>
        <SeasonOverview onNavigate={go} farm={farm} crops={crops} weights={weights} setupInputs={setupInputs} />
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
      </div>);
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
    function Rotation() {
        return (<>
        <div className="page-heading">
          <div>
            <h1>{__text("Estrat\u00E9gias de Rota\u00E7\u00E3o")}</h1>
            <p>{__text("Compare caminhos para a pr\u00F3xima safra, com as suas prioridades.")}</p>
          </div>
        </div>
        <RotationStrategies inputs={setupInputs} farm={farm} crops={crops} onPesosChange={(pesos) => setSetupInputs((current) => (current ? { ...current, pesos } : current))} onCountChange={(n) => setSetupInputs((current) => (current ? { ...current, n_alternativas: n } : current))} onEditSetup={() => go("demo")} onSources={() => open("sources")} />
      </>);
    }
    function Settings() {
        return (<>
        <div className="page-heading">
          <div>
            <h1>{__text("Configura\u00E7\u00F5es")}</h1>
            <p>{__text("Sua propriedade, suas prefer\u00EAncias e a origem dos dados.")}</p>
          </div>
                  </div>
        <Demo />
        <PropertySettings key={JSON.stringify([farm, setupInputs])} farm={farm} inputs={setupInputs} weights={weights} savedAt={savedAt} report={report} onReport={(f) => {
                setReport(f);
                if (f)
                    toast("Laudo selecionado localmente. Nenhum arquivo foi enviado.");
            }} onSave={(nextFarm, inputs) => {
                setFarm(nextFarm);
                setDraft(nextFarm);
                setSetupInputs(inputs);
                setPersisted(true);
                toast("Alterações salvas. Os cenários foram recalculados.");
            }} onRedo={() => go("demo")} onForget={forgetProperty}/>
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
            }))} onInput={() => setPersisted(true)}>
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
              <p>{__text("Os dados da propriedade ficam salvos apenas neste navegador. N\u00E3o h\u00E1 conta real, sincroniza\u00E7\u00E3o ou envio de documentos.")}</p>
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
            "/assets/hero-br-clima-v1.webp",
            "/assets/hero-br-orbita-v1.webp",
            "/assets/hero-br-produtor-v1.webp",
        ];
        const heroDescriptions = ["Lavouras sob um céu de tempestade no Paraná · imagem ilustrativa gerada por IA", "Brasil visto do espaço · ilustração gerada por IA", "Produtor em uma paisagem rural do Paraná · imagem ilustrativa gerada por IA"];
        return (<div className="landing">
        <nav className="landing-nav">
          <LanguageSwitcher />
          <Logo />
          <div>
            <a href="#como-funciona" onClick={(e) => {
                e.preventDefault();
                document.getElementById("como-funciona")?.scrollIntoView({
                    behavior: reduced ? "instant" : "smooth",
                });
            }}>{__text("Como funciona")}</a>
            <a href="#tecnologia" onClick={(e) => {
                e.preventDefault();
                open("technology");
            }}>{__text("Tecnologia")}</a>
            <button onClick={() => go("about")}>{__text("Sobre n\u00F3s")}</button>
          </div>
        </nav>
        <section className="hero" aria-label={__text("Destaques NATIVA")} aria-roledescription={__text("carrossel")} onFocusCapture={() => setCarouselFocused(true)} onBlurCapture={(event) => {
                if (!event.currentTarget.contains(event.relatedTarget as Node | null))
                    setCarouselFocused(false);
            }}>
          {__text(heroImgs.map((src, index) => (<img key={src} className={`hero-photo${slide === index ? " hero-photo-active" : ""}`} src={src} alt={__text(slide === index ? heroDescriptions[index] : "")} aria-hidden={slide !== index} fetchPriority={index === 0 ? "high" : "auto"} decoding="async"/>)))}
          <div className="hero-shade"/>
          <small className="hero-image-credit">{__text("Imagens ilustrativas geradas por IA")}</small>
          <div className="hero-content">
            <small>{__text(["O CLIMA MUDA. SEU PLANEJAMENTO TAMBÉM.", "MAIS INFORMAÇÃO. MAIS PREPARO.", "DA ANÁLISE AO PRÓXIMO CICLO."][slide])}</small>
            <h1>{__text(["Esteja preparado\npara as mudanças do clima.", "Decida com mais contexto.\nDo espaço à sua lavoura.", "Encontre caminhos\npara uma safra mais resiliente."][slide])}</h1>
            <p>{__text(["Chuvas imprevisíveis e secas prolongadas exigem um novo planejamento. Explore sinais ambientais para preparar o próximo ciclo.", "Explore como observações de clima, solo e vegetação da NASA podem apoiar as decisões da sua propriedade.", "Compare estratégias de rotação considerando água, solo e clima antes de planejar o próximo plantio."][slide])}</p>
            <div>
              <button className="button yellow" onClick={() => go("demo")}>{__text("Explore a demo →")}</button>
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
        <ClimateStory/>
        <SolutionStory earth={L.imgFotografiaComZoomSuave1} field={L.imgFotografiaComZoomSuave2} onExplore={() => go("demo")}/>
      </div>);
    }
    function AboutPage() {
        const members = ["Fernanda", "Bruna", "Pedro", "Caio", "Lucas", "Enzo"];
        return <div className="landing about-page">
            <nav className="landing-nav"><LanguageSwitcher /><Logo /><div><button onClick={() => go("landing")}>{__text("Voltar ao início")}</button><button className="button yellow" onClick={() => go("demo")}>{__text("Explore a demo →")}</button></div></nav>
            <main className="about-content">
                <header className="about-intro"><span className="about-eyebrow">AGRO NAUTAS · NATIVA</span><h1>{__text("Seis pessoas. Uma missão em comum.")}</h1><p>{__text("Criamos a NATIVA para aproximar a observação da Terra das decisões no campo. Somos a equipe AgroNautas, participante do NASA Space Apps Challenge.")}</p></header>
                <section className="about-team" aria-label={__text("Nossa equipe")}>
                    {members.map((name, index) => <article className="about-member" key={name}><div className="about-avatar" aria-hidden="true">{name.slice(0, 1)}</div><span className="about-member-number">0{index + 1}</span><h2>{name}</h2><p>{__text("Apresentação em breve.")}</p></article>)}
                </section>
                <footer className="about-footer"><p>{__text("Diferentes perspectivas para uma agricultura mais preparada.")}</p><button className="back-link" onClick={() => go("landing")}>{__text("Voltar ao início")} →</button></footer>
            </main>
        </div>;
    }
    function PropertySetup() {
        return <PropertyWizard initial={draft} brand={<Logo />} onHome={() => go("landing")} onComplete={(nextFarm, inputs) => {
            setFarm(nextFarm);
            setDraft(nextFarm);
            setSetupInputs(inputs);
            setPersisted(true);
            go("overview");
        }} />;
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
          <h2>{__text("Minha Propriedade")}</h2>
          <FarmMap view={mapView} onViewChange={setMapView} farm={farm} area={setupInputs?.area} expanded onExpand={() => open(null)} />
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
          <CoverageNotice />
          <LinkButton onClick={() => go("settings")}>{__text("Editar propriedade \u2192")}</LinkButton>
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
    const inDashboard = !["landing", "demo", "about"].includes(page);
    return (<>
      {__text(page === "landing" ? (Landing()) : page === "demo" ? (PropertySetup()) : page === "about" ? (AboutPage()) : (<div className={"dashboard" + (sidebarCollapsed ? " sidebar-collapsed" : "")}>
          {__text(menu && (<button className="nav-shade" aria-label={__text("Fechar navega\u00E7\u00E3o")} onClick={() => setMenu(false)}/>))}
          <aside id="dashboard-sidebar" className={"sidebar " + (menu ? "shown" : "")}>
            <div className="sidebar-header">
              <Logo toggleSidebar />
              <button className="sidebar-close" aria-label={__text("Fechar navegação")} onClick={() => setMenu(false)}><span aria-hidden="true">×</span></button>
            </div>
            <small className="nav-section">{__text("PRINCIPAL")}</small>
            <nav id="dashboard-nav">
              {__text(navItems.map(([id, label, img], i) => (<React.Fragment key={id}>
                  {__text(i === 2 && (<small className="nav-section planning">{__text("PLANEJAMENTO")}</small>))}
                  <button className={page === id ? "selected" : ""} aria-label={__text(label)} title={__text(label)} onClick={() => go(id)}>
                    <img src={img} alt={__text("")}/>
                    <span className="nav-label">{__text(label)}</span>
                  </button>
                </React.Fragment>)))}
            </nav>
            <div className="sidebar-bottom">
              <button className={page === "settings" || page === "farm" ? "selected" : ""} aria-label={__text("Configurações")} title={__text("Configurações")} onClick={() => go("settings")}>
                <img src={A.imgIconeDeNavegacao5} alt={__text("")}/><span className="nav-label">{__text("Configura\u00E7\u00F5es")}</span></button>
              <button aria-label={__text("Ajuda")} title={__text("Ajuda")} onClick={() => open("help")}>
                <img src={A.imgIconeAjuda} alt={__text("")}/><span className="nav-label">{__text("Ajuda")}</span></button>
              <button className="sidebar-home" aria-label={__text("Voltar ao início ↗")} title={__text("Voltar ao início ↗")} onClick={() => go("landing")}><span className="sidebar-home-icon" aria-hidden="true">↗</span><span className="nav-label">{__text("Voltar ao início ↗")}</span></button>
            </div>
          </aside>
          <header className="topbar">
            <LanguageSwitcher />
            <button className="mobile-menu" aria-expanded={menu} aria-controls="dashboard-sidebar" aria-label={__text("Abrir navega\u00E7\u00E3o")} onClick={() => setMenu(true)}>{__text("\u2630")}</button>
            <span className="mobile-brand">{__text("NATIVA")}</span>
            <button className="property-select" title={farm.name} aria-haspopup="dialog" aria-expanded={modal === "property"} onClick={() => open("property")}>
              <span className="property-select-name">{farm.name}</span>
              <svg className="property-select-chevron" viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="m5 7.5 5 5 5-5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>
            </button>
          </header>
          <main className="main-content">
            {__text(page === "overview"
                ? Overview()
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
    </>);
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
