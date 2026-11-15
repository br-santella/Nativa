import { t as __text, t, locale, useLanguage, LanguageProvider, LanguageSwitcher } from "./i18n";
import React, { useState, useEffect, useMemo, useRef, } from "react";
import { createRoot } from "react-dom/client";
import { motion, useReducedMotion } from "motion/react";
import assets from "./assets.json";
import { months, initialFarm, initialCrops, series, info, dataSources, } from "./data";
import { health } from "./api";
import { rotacaoDoHistorico } from "./rotacaoAtual";
import setupOptions from "./setup-options.json";
/** Number in the active language (decimal comma in pt-BR, point in English). */
const num = (n: number, digits = 1) => n.toLocaleString(locale(), { minimumFractionDigits: digits, maximumFractionDigits: digits });
/** Area in hectares as typed or saved (always with a point), shown in the active language. */
const ha = (v: string | number) => Number.isFinite(Number(v)) && String(v).trim() !== "" ? Number(v).toLocaleString(locale(), { maximumFractionDigits: 2 }) : String(v);
/** Ids of the sample crops: their area follows the property when it changes. */
const SAMPLE_CROP_IDS = new Set(initialCrops.map((c) => c.id));
import type { Farm, Crop } from "./data";
import "./styles.css";
import "./crop-climate.css";
import "./overview-theme.css";
import RotationStrategies from "./RotationStrategies";
import SeasonOverview from "./SeasonOverview";
import PropertyIcon from "./PropertyIcon";
import FarmMap from "./FarmMap";
import { initialMapView } from "./mapLayers";
import MonitoringCards from "./MonitoringCards";
import PropertyWizard from "./PropertyWizard";
import type { SetupInputs } from "./PropertyWizard";
import PropertySettings from "./PropertySettings";
import ClimateStory from "./ClimateStory";
import SolutionStory from "./SolutionStory";
import OnboardingTour, { tourSeen } from "./OnboardingTour";
import { loadSaved, persist, clearSaved } from "./storage";
import { PRIORITIES } from "./priorities";
import type { Pesos } from "./api";
const saved = loadSaved();
const A = assets.overview, L = assets["13:16"];
const path = (file: string) => "/assets/" + file;
type Page = "about" | "landing" | "demo" | "overview" | "farm" | "crop-climate" | "rotation" | "settings";
type Modal = null | "sources" | "indicators" | "help" | "technology" | "addCrop" | "property" | "contact" | "map" | "climate-detail";
const pages: Page[] = [
    "about",
    "landing",
    "demo",
    "overview",
    "farm",
    "crop-climate",
    "rotation",
    "settings",
];
function currentPage(): Page {
    const hash = location.hash.slice(1);
    if (hash === "history" || hash === "climate") {
        history.replaceState(null, "", "#crop-climate");
        return "crop-climate";
    }
    const p = hash as Page;
    if ((p as string) === "settings/property") return "settings";
    if (["signup", "onboard", "login"].includes(p)) return "demo";
    if (p === "farm") return "settings";
    return pages.includes(p) ? p : "landing";
}
// The app models a single plot per property.
const PLOT_NAME = "Talhão 01";
type CropStatus = "Planejado" | "Em crescimento" | "Concluído";
const asDate = (s: string) => new Date(s + "T12:00:00");
/** Status from the planting and harvest dates, so it never goes stale. */
function cropStatus(c: Crop, today = new Date()): CropStatus {
    if (asDate(c.plant) > today)
        return "Planejado";
    return asDate(c.harvest) >= today ? "Em crescimento" : "Concluído";
}
/** Summer crops (planted Sep–Dec) span two years, as in "2025/26"; second-window crops use a single year. */
function seasonOf(plant: string) {
    const d = asDate(plant), y = d.getFullYear();
    return d.getMonth() >= 8 ? `${y}/${String(y + 1).slice(2)}` : String(y);
}
const byPlantDesc = (crops: Crop[]) => [...crops].sort((a, b) => b.plant.localeCompare(a.plant));
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
    const climateYears = ["2025", "2024", "2023"];
    const availableYears = Array.from(new Set([...climateYears, ...crops.flatMap(c => {
        const first = asDate(c.plant).getFullYear(), last = asDate(c.harvest).getFullYear();
        return Array.from({ length: Math.max(0, last - first) + 1 }, (_, i) => String(first + i));
    })])).sort().reverse();
    const [climateIndicator, setClimateIndicator] = useState<keyof typeof series>("temperature");
    const [deletedCrops, setDeletedCrops] = useState<{ crop: Crop; nextId?: number }[]>([]);
    function deleteCrop(id: number) {
        const index = crops.findIndex(crop => crop.id === id);
        if (index < 0) return;
        setDeletedCrops(previous => [...previous, { crop: crops[index], nextId: crops[index + 1]?.id }]);
        setCrops(previous => previous.filter(crop => crop.id !== id));
    }
    function undoDeleteCrop() {
        const deleted = deletedCrops.at(-1);
        if (!deleted) return;
        setCrops(previous => {
            if (previous.some(crop => crop.id === deleted.crop.id)) return previous;
            const index = previous.findIndex(crop => crop.id === deleted.nextId);
            const restored = [...previous];
            restored.splice(index < 0 ? restored.length : index, 0, deleted.crop);
            return restored;
        });
        setDeletedCrops(previous => previous.slice(0, -1));
    }
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
    const [tour, setTour] = useState(false);
    const [setupInputs, setSetupInputs] = useState<SetupInputs | undefined>(saved?.setupInputs);
    // One set of engine weights (five criteria, 0–10) for Overview, Rotation Strategies and Settings:
    // the setup's weights, or the app's own ones before the setup is done.
    const [freePesos, setFreePesos] = useState<Pesos>(saved?.pesos ?? PRIORITIES[0].pesos);
    const pesos = setupInputs?.pesos ?? freePesos;
    const updatePesos = (next: Pesos) => (setupInputs ? setSetupInputs((current) => (current ? { ...current, pesos: next } : current)) : setFreePesos(next));
    // Legacy four % values (water, soil, income, climate risk) kept in the saved state for older readers.
    const weights = useMemo(() => [pesos.agua, pesos.solo, pesos.renda, pesos.risco].map((w) => w * 10), [pesos]);
    // Saving starts once the user completes the setup or saves the property; from then on every change is kept in this browser.
    const [persisted, setPersisted] = useState(saved !== null), [savedAt, setSavedAt] = useState<string | null>(saved?.savedAt ?? null);
    useEffect(() => {
        if (persisted)
            setSavedAt(persist({ farm, setupInputs, weights, pesos, crops, settings }));
    }, [persisted, farm, setupInputs, pesos, crops, settings]);
    function forgetProperty() {
        clearSaved();
        setPersisted(false);
        setSavedAt(null);
        setFarm({ ...initialFarm });
        setDraft({ ...initialFarm });
        setCrops(initialCrops);
        setDeletedCrops([]);
        setSetupInputs(undefined);
        setFreePesos(PRIORITIES[0].pesos);
        toast("Dados da propriedade apagados deste navegador.");
    }
    const fahrenheit = settings.temperature.startsWith("Graus Fahrenheit");
    const tempUnit = fahrenheit ? "°F" : "°C";
    const toUnit = (celsius: number) => (fahrenheit ? celsius * 9 / 5 + 32 : celsius);
    const fmtDate = (s: string) => asDate(s).toLocaleDateString(locale(), { day: "numeric", month: "short", year: "numeric" });
    const sortedCrops = byPlantDesc(crops);
    // Latest history record of the current crop (farm.crop is kept in step with the setup's current rotation).
    const currentRecord = sortedCrops.find((c) => c.crop === farm.crop && cropStatus(c) !== "Planejado");
    // Same rule as Rotation Strategies: the setup's rotation when there is one, else the one derived from the history.
    const currentRotation = setupInputs
        ? (setupOptions.combinacoes.find((c) => c.id === setupInputs.rotacao_atual)?.nome ?? setupInputs.rotacao_atual)
        : rotacaoDoHistorico(crops).rotulo;
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
    // Once the property is set up, the demo entry points skip the signup and open the dashboard.
    function enterDemo() {
        go(persisted ? "overview" : "demo");
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
        ["crop-climate", "Histórico", A.imgIconeDeNavegacao2],
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
        <span>{__text("\u2022 S\u00E9ries de clima desta p\u00E1gina e cultivos de exemplo s\u00E3o ilustrativos, n\u00E3o medi\u00E7\u00F5es da sua propriedade nem recomenda\u00E7\u00F5es validadas.")}</span>
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
        const vals = climateValues(kind);
        if (!vals.length) return <p className="climate-unavailable" role="status">{__text("Sem série climática demonstrativa para este ano.")}</p>;
        const color = {
            temperature: "#efae38",
            rain: "#8ebdc6",
            moisture: "#a8c9a3",
            ndvi: "#8ca53b",
        }[kind];
        const max = { temperature: toUnit(35), rain: 300, moisture: 60, ndvi: 1 }[kind];
        const minimum = kind === "temperature" ? toUnit(15) : 0;
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
                    ? num(toUnit([35, 25, 15][i]), 0)
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
        <small>{`● NASA ${kind === "moisture" ? "SMAP" : kind === "ndvi" ? "MODIS" : "POWER"} · `}{__text("s\u00E9rie fict\u00EDcia")}</small>
      </div>);
    }
    function Overview() {
        return (<div className="overview-page">
        <h1 className="overview-title">{__text("Visão Geral")}</h1>
        <p className="overview-intro">{__text("Acompanhe sua propriedade, entenda o ciclo atual e explore possibilidades para a próxima safra.")}</p>
        <p className="demo">{locale() === "en-US" ? "Climate indicators: API estimates at the property reference point. Other demonstration information remains illustrative." : "Indicadores climáticos: estimativas via API no ponto de referência da propriedade. Outras informações de demonstração permanecem ilustrativas."}</p>
        <section className="overview-current-crop" aria-labelledby="overview-current-crop-title">
          <div>
            <small id="overview-current-crop-title"><PropertyIcon kind="farm" />{__text("Nome da propriedade")}</small>
            <h2>{farm.name}</h2>
          </div>
          <dl>
            <div><dt><PropertyIcon kind="crop" />{__text("CULTIVO ATUAL")}</dt><dd>{__text(farm.crop)}</dd></div>
            <div><dt><PropertyIcon kind="location" />{__text("Localização")}</dt><dd>{farm.city} · {__text(farm.country)}</dd></div>
            <div><dt><PropertyIcon kind="area" />{__text("Área total")}</dt><dd>{ha(farm.area)} ha</dd></div>
          </dl>
        </section>
        <div className="overview-map">
          <FarmMap id="property-map" view={mapView} onViewChange={setMapView} farm={farm} area={setupInputs?.area} onExpand={() => open("map")} />
          <aside className="overview-indicators" aria-label={__text("Indicadores")}>
            <MonitoringCards farm={farm} area={setupInputs?.area} fahrenheit={settings.temperature.startsWith("Graus Fahrenheit")} view={mapView} onChange={setMapView} />
          </aside>
        </div>
        <SeasonOverview onNavigate={target => go(target === "history" ? "crop-climate" : target)} farm={farm} crops={crops} pesos={pesos} setupInputs={setupInputs} />
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
        // Calendar built from the crop history: one row per crop that overlaps the chosen year.
        const shown = year;
        const y = Number(shown);
        const covered = new Array(12).fill(false);
        const rows = [...sortedCrops].reverse().flatMap((c) => {
            const plant = asDate(c.plant), harvest = asDate(c.harvest);
            if (plant.getFullYear() > y || harvest.getFullYear() < y)
                return [];
            const plantedNow = plant.getFullYear() === y, harvestedNow = harvest.getFullYear() === y;
            const first = plantedNow ? plant.getMonth() : 0, last = harvestedNow ? harvest.getMonth() : 11;
            for (let m = first; m <= last; m++)
                covered[m] = true;
            const spans: [string, number, number, string][] = [];
            if (plantedNow)
                spans.push(["Plantio", first, first, ""]);
            const devStart = plantedNow ? first + 1 : first, devEnd = harvestedNow ? last - 1 : last;
            if (devStart <= devEnd)
                spans.push(["Desenvolvimento", devStart, devEnd, ""]);
            if (harvestedNow && !(plantedNow && first === last))
                spans.push(["Colheita", last, last, "harvest"]);
            return [{ id: c.id, label: `${t(c.crop)} ${seasonOf(c.plant)}`, spans }];
        });
        const bare: [number, number][] = [];
        covered.forEach((isCovered, m) => {
            if (isCovered)
                return;
            const prev = bare[bare.length - 1];
            if (prev && prev[1] === m - 1)
                prev[1] = m;
            else
                bare.push([m, m]);
        });
        return (<section className="panel timeline-panel">
        <div className="section-heading">
          <div>
            <h2>{__text("Uma vis\u00E3o de cada safra")}</h2>
            <p>{__text(PLOT_NAME)} • {ha(farm.area)} ha • {__text("plantio, desenvolvimento e colheita do hist\u00F3rico de cultivo")}</p>
          </div>
          <select aria-label={__text("Ano do calend\u00E1rio")} value={year} onChange={(e) => { setYear(e.target.value); setPeriod("12"); }}>
            {__text(availableYears.map((y) => (<option key={y} value={y}>{__text(y)}</option>)))}
          </select>
        </div>
        <div className="timeline-scroll">
          <div className="timeline">
            <div className="timeline-labels">
              <span />
              {__text(months.map((m) => (<span key={m}>{__text(m)}</span>)))}
            </div>
            {rows.map((row) => (<div className="timeline-row" key={row.id}>
                <strong>{row.label}</strong>
                <div className="timeline-track">
                  {row.spans.map(([label, from, to, kind]) => (<span key={label} className={kind} style={{ gridColumn: `${from + 1}/${to + 2}` }}>{__text(label)}</span>))}
                </div>
              </div>))}
            {bare.length > 0 && (<div className="timeline-row">
                <strong>{__text("Sem cultivo")}</strong>
                <div className="timeline-track">
                  {bare.map(([from, to]) => (<span key={from} className="bare" style={{ gridColumn: `${from + 1}/${to + 2}` }}>{__text("Solo descoberto")}</span>))}
                </div>
              </div>)}
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
    const climateIndicators = {
        temperature: { name: "Temperatura média", source: "NASA POWER", unit: tempUnit, color: "#efae38", description: "Meses mais quentes podem aumentar a demanda por água.", limitation: "Meteorologia em grade: temperatura e precipitação. A escala regional não substitui uma estação local." },
        rain: { name: "Precipitação acumulada", source: "NASA POWER", unit: "mm", color: "#8ebdc6", description: "A chuva se concentra entre outubro e março neste exemplo.", limitation: "Meteorologia em grade: temperatura e precipitação. A escala regional não substitui uma estação local." },
        moisture: { name: "Umidade do solo", source: "NASA SMAP", unit: "%", color: "#a8c9a3", description: "Água na camada superficial; não representa toda a zona de raízes.", limitation: "Umidade na camada superficial do solo. A conversão para percentual é ilustrativa e não descreve toda a zona de raízes." },
        ndvi: { name: "Índice de vegetação (NDVI)", source: "NASA MODIS", unit: "", color: "#8ca53b", description: "NDVI indica atividade da vegetação, não rendimento da safra.", limitation: "Índice espectral relacionado ao vigor vegetal. Nuvens, resolução e época do ano afetam a leitura." },
    };
    function climateValues(kind: keyof typeof series) {
        if (!climateYears.includes(year)) return [];
        return series[kind].slice(period === "6" ? 6 : 0)
            .map(x => year === "2024" ? x * 0.93 : year === "2023" ? x * 1.04 : x)
            .map(x => kind === "temperature" ? toUnit(x) : x);
    }
    function climateValue(kind: keyof typeof series) {
        const values = climateValues(kind);
        if (!values.length) return __text("Dados indisponíveis");
        const value = kind === "rain" ? values.reduce((a, b) => a + b, 0) : values.reduce((a, b) => a + b, 0) / values.length;
        return value.toLocaleString(locale(), { maximumFractionDigits: kind === "ndvi" ? 2 : 1 });
    }
    function CropClimate() {
        const fmt = (value: string) => new Date(value + "T12:00:00").toLocaleDateString(locale());
        return <div className="crop-climate-page">
          <div className="page-heading"><div>
            <h1>{__text("Histórico")}</h1>
            <p>{__text("Acompanhe suas safras e as condições climáticas da propriedade.")}</p>
          </div></div>
          <Demo />
          <div className="crop-climate-layout">
            <div className="crop-climate-main">
        <section className="panel crop-records" aria-labelledby="crop-records-title">
          <div className="section-heading">
            <div><small>{__text("Histórico de Cultivo")}</small><h2 id="crop-records-title">{__text("Cultivos registrados")}</h2></div>
            <Btn onClick={() => open("addCrop")}>{__text("＋ Adicionar cultivo")}</Btn>
          </div>
          <div className="crop-delete-feedback" role="status" aria-live="polite">
            {deletedCrops.length > 0 && <>
              <span>{__text("Cultivo excluído.")} {__text(deletedCrops.at(-1)!.crop.crop)} · {seasonOf(deletedCrops.at(-1)!.crop.plant)}</span>
              <button type="button" onClick={undoDeleteCrop}>{__text("Desfazer exclusão")}</button>
            </>}
          </div>
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
                "Ações",
            ].map((t) => (<th key={t}>{__text(t)}</th>)))}
                </tr>
              </thead>
              <tbody>
                {sortedCrops.map((c) => {
                    const cStatus = cropStatus(c);
                    return (<tr key={c.id}>
                    <td>
                      {__text(c.crop)} • {seasonOf(c.plant)}
                    </td>
                    <td>{fmt(c.plant)}</td>
                    <td>
                      {fmt(c.harvest)}
                      {cStatus !== "Concluído" ? "*" : ""}
                    </td>
                    <td>{ha(c.area)} ha</td>
                    <td>
                      {c.yield ? c.yield + " sc/ha" : __text(cStatus === "Concluído" ? "Não informada" : "Ainda não colhida")}
                    </td>
                    <td>
                      <span className="status">{__text(cStatus)}</span>
                    </td>
                    <td>
                      <button type="button" className="crop-delete-button"
                        aria-label={`${__text("Excluir cultivo")}: ${__text(c.crop)} ${seasonOf(c.plant)}`}
                        title={__text("Excluir cultivo")} onClick={() => deleteCrop(c.id)}>×</button>
                    </td>
                  </tr>);
                })}
                {crops.length === 0 && <tr><td colSpan={7}>{__text("Nenhum cultivo registrado.")}</td></tr>}
              </tbody>
            </table>
          </div>
          <small>{__text("* Data prevista, n\u00E3o observada. Situa\u00E7\u00E3o calculada pelas datas de plantio e colheita.")}</small>
        </section>
              <div className="crop-calendar"><Timeline /></div>

            </div>
            <aside className="panel crop-climate-sidebar" aria-labelledby="climate-summary-title">
              <header><small>{__text("Análise Climática")}</small><h2 id="climate-summary-title">{__text("Resumo climático")}</h2><p>{__text("Clique em um indicador para explorar os detalhes.")}</p></header>
              <div className="crop-climate-indicators">
                {(Object.keys(climateIndicators) as (keyof typeof series)[]).map(kind => {
                    const indicator = climateIndicators[kind];
                    const values = climateValues(kind);
                    const min = kind === "temperature" ? toUnit(15) : 0;
                    const max = { temperature: toUnit(35), rain: 300, moisture: 60, ndvi: 1 }[kind];
                    const points = values.map((v, i) => `${i * 240 / (values.length - 1)},${52 - (v - min) / (max - min || 1) * 40}`).join(" ");
                    return <button type="button" className="climate-mini" key={kind} aria-haspopup="dialog" onClick={() => { setClimateIndicator(kind); open("climate-detail"); }}>
                      <span className="climate-mini-heading"><span>{__text(indicator.name)}</span><span aria-hidden="true">↗</span></span>
                      <span className="climate-mini-value" style={{ color: indicator.color }}>{climateValue(kind)} <small>{values.length ? indicator.unit : ""}</small></span>
                      {values.length ? <svg viewBox="0 0 240 64" aria-hidden="true" focusable="false">
                        {kind === "rain" ? values.map((v, i) => <rect key={i} x={i * 240 / values.length + 3} y={56 - v / max * 44} width={240 / values.length - 6} height={v / max * 44} rx="2" fill={indicator.color} />) : <polyline points={points} stroke={indicator.color} strokeWidth="2" fill="none" vectorEffect="non-scaling-stroke" />}
                      </svg> : <span className="climate-unavailable">{__text("Sem série climática demonstrativa para este ano.")}</span>}
                      <span className="climate-mini-period">{__text(period === "6" ? "Jul–Dez" : "Jan–Dez")} {year} <span>{__text("Ver detalhes →")}</span></span>
                    </button>;
                })}
              </div>
              <p className="climate-summary-note">{__text("Séries demonstrativas, não medições da propriedade.")}</p>
              <LinkButton onClick={() => open("sources")}>{__text("Fontes e limitações →")}</LinkButton>
            </aside>
          </div>
              <section className="plan-banner crop-plan-banner">
                <div>
                  <h2>{__text("Planeje sua próxima safra.")}</h2>
                  <p>{__text("Compare estratégias de rotação considerando o clima, o solo e as prioridades da sua propriedade.")}</p>
                  <button type="button" className="button" onClick={() => go("rotation")}>{__text("Comparar estratégias →")}</button>
                </div>
                <div className="banner-art" aria-hidden="true">
                  {[A.imgRotation, A.imgFieldRows, A.imgSprout, A.imgWarmAccent].map((src, i) => <img key={src} className={"art-" + i} src={src} alt="" />)}
                </div>
              </section>
        </div>;
    }
    function ClimateDetail() {
        const indicator = climateIndicators[climateIndicator];
        return <div className="climate-detail">
          <header><small>{indicator.source} · {__text("DADOS DEMONSTRATIVOS")}</small><h2 id="climate-detail-title">{__text(indicator.name)}</h2></header>
          <div className="climate-detail-filters">
            <label>{__text("Ano")}<select value={year} onChange={e => setYear(e.target.value)}>{availableYears.map(y => <option key={y}>{y}</option>)}</select></label>
            <label>{__text("Período de análise")}<select value={period} onChange={e => setPeriod(e.target.value)}><option value="12">{__text("12 meses")}</option><option value="6">{__text("6 meses (Jul–Dez)")}</option></select></label>
            <strong style={{ color: indicator.color }}>{climateValue(climateIndicator)} <small>{climateValues(climateIndicator).length ? indicator.unit : ""}</small></strong>
          </div>
          <Chart kind={climateIndicator} large />
          <section className="climate-detail-explanation"><h3>{__text("Interpretação e limitações")}</h3><p>{__text(indicator.description)}</p><p>{__text(indicator.limitation)}</p><p>{__text("As linhas tracejadas são ilustrativas; não representam uma previsão meteorológica.")}</p></section>
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
        </div>;
    }
    function Rotation() {
        return (<>
        <div className="page-heading">
          <div>
            <h1>{__text("Estrat\u00E9gias de Rota\u00E7\u00E3o")}</h1>
            <p>{__text("Compare caminhos para a pr\u00F3xima safra, com as suas prioridades.")}</p>
          </div>
        </div>
        <RotationStrategies inputs={setupInputs} farm={farm} crops={crops} pesos={pesos} onPesosChange={updatePesos} onCountChange={(n) => setSetupInputs((current) => (current ? { ...current, n_alternativas: n } : current))} onSources={() => open("sources")} />
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
        <PropertySettings key={JSON.stringify([farm, setupInputs, freePesos])} farm={farm} inputs={setupInputs} pesos={pesos} savedAt={savedAt} report={report} onReport={(f) => {
                setReport(f);
                if (f)
                    toast("Laudo selecionado localmente. Nenhum arquivo foi enviado.");
            }} onSave={(nextFarm, inputs, nextPesos) => {
                setFarm(nextFarm);
                setDraft(nextFarm);
                setCrops((p) => p.map((c) => SAMPLE_CROP_IDS.has(c.id) ? { ...c, area: nextFarm.area } : c));
                setSetupInputs(inputs);
                setFreePesos(nextPesos);
                setPersisted(true);
                toast("Alterações salvas. Os cenários foram recalculados.");
            }} onRedo={() => go("demo")} onForget={forgetProperty}/>
        <section className="settings-section" aria-labelledby="settings-reading-title">
          <header className="settings-heading">
            <span className="settings-step" aria-hidden="true">02</span>
            <div>
              <h2 id="settings-reading-title">{__text("Prefer\u00EAncias de leitura")}</h2>
              <p>{__text("Valem para todas as abas e s\u00E3o aplicadas na hora.")}</p>
            </div>
          </header>
          <div className="two-col">
            <section className="panel">
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
                <div>
                  <dt>{__text("Umidade do solo")}</dt>
                  <dd>{__text("Percentual (%)")}</dd>
                </div>
              </dl>
            </section>
            <aside className="panel green-panel settings-storage">
              <h2>{__text("Onde seus dados ficam")}</h2>
              <dl>
                <div>
                  <dt>{__text("Propriedade, cultivos e prefer\u00EAncias")}</dt>
                  <dd>{__text(persisted ? "Neste navegador. Apague em \u201CApagar dados salvos\u201D, acima." : "Ainda n\u00E3o salvos: conclua o cadastro ou salve a propriedade.")}</dd>
                </div>
                <div>
                  <dt>{__text("Laudo de solo")}</dt>
                  <dd>{__text("S\u00F3 enquanto a p\u00E1gina est\u00E1 aberta. N\u00E3o \u00E9 enviado nem analisado.")}</dd>
                </div>
                <div>
                  <dt>{__text("API da NATIVA")}</dt>
                  <dd>{__text("Recebe a \u00E1rea, a rota\u00E7\u00E3o, as prioridades, a an\u00E1lise de solo e os pre\u00E7os para calcular indicadores e cen\u00E1rios.")}</dd>
                </div>
                <div>
                  <dt>{__text("Busca de endere\u00E7o")}</dt>
                  <dd>{__text("O texto buscado vai ao OpenStreetMap (Nominatim).")}</dd>
                </div>
              </dl>
              <small>{__text("Sem conta, sincroniza\u00E7\u00E3o ou envio de documentos.")}</small>
            </aside>
          </div>
        </section>
        <section className="settings-section" aria-labelledby="settings-sources-title">
          <header className="settings-heading">
            <span className="settings-step" aria-hidden="true">03</span>
            <div>
              <h2 id="settings-sources-title">{__text("Fontes de dados")}</h2>
              <p>{__text("Onde cada fonte aparece na NATIVA.")}</p>
            </div>
          </header>
          <div className="settings-sources">
            {([
                ["engine", "Motor de rota\u00E7\u00E3o", "Estrat\u00E9gias de Rota\u00E7\u00E3o e Safra anual \u2022 para a \u00E1rea cadastrada", true],
                ["indicators", "Indicadores e mapa", "Vis\u00E3o Geral \u2022 no ponto de refer\u00EAncia da propriedade", true],
                ["illustrative", "Ilustrativas", "An\u00E1lise Clim\u00E1tica \u2022 s\u00E9ries de exemplo", false],
            ] as const).map(([key, title, where, live]) => (<section className="panel" key={key}>
                <h3 className={live ? "" : "warm"}>{__text(title)}</h3>
                <p>{__text(where)}</p>
                {key === "engine" && <EngineStatus />}
                <dl className="source-list">
                  {dataSources[key].map(([name, use]) => (<div key={name}>
                      <dt>{__text(name)}</dt>
                      <dd>{__text(use)}</dd>
                    </div>))}
                </dl>
              </section>))}
          </div>
          <LinkButton onClick={() => open("sources")}>{__text("Consultar premissas e limita\u00E7\u00F5es \u2192")}</LinkButton>
        </section>
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
              <button className="button yellow" onClick={enterDemo}>{__text(persisted ? "Continuar na demo →" : "Explore a demo →")}</button>
            </div>
          </div>
          <div className="carousel-controls">
            <div>
              {__text(heroImgs.map((_, i) => (<button key={i} aria-label={`${__text("Ir para imagem")} ${i + 1}`} aria-pressed={slide === i} className={slide === i ? "active" : ""} onClick={() => setSlide(i)}/>)))}
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
        <SolutionStory earth={L.imgFotografiaComZoomSuave1} field={L.imgFotografiaComZoomSuave2} onExplore={enterDemo}/>
      </div>);
    }
    function AboutPage() {
        const members = ["Fernanda", "Bruna", "Pedro", "Caio", "Lucas", "Enzo"];
        return <div className="landing about-page">
            <nav className="landing-nav"><LanguageSwitcher /><Logo /><div><button onClick={() => go("landing")}>{__text("Voltar ao início")}</button><button className="button yellow" onClick={enterDemo}>{__text(persisted ? "Continuar na demo →" : "Explore a demo →")}</button></div></nav>
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
            setCrops((p) => p.map((c) => SAMPLE_CROP_IDS.has(c.id) ? { ...c, area: nextFarm.area } : c));
            setSetupInputs(inputs);
            setPersisted(true);
            go("overview");
        }} />;
    }
    function AddCrop() {
        const [value, setValue] = useState({
            crop: "Milho",
            plant: "2027-02-01",
            harvest: "2027-06-25",
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
                if (Number(value.area) > Number(farm.area)) {
                    setError("A área cultivada não pode ser maior que a área da propriedade.");
                    return;
                }
                const added = { ...value, id: Date.now(), season: seasonOf(value.plant), status: "" };
                setCrops((p) => [{ ...added, status: cropStatus(added) }, ...p]);
                setModal(null);
                toast("Cultivo adicionado ao histórico.");
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
              <option value={PLOT_NAME}>{__text(PLOT_NAME)}</option>
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
              <input type={i < 2 ? "date" : "number"} min={i > 1 ? 0 : undefined} max={key === "area" ? farm.area : undefined} step={i > 1 ? "any" : undefined} value={value[key]} required={key !== "yield"} onChange={(e) => setValue((v) => ({ ...v, [key]: e.target.value }))}/>
            </label>)))}
        </div>
        {__text(error && (<p className="error" role="alert">
            {__text(error)}
          </p>))}
        <p>{__text("As datas podem coexistir com outros cultivos no mesmo ano.")}</p>
        <button type="submit" className="button">{__text("Salvar cultivo")}</button>
        <small>{__text(persisted ? "Fica salvo neste navegador, junto com a propriedade." : "Conclua o cadastro para salvar o hist\u00F3rico neste navegador.")}</small>
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
              {farm.city} • {ha(farm.area)} ha</small>
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
          {modal === "help" && (<button type="button" className="button lime tour-restart" onClick={startTour}>{__text("Ver tutorial guiado")}</button>)}
          <Btn onClick={() => open(null)}>{__text("Entendi")}</Btn>
        </>);
        }
        return null;
    }
    const inDashboard = !["landing", "demo", "about"].includes(page);
    // First visit to the dashboard: open the guided tour on the overview, where all its targets are.
    function startTour() {
        setModal(null);
        setMenu(false);
        go("overview");
        setTour(true);
    }
    useEffect(() => {
        if (inDashboard && !tour && !tourSeen()) startTour();
    }, [inDashboard]);
    return (<>
      {__text(page === "landing" ? (Landing()) : page === "demo" ? (PropertySetup()) : page === "about" ? (AboutPage()) : (<div className={"dashboard" + (sidebarCollapsed ? " sidebar-collapsed" : "")}>
          {__text(menu && (<button className="nav-shade" aria-label={__text("Fechar navega\u00E7\u00E3o")} onClick={() => setMenu(false)}/>))}
          <aside id="dashboard-sidebar" className={"sidebar " + (menu ? "shown" : "")}>
            <div className="sidebar-header">
              <Logo toggleSidebar />
              <button className="sidebar-close" aria-label={__text("Fechar navegação")} onClick={() => setMenu(false)}><span aria-hidden="true">×</span></button>
            </div>
            <small className="nav-section">{__text("Principal")}</small>
            <nav id="dashboard-nav">
              {__text(navItems.map(([id, label, img]) => (<React.Fragment key={id}>
                  <button data-tour={id} className={page === id ? "selected" : ""} aria-current={page === id ? "page" : undefined} aria-label={__text(label)} title={__text(label)} onClick={() => go(id)}>
                    <img src={img} alt={__text("")}/>
                    <span className="nav-label">{__text(label)}</span>
                  </button>
                </React.Fragment>)))}
            </nav>
            <div className="sidebar-bottom">
              <button data-tour="settings" className={page === "settings" || page === "farm" ? "selected" : ""} aria-label={__text("Configurações")} title={__text("Configurações")} onClick={() => go("settings")}>
                <img src={A.imgIconeDeNavegacao5} alt={__text("")}/><span className="nav-label">{__text("Configura\u00E7\u00F5es")}</span></button>
              <button data-tour="help" aria-label={__text("Ajuda")} title={__text("Ajuda")} onClick={() => open("help")}>
                <img src={A.imgIconeAjuda} alt={__text("")}/><span className="nav-label">{__text("Ajuda")}</span></button>
              <button className="sidebar-home" aria-label={__text("Voltar ao início")} title={__text("Voltar ao início")} onClick={() => go("landing")}><span className="sidebar-home-icon" aria-hidden="true">←</span><span className="nav-label">{__text("Voltar ao início")}</span></button>
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
                : page === "crop-climate"
                        ? CropClimate()
                            : page === "rotation"
                                ? Rotation()
                                : Settings())}
          </main>
        </div>))}
      {__text(modal !== null && (<Dialog onClose={() => open(null)} wide={modal === "map" || modal === "climate-detail"} labelledBy={modal === "climate-detail" ? "climate-detail-title" : undefined}>
          {modal === "climate-detail" ? ClimateDetail() : <ModalContent />}
        </Dialog>))}
      {tour && page === "overview" && (<OnboardingTour onClose={() => setTour(false)} onFinish={() => { setTour(false); go("rotation"); }}/>)}
      {__text(notice && (<div className="toast" role="status">{__text("\u2713")}{__text(notice)}
          <button aria-label={__text("Fechar notifica\u00E7\u00E3o")} onClick={() => setNotice("")}>{__text("\u00D7")}</button>
        </div>))}
      {__text(inDashboard && <span className="sr-only">{__text("Demonstra\u00E7\u00E3o NATIVA")}</span>)}
    </>);
}
/** Live status of the NATIVA API, shown next to the engine data sources. */
function EngineStatus() {
    const [status, setStatus] = useState<"checking" | "ok" | "degraded" | "offline">("checking");
    useEffect(() => {
        let active = true;
        health(locale() === "en-US" ? "en" : "pt-BR").then((h) => active && setStatus(h.status === "ok" ? "ok" : "degraded")).catch(() => active && setStatus("offline"));
        return () => { active = false; };
    }, []);
    const label = { checking: "verificando…", ok: "conectada", degraded: "degradada", offline: "indisponível" }[status];
    return (<small className={"engine-status " + status}>● {__text("API")}: {__text(label)}</small>);
}
function Dialog({ children, onClose, wide, labelledBy, }: {
    children: React.ReactNode;
    onClose: () => void;
    wide: boolean;
    labelledBy?: string;
}) {
    const ref = useRef<HTMLDialogElement>(null);
    useEffect(() => {
        const d = ref.current;
        const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
        d?.showModal();
        return () => {
            d?.close();
            if (previousFocus?.isConnected) previousFocus.focus();
        };
    }, []);
    return (<dialog ref={ref} className={"modal " + (wide ? "modal-wide" : "")} aria-label={labelledBy ? undefined : __text("Detalhes NATIVA")} aria-labelledby={labelledBy} onCancel={(e) => {
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
