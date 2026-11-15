// "Estratégias de Rotação": the engine's result explained to the farmer.
// 01 priorities (from the setup, editable) -> 02 the options chosen in the setup -> 03 current rotation vs one option.
import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { ApiError, health, recomendacao } from "./api";
import type { DataOrigem, Health, ItemRanking, Lang, Pesos, Recomendacao } from "./api";
import type { SetupInputs } from "./PropertyWizard";
import type { Farm } from "./data";
import { useLanguage } from "./i18n";
import { rotacaoDoHistorico } from "./rotacaoAtual";
import { CRITERIA, PRIORITIES, THEMES, levelLabel } from "./priorities";
import PriorityPicker from "./PriorityPicker";
import { rotationCalendar } from "./rotationCalendar";
import type { MonthUse } from "./rotationCalendar";
import type { CriterionId } from "./priorities";
import "./rotation-strategies.css";

const DEMO_FIELD = "72638";
const RECALC_DELAY_MS = 600;
/** The engine accepts 1 to 6 alternatives; the page asks for 6 and shows as many as the user picks. */
const MAX_OPTIONS = 6;
const CURRENT_COLOR = "#9fb3b6";
const OPTION_COLOR = "#ffbf22";

type Crop = { crop: string; plant: string; harvest?: string };
type Props = {
  inputs?: SetupInputs;
  farm: Farm;
  crops: Crop[];
  /** App weights used when there is no setup yet (the same ones the Overview sends to the engine). */
  pesos?: Pesos;
  /** Persists edited weights in the app state, so they survive leaving the page. */
  onPesosChange?: (pesos: Pesos) => void;
  /** Persists the number of options shown. */
  onCountChange?: (count: number) => void;
  onSources: () => void;
};

/** Inputs used when the user reaches this page without going through the setup wizard. */
function fallbackInputs(farm: Farm, crops: Crop[], pesos: Pesos = PRIORITIES[0].pesos): SetupInputs {
  const lat = Number(farm.latitude), lon = Number(farm.longitude);
  const valid = farm.latitude.trim() !== "" && farm.longitude.trim() !== "" && Number.isFinite(lat) && Number.isFinite(lon);
  const current = rotacaoDoHistorico(crops);
  return {
    area: valid ? { lat, lon } : { talhao_id: DEMO_FIELD },
    rotacao_atual: current.id,
    pesos,
    n_alternativas: 3,
    data_referencia: new Date().toLocaleDateString("en-CA", { timeZone: "America/Sao_Paulo" }),
    problemas_area: [],
    restricoes: { sem_comprador: [], maquinas: { plataforma_milho: true, semeadora_consorcio: true } },
    // "Não informado" leaves the field out, so the engine uses its default.
    irrigacao: (farm.irrigation === "Sim" ? { disponivel: true } : farm.irrigation === "Não" ? { disponivel: false } : undefined) as SetupInputs["irrigacao"],
    ...(current.colheitaPrevista ? { colheita_prevista: current.colheitaPrevista } : {}),
  };
}

const score = (v: number | null | undefined) => (v == null ? null : Math.round(v * 100));

export default function RotationStrategies({ inputs, farm, crops, pesos: appPesos, onPesosChange, onCountChange, onSources }: Props) {
  const { language } = useLanguage();
  const en = language === "en";
  const lang: Lang = en ? "en" : "pt-BR";
  const say = (pt: string, english: string) => (en ? english : pt);
  const tx = (text: { pt: string; en: string }) => (en ? text.en : text.pt);
  const money = (v: number) => `R$ ${Math.round(v).toLocaleString(en ? "en-US" : "pt-BR")}`;
  const signedMoney = (v: number) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${money(Math.abs(v))}`;

  const base = useMemo(() => inputs ?? fallbackInputs(farm, crops, appPesos), [inputs, farm, crops, appPesos]);

  // 01 · priorities: edits apply automatically after a short pause.
  const [pesos, setPesos] = useState<Pesos>(base.pesos);
  const [committed, setCommitted] = useState<Pesos>(base.pesos);
  const persist = useRef(onPesosChange);
  persist.current = onPesosChange;
  // Last weights handed to the app state; pending edits are flushed when the page unmounts.
  const saved = useRef(JSON.stringify(base.pesos));
  const latest = useRef(pesos);
  latest.current = pesos;
  const save = (value: Pesos) => {
    const key = JSON.stringify(value);
    if (key === saved.current) return;
    saved.current = key;
    persist.current?.(value);
  };
  useEffect(() => {
    const id = setTimeout(() => { setCommitted(pesos); save(pesos); }, RECALC_DELAY_MS);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pesos]);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => () => save(latest.current), []);
  const pending = JSON.stringify(pesos) !== JSON.stringify(committed);

  // Engine call: one request per distinct body (weights, setup and language).
  const body = useMemo(() => ({ ...base, pesos: committed, n_alternativas: MAX_OPTIONS }), [base, committed]);
  const [count, setCount] = useState(Math.min(Math.max(base.n_alternativas, 1), MAX_OPTIONS));
  const chooseCount = (n: number) => { setCount(n); onCountChange?.(n); };
  const requestKey = JSON.stringify(body) + lang;
  const [api, setApi] = useState<Health | null>(null);
  const [res, setRes] = useState<Recomendacao | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    health(lang)
      .then(h => {
        if (!active) return null;
        setApi(h);
        if (h.status !== "ok") return null;
        return recomendacao({ area: body.area, rotacaoAtual: body.rotacao_atual, pesos: body.pesos, colheitaPrevista: body.colheita_prevista, irrigacao: body.irrigacao }, lang, body);
      })
      .then(r => { if (active) setRes(r); })
      .catch((e: unknown) => {
        if (!active) return;
        setRes(null);
        setError(e instanceof ApiError ? e : new ApiError(0, "erro", String(e)));
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestKey]);

  const current = res?.atual ?? null;
  const block = res?.agora ?? (res ? { ranking: res.ranking, alternativas: res.alternativas, eliminadas: res.eliminadas } : null);
  const options = block ? block.alternativas.slice(0, count) : [];
  const evaluated = block?.ranking.length ?? 0;

  const bestId = options.reduce<ItemRanking | null>((best, it) => (it.nota ?? -1) > (best?.nota ?? -1) ? it : best, null)?.id;

  // Card titles: each option gets the criterion where it gains most over today (weighted by the priorities)
  // that a better-ranked option has not taken yet.
  const themes = new Map<string, CriterionId | null>();
  {
    const taken = new Set<CriterionId>();
    const baseline = current && !current.eliminada ? current : null;
    for (const o of options) {
      const gains = CRITERIA.map(c => ({ id: c.id, gain: committed[c.id] * ((o.criterios?.[c.id] ?? 0) - (baseline?.criterios?.[c.id] ?? 0)) }))
        .filter(g => baseline && g.gain > 0).sort((a, b) => b.gain - a.gain);
      const pick = gains.find(g => !taken.has(g.id)) ?? gains[0];
      if (pick) taken.add(pick.id);
      themes.set(o.id, pick?.id ?? null);
    }
  }

  // 03 · comparison target (defaults to the best option).
  const [compareId, setCompareId] = useState<string | null>(null);
  const target = options.find(o => o.id === compareId) ?? options[0] ?? null;
  const compareRef = useRef<HTMLElement>(null);
  const compareWith = (id: string) => { setCompareId(id); compareRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }); };

  const origin = (o: DataOrigem["origem"]) => ({
    estagio: say("pelo estágio da lavoura", "from the crop stage"),
    informada: say("informada por você", "provided by you"),
    derivada: say("logo após a colheita prevista", "right after the expected harvest"),
    premissa: say("estimativa de calendário", "calendar estimate"),
  })[o] ?? o;

  const statusLine = error?.codigo === "sem_conexao" ? null : (loading || pending) && res ? say("Atualizando resultados…", "Updating results…") : null;

  return <div className="rs">
   <div className="rs-top">
    {/* Land summary: what the engine is working with. */}
    <section className="rs-summary" aria-label={say("Sua área", "Your land")}>
     <span className="rs-eyebrow">{say("Sua área", "Your land")}</span>
     <h2>{farm.name || say("Sua propriedade", "Your farm")}</h2>
     <p className="rs-summary-place">{[farm.city, farm.area && `${Number.isFinite(Number(farm.area)) ? Number(farm.area).toLocaleString(en ? "en-US" : "pt-BR", { maximumFractionDigits: 1 }) : farm.area} ha`].filter(Boolean).join(" · ")}</p>
     <ul className="rs-facts">
      <li><span className="rs-fact-icon" aria-hidden="true">⟳</span><div><small>{say("Rotação atual", "Current rotation")}</small><strong>{current?.rotacao ?? "—"}</strong></div></li>
      <li><span className="rs-fact-icon" aria-hidden="true">☀</span><div><small>{say("Colheita do verão", "Summer harvest")}</small><strong>{res?.colheita_estimada ? `~${res.colheita_estimada.data}` : "—"}</strong>{res?.colheita_estimada && <em>{origin(res.colheita_estimada.origem)}</em>}</div></li>
      <li><span className="rs-fact-icon" aria-hidden="true">✿</span><div><small>{say("Semeadura da 2ª safra", "Second-crop sowing")}</small><strong>{res?.semeadura_2a?.data ?? "—"}</strong>{res?.semeadura_2a && <em>{origin(res.semeadura_2a.origem)}</em>}</div></li>
     </ul>
    </section>

    {/* 01 · priorities */}
    <section className="rs-section rs-priorities">
     <header className="rs-heading"><span className="rs-step">01</span><div><h2>{say("O que mais importa na sua safra", "What matters most this season")}</h2><p>{say("Veio do seu cadastro. Se mudar aqui, os resultados se atualizam sozinhos.", "This comes from your setup. Change it here and the results update on their own.")}</p></div></header>
     <PriorityPicker pesos={pesos} onChange={setPesos}/>
    </section>
   </div>

   {/* 02 · options */}
   <section className="rs-section">
    <header className="rs-heading rs-heading-row"><span className="rs-step">02</span><div>
     <h2>{say("Suas opções", "Your options")}</h2>
     <p>{say(`As ${count} alternativas com maior nota para as suas prioridades. A nota vai de 0 a 100 e junta os cinco critérios com os pesos acima.`,
      `The ${count} alternatives with the highest score for your priorities. The score goes from 0 to 100 and combines the five criteria with the weights above.`)}</p>
    </div>
     <div className="rs-count" role="radiogroup" aria-label={say("Quantas opções mostrar", "How many options to show")}>
      <span>{say("Mostrar", "Show")}</span>
      {Array.from({ length: MAX_OPTIONS }, (_, i) => i + 1).map(n => <label key={n}><input type="radio" name="option-count" checked={count === n} onChange={() => chooseCount(n)}/><span>{n}</span></label>)}
     </div>
    </header>
    {statusLine && <p className="rs-status" role="status">{statusLine}</p>}
    {!res ? <Placeholder error={error} degraded={api != null && api.status !== "ok"} en={en}/> : <>
     {current && <p className="rs-baseline">{current.eliminada
      ? say(`A sua rotação de hoje (${current.rotacao}) foi eliminada pelas regras do motor, então as opções não têm com o que ser comparadas.`, `Your current rotation (${current.rotacao}) was ruled out by the engine rules, so the options have nothing to be compared with.`)
      : <>{say("Comparadas com a sua rotação de hoje:", "Compared with your rotation today:")} <strong>{current.rotacao}</strong> · {say("nota", "score")} <strong>{score(current.nota)}</strong>{current.posicao != null && evaluated > 0 ? say(` (${current.posicao}ª entre ${evaluated} avaliadas)`, ` (#${current.posicao} of ${evaluated} evaluated)`) : ""}</>}</p>}
     {options.length === 0 && <p className="rs-empty">{say("O motor não encontrou alternativas válidas para esta área com o seu cadastro.", "The engine found no valid alternatives for this land with your setup.")}</p>}
     <div className="rs-cards" style={{ "--rs-cols": options.length <= 4 ? options.length : Math.ceil(options.length / 2) } as CSSProperties}>
      {options.map((item, i) => <ScenarioCard key={item.id} item={item} rank={i + 1} current={current} best={item.id === bestId}
       theme={themes.get(item.id) ?? null} harvest={res.colheita_estimada?.data} sowing={res.semeadura_2a?.data} evaluated={evaluated} en={en} money={money}
       compared={target?.id === item.id} onCompare={() => compareWith(item.id)}/>)}
     </div>
     <p className="rs-cards-legend">{say("↑ melhor que a rotação de hoje · ↓ pior que a rotação de hoje. As frases resumem as notas de cada critério calculadas pelo motor.",
      "↑ better than today’s rotation · ↓ worse than today’s rotation. The phrases summarise each criterion score computed by the engine.")}</p>
    </>}
   </section>

   {/* 03 · comparison */}
   {res && current && target && <section className="rs-section" ref={compareRef}>
    <header className="rs-heading"><span className="rs-step">03</span><div>
     <h2>{say("Compare lado a lado", "Compare side by side")}</h2>
     <p>{say("Sua rotação de hoje, à esquerda, contra uma das opções, à direita. No meio, o que você ganha e o que perde ao trocar; use as setas para passar pelas opções.", "Your rotation today on the left against one of the options on the right. In the middle, what you gain and lose by switching; use the arrows to go through the options.")}</p>
    </div></header>
    <div className="rs-versus">
     <ScenarioCard item={current} rank={0} current={null} best={false} theme={null} harvest={res.colheita_estimada?.data} sowing={res.semeadura_2a?.data}
      evaluated={evaluated} en={en} money={money} compared={false} compact/>
     <Versus current={current} option={target} rank={options.indexOf(target) + 1} total={options.length} en={en} money={money} signedMoney={signedMoney}
      onStep={step => { const i = options.indexOf(target); setCompareId(options[(i + step + options.length) % options.length].id); }}/>
     <ScenarioCard item={target} rank={options.indexOf(target) + 1} current={current} best={false} theme={themes.get(target.id) ?? null} harvest={res.colheita_estimada?.data}
      sowing={res.semeadura_2a?.data} evaluated={evaluated} en={en} money={money} compared compact/>
    </div>
   </section>}

   {/* Notes */}
   {res && res.avisos.length > 0 && <details className="rs-notes">
    <summary>{say(`Avisos do motor (${res.avisos.length})`, `Engine notes (${res.avisos.length})`)}</summary>
    <ul>{res.avisos.map(a => <li key={a}>{a}</li>)}</ul>
   </details>}
   <footer className="rs-footer">
    <p>{say("Valores estimados com dados NASA POWER, SoilGrids, MapBiomas e IBGE. Nenhum cenário é uma recomendação absoluta: confirme com assistência agronômica antes de decidir.",
     "Estimates based on NASA POWER, SoilGrids, MapBiomas and IBGE data. No scenario is an absolute recommendation: check with an agronomist before deciding.")}</p>
    <button type="button" className="rs-link-button" onClick={onSources}>{say("Ver premissas e limitações →", "See assumptions and limitations →")}</button>
   </footer>
  </div>;
}

function Placeholder({ error, degraded, en }: { error: ApiError | null; degraded: boolean; en: boolean }) {
  const say = (pt: string, english: string) => (en ? english : pt);
  if (error) return <p className="rs-error" role="alert">{error.codigo === "fora_da_regiao"
    ? `${error.message} ${say("Ajuste a área no cadastro para um ponto no Paraná.", "Set the land in your setup to a point in Paraná.")}`
    : error.codigo === "sem_conexao" ? say("Não foi possível conectar ao motor agora. Tente de novo em instantes.", "Could not reach the engine right now. Try again in a moment.") : error.message}</p>;
  if (degraded) return <p className="rs-error" role="alert">{say("O motor está sem os dados necessários no momento. Tente novamente mais tarde.", "The engine is missing the data it needs right now. Please try again later.")}</p>;
  return <div className="rs-loading" role="status"><span/>{say("Calculando as opções para a sua área…", "Working out the options for your land…")}</div>;
}

type MoneyFns = { money: (v: number) => string; signedMoney: (v: number) => string };

function Delta({ value, unit = "", en }: { value: number; unit?: string; en: boolean }) {
  const cls = value > 0 ? "is-up" : value < 0 ? "is-down" : "is-same";
  const text = value === 0 ? (en ? "same" : "igual") : `${value > 0 ? "+" : "−"}${Math.abs(value)}${unit}`;
  return <span className={"rs-delta " + cls}>{text}</span>;
}

const SHORT_NAMES: Record<string, { pt: string; en: string }> = {
  renda: { pt: "Renda", en: "Income" }, solo: { pt: "Solo", en: "Soil" }, agua: { pt: "Água", en: "Water" },
  pragas: { pt: "Pragas", en: "Pests" }, risco: { pt: "Clima", en: "Climate" },
};

function ScenarioCard({ item, rank, current, best, theme, harvest, sowing, evaluated, en, money, compared, onCompare, compact = false }: {
  item: ItemRanking; rank: number; current: ItemRanking | null; best: boolean; theme: CriterionId | null; harvest?: string; sowing?: string;
  evaluated: number; en: boolean; money: (v: number) => string; compared: boolean; onCompare?: () => void;
  /** Comparison view: no details panel and no buttons. */
  compact?: boolean;
}) {
  const say = (pt: string, english: string) => (en ? english : pt);
  const tx = (text: { pt: string; en: string }) => (en ? text.en : text.pt);
  const [open, setOpen] = useState(false);
  const isCurrent = item.atual;
  const baseline = !isCurrent && current && !current.eliminada ? current : null;
  const title = isCurrent ? say("Rotação atual", "Current rotation") : theme ? tx(THEMES[theme]) : say("Alternativa para explorar", "Alternative to explore");
  const ribbon = best ? say("Maior nota para as suas prioridades", "Highest score for your priorities")
    : isCurrent ? say("Sua rotação hoje · referência", "Your rotation today · baseline")
    : say(`Opção #${rank} · para explorar`, `Option #${rank} · to explore`);
  const calendar = item.verao && item.segunda && harvest && sowing ? rotationCalendar(item.verao.id, item.segunda.id, harvest, sowing) : null;
  const secondName = item.segunda?.id === "pousio" ? say("Pousio", "Fallow") : item.segunda?.nome ?? "";
  return <article className={"rs-card" + (best ? " is-best" : "") + (isCurrent ? " is-current" : "") + (compared ? " is-compared" : "")}>
   <div className="rs-card-ribbon">{ribbon}</div>
   <div className="rs-card-body">
    <h3>{title}</h3>
    {item.eliminada ? <p className="rs-warning">{say("Eliminada pelas regras: ", "Ruled out: ")}{(item.motivos ?? []).join(" ")}</p> : <>
     <div className="rs-card-score"><strong>{score(item.nota)}</strong><span>/ 100</span><small>{isCurrent && item.posicao != null && evaluated > 0 ? say(`${item.posicao}ª entre ${evaluated} avaliadas`, `#${item.posicao} of ${evaluated} evaluated`) : say("nota para as suas prioridades", "score for your priorities")}</small></div>
     {item.verao && item.segunda
      ? <div className="rs-card-sequence" data-rotation={item.rotacao} aria-label={item.rotacao}>
         <span className="is-summer"><small>{say("Verão", "Summer")}</small><strong>{item.verao.nome}</strong></span>
         <span className="rs-card-sequence-arrow" aria-hidden="true">→</span>
         <span className="is-second"><small>{say("2ª safra", "2nd season")}</small><strong>{secondName}</strong></span>
        </div>
      : <p className="rs-card-sequence is-plain" data-rotation={item.rotacao}>{item.rotacao}</p>}
     {!compact && calendar && <Calendar months={calendar} summer={item.verao!.nome} second={secondName} en={en}/>}
     <dl className="rs-traits">
      {CRITERIA.map(c => {
        const value = item.criterios?.[c.id];
        if (value == null) return null;
        const before = baseline?.criterios?.[c.id];
        const diff = before == null ? 0 : Math.round(value * 100) - Math.round(before * 100);
        return <div key={c.id}><dt>{tx(SHORT_NAMES[c.id])}</dt><dd>
         <span>{tx(levelLabel(c.id, value))}{diff !== 0 && <b className={diff > 0 ? "is-up" : "is-down"} title={diff > 0 ? say("Melhor que hoje", "Better than today") : say("Pior que hoje", "Worse than today")}>{diff > 0 ? "↑" : "↓"}</b>}</span>
         {c.id === "renda" && item.margem && <small>{say("margem", "margin")} {money(item.margem.total_r_ha)}/ha</small>}
        </dd></div>;
      })}
     </dl>
     {!compact && <>
     <div className="rs-card-note is-benefit"><small>{say("Benefício potencial", "Potential benefit")}</small><p>{item.card?.beneficios[0] ?? say("Sem benefício marcante nos critérios avaliados.", "No notable benefit in the criteria evaluated.")}</p></div>
     <div className="rs-card-note is-attention"><small>{say("Ponto de atenção", "Point of attention")}</small><p>{item.card?.riscos[0] ?? "—"}</p></div>
     </>}
    </>}
   </div>
   {!compact && open && item.card && <div className="rs-details">
    <p>{item.card.por_que}</p>
    {item.card.evidencias.length > 0 && <><h4>{say("De onde vêm esses números", "Where these numbers come from")}</h4><ul>{item.card.evidencias.map(e => <li key={e}>{e}</li>)}</ul></>}
    {item.card.lacunas.length > 0 && <><h4>{say("O que ainda falta saber", "What is still unknown")}</h4><ul>{item.card.lacunas.map(e => <li key={e}>{e}</li>)}</ul></>}
   </div>}
   {!compact && <div className="rs-card-actions">
    {item.card && <button type="button" className={"rs-card-button" + (best ? " is-primary" : "")} aria-expanded={open} onClick={() => setOpen(!open)}>{open ? say("Ocultar detalhes", "Hide details") : say("Entender este cenário →", "Understand this scenario →")}</button>}
    {onCompare && <button type="button" className="rs-link-button" onClick={onCompare}>{say("Comparar com a de hoje", "Compare with today’s")}</button>}
   </div>}
  </article>;
}

const MONTH_LETTERS = { pt: "JFMAMJJASOND", en: "JFMAMJJASOND" };

function Calendar({ months, summer, second, en }: { months: MonthUse[]; summer: string; second: string; en: boolean }) {
  const say = (pt: string, english: string) => (en ? english : pt);
  const letters = en ? MONTH_LETTERS.en : MONTH_LETTERS.pt;
  const uses = new Set(months);
  return <div className="rs-cal" role="img" aria-label={say(`Calendário estimado: ${summer} no verão, ${second} na 2ª safra`, `Estimated calendar: ${summer} in summer, ${second} in the second season`)}>
   <span className="rs-cal-title">{say("Calendário · estimativa", "Calendar · estimate")}</span>
   <div className="rs-cal-grid">{months.map((m, i) => <div key={i}><span>{letters[i]}</span><i className={"is-" + m}/></div>)}</div>
   <small className="rs-cal-legend">
    {uses.has("summer") && <span><i className="is-summer"/>{summer}</span>}
    {uses.has("second") && <span><i className="is-second"/>{second}</span>}
    {uses.has("bare") && <span><i className="is-bare"/>{say("Sem cultura", "No crop")}</span>}
   </small>
  </div>;
}

type Point = { label: string; text: string; delta: string; up: boolean };

/** Middle column of the comparison: what the option gains and loses against today's rotation. */
function Versus({ current, option, rank, total, en, money, signedMoney, onStep }: {
  current: ItemRanking; option: ItemRanking; rank: number; total: number; en: boolean; onStep: (step: number) => void;
} & MoneyFns) {
  const say = (pt: string, english: string) => (en ? english : pt);
  const tx = (text: { pt: string; en: string }) => (en ? text.en : text.pt);
  const pros: Point[] = [], cons: Point[] = [], same: string[] = [];
  const baseline = current.eliminada ? null : current;
  const cs = baseline ? score(baseline.nota) : null, os = score(option.nota) ?? 0;
  for (const c of CRITERIA) {
    const b = option.criterios?.[c.id], a = baseline?.criterios?.[c.id];
    if (b == null || a == null) continue;
    const diff = Math.round(b * 100) - Math.round(a * 100);
    const before = tx(levelLabel(c.id, a)), after = tx(levelLabel(c.id, b));
    if (diff === 0) { same.push(tx(c.name)); continue; }
    const text = before === after ? (diff > 0 ? say(`${after}, um pouco melhor`, `${after}, slightly better`) : say(`${after}, um pouco pior`, `${after}, slightly worse`)) : `${before} → ${after}`;
    (diff > 0 ? pros : cons).push({ label: tx(c.name), text, delta: `${diff > 0 ? "+" : "−"}${Math.abs(diff)}`, up: diff > 0 });
  }
  const moneyPoint = (label: string, a?: number, b?: number) => {
    if (a == null || b == null || Math.round(b - a) === 0) return;
    (b > a ? pros : cons).push({ label, text: `${money(a)} → ${money(b)} /ha`, delta: signedMoney(b - a), up: b > a });
  };
  moneyPoint(say("Renda da 2ª safra", "Second-crop income"), baseline?.margem?.incremental_r_ha, option.margem?.incremental_r_ha);
  moneyPoint(say("Margem da rotação no ano", "Yearly rotation margin"), baseline?.margem?.total_r_ha, option.margem?.total_r_ha);
  const list = (points: Point[]) => <ul className="rs-points">{points.map(p => <li key={p.label} className={p.up ? "is-up" : "is-down"}>
    <span className="rs-points-arrow" aria-hidden="true">{p.up ? "↑" : "↓"}</span>
    <span><strong>{p.label}</strong><small>{p.text}</small></span>
    <b>{p.delta}</b>
   </li>)}</ul>;
  return <div className="rs-versus-middle">
   <div className="rs-versus-nav">
    <button type="button" onClick={() => onStep(-1)} disabled={total < 2} aria-label={say("Opção anterior", "Previous option")}>‹</button>
    <span>{say(`Opção #${rank} de ${total}`, `Option #${rank} of ${total}`)}</span>
    <button type="button" onClick={() => onStep(1)} disabled={total < 2} aria-label={say("Próxima opção", "Next option")}>›</button>
   </div>
   {cs != null && <div className="rs-versus-score">
    <span>{say("Nota geral", "Overall score")}</span>
    <strong>{cs} → {os}</strong>
    <b className={os > cs ? "is-up" : os < cs ? "is-down" : ""}>{os === cs ? say("igual", "same") : `${os > cs ? "+" : "−"}${Math.abs(os - cs)} ${say("pontos", "points")}`}</b>
   </div>}
   <div className="rs-versus-block">
    <h4 className="is-up">{say(`Vantagens ao trocar (${pros.length})`, `Gains from switching (${pros.length})`)}</h4>
    {pros.length ? list(pros) : <p className="rs-versus-empty">{say("Nenhuma em relação a hoje.", "None compared with today.")}</p>}
   </div>
   <div className="rs-versus-block">
    <h4 className="is-down">{say(`Desvantagens ao trocar (${cons.length})`, `Losses from switching (${cons.length})`)}</h4>
    {cons.length ? list(cons) : <p className="rs-versus-empty">{say("Nenhuma em relação a hoje.", "None compared with today.")}</p>}
   </div>
   {same.length > 0 && <p className="rs-versus-same">{say("Sem diferença: ", "No difference: ")}{same.join(", ")}</p>}
   {option.card?.por_que && <details className="rs-versus-why"><summary>{say("O que muda, segundo o motor", "What changes, according to the engine")}</summary><p>{option.card.por_que}</p></details>}
  </div>;
}
