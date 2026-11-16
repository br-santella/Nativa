// "Entender este cenário": one option explained for two readers.
// Always visible: name, badges and three key numbers (score, income vs. today, climate risk).
// Tabs: "Resumo" (plain language: what changes, calendar, soil, score bars, advantages and points of attention),
// "Por que confiar" (how the result would have varied in past seasons, and the data behind it) and
// "Detalhes técnicos" (the engine's own text, evidence grouped by theme, limitations and terms).
import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import type { Bloco, ItemRanking, Pesos } from "./api";
import { CRITERIA, levelLabel } from "./priorities";
import type { CriterionId } from "./priorities";
import { CROP_ROLES, bareSoilDays } from "./cropRoles";
import { rotationCalendar } from "./rotationCalendar";
import type { MonthUse } from "./rotationCalendar";
import SoilBadges from "./SoilBadges";

type Props = {
  item: ItemRanking;
  /** Today's rotation, for the comparisons (null when `item` is today's rotation or it was ruled out). */
  current: ItemRanking | null;
  block: Bloco | null;
  rank: number;
  evaluated: number;
  en: boolean;
  money: (v: number) => string;
  /** Summer harvest and second-crop sowing (dd/mm), for the calendar. */
  harvest?: string;
  sowing?: string;
  /** Weights the score was computed with, to show how much each criterion counts. */
  pesos?: Pesos;
  onClose: () => void;
  /** Closes the window and opens the side-by-side comparison with today's rotation. */
  onCompare?: () => void;
};

type Tab = "summary" | "trust" | "technical";
const TABS: Tab[] = ["summary", "trust", "technical"];
const pct = (v: number) => Math.round(v * 100);
/** Points of difference (0–100) below which a criterion counts as "the same as today". */
const SAME_BAND = 3;
/** Income difference (BRL/ha/yr) below which the income counts as "about the same as today". */
const SAME_MONEY = 100;
const MONTH_LETTERS = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"];

/** Evidence lines grouped by theme (keywords in Portuguese and in the API's English). */
const THEMES: { id: string; pt: string; en: string; match: RegExp }[] = [
  { id: "soil", pt: "Solo", en: "Soil", match: /solo descoberto|bare soil/i },
  { id: "income", pt: "Renda", en: "Income", match: /^(soja|soybean|milho|corn|sorgo|sorghum|trigo|wheat|feij|bean|aveia|oat|nabo|radish|milheto|millet|braqui|brachiaria|bônus|bonus|total|histórico de renda|income history|pousio|fallow)/i },
  { id: "water", pt: "Água", en: "Water", match: /^(água|water|déficit|deficit)/i },
  { id: "climate", pt: "Clima", en: "Climate", match: /geada|frost|risco climático|climate risk/i },
  { id: "zarc", pt: "Calendário oficial (ZARC)", en: "Official calendar (ZARC)", match: /^zarc/i },
  { id: "market", pt: "Mercado", en: "Market", match: /^(mercado|market)/i },
];
/** Data sources detected in the evidence, NASA first. */
const SOURCES: { name: string; pt: string; en: string; match: RegExp; nasa?: boolean }[] = [
  { name: "NASA POWER", pt: "clima diário desde 1991", en: "daily climate since 1991", match: /NASA POWER/i, nasa: true },
  { name: "SoilGrids", pt: "solo", en: "soil", match: /SoilGrids/i },
  { name: "IBGE PAM", pt: "produtividade do município", en: "municipal yields", match: /PAM/ },
  { name: "ZARC · MAPA", pt: "calendário oficial de risco", en: "official risk calendar", match: /ZARC/ },
  { name: "SEAB/DERAL", pt: "preços", en: "prices", match: /DERAL/ },
  { name: "CONAB", pt: "custos", en: "costs", match: /CONAB/ },
];

export default function ScenarioDetail({ item, current, block, rank, evaluated, en, money, harvest, sowing, pesos, onClose, onCompare }: Props) {
  const say = (pt: string, english: string) => (en ? english : pt);
  const name = (c: { name: { pt: string; en: string } }) => (en ? c.name.en : c.name.pt);
  // Short names for generated sentences: a higher "risco" score means less risk, so it reads as "clima" there.
  const SHORT: Record<CriterionId, { pt: string; en: string }> = { renda: { pt: "renda", en: "income" }, solo: { pt: "saúde do solo", en: "soil health" },
    agua: { pt: "água", en: "water" }, pragas: { pt: "quebra de pragas", en: "pest break" }, risco: { pt: "clima", en: "climate" } };
  const short = (id: CriterionId) => (en ? SHORT[id].en : SHORT[id].pt);
  const cap = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);
  const ref = useRef<HTMLDialogElement>(null);
  const [tab, setTab] = useState<Tab>("summary");
  useEffect(() => {
    const dialog = ref.current;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    dialog?.showModal();
    return () => {
      dialog?.close();
      if (previousFocus?.isConnected) previousFocus.focus();
    };
  }, []);

  const baseline = !item.atual && current && !current.eliminada ? current : null;
  const card = item.card;
  const uncertainty = item.incerteza;
  const climate = uncertainty?.risco_climatico;
  const noClimateRisk = !climate && item.criterios != null && item.criterios.risco >= 1;
  const incomeRange = uncertainty?.renda;
  const seasons = Object.entries(uncertainty?.nota_por_safra ?? {}).sort(([a], [b]) => a.localeCompare(b));
  const income = item.historico_renda?.safras ?? [];
  const incomeMax = Math.max(1, ...income.map(s => Math.abs(s.margem_sc_soja_ha)));
  const lossYears = income.filter(s => s.margem_sc_soja_ha < 0).map(s => s.ano);
  const stability = block?.estabilidade;
  const firstIn = stability ? stability.primeiro.find(p => p.id === item.id)?.safras ?? 0 : null;
  const tie = block?.empate_tecnico && block.empate_tecnico.ids.includes(item.id) ? block.empate_tecnico : null;
  const estimated = (uncertainty?.criterios_estimados ?? []).map(id => CRITERIA.find(c => c.id === id)).filter(Boolean) as typeof CRITERIA;
  const roles = item.segunda ? CROP_ROLES[item.segunda.id] ?? [] : [];
  const bareDays = bareSoilDays(card?.evidencias);
  const secondName = item.segunda?.id === "pousio" ? say("Pousio", "Fallow") : item.segunda?.nome;
  const todayName = baseline ? (baseline.segunda?.id === "pousio" ? say("pousio", "fallow") : baseline.segunda?.nome ?? baseline.rotacao) : null;
  const incomeDiff = baseline?.margem && item.margem ? item.margem.total_r_ha - baseline.margem.total_r_ha : null;
  const signed = (v: number) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${money(Math.abs(v))}`;
  // Engine enums: `confianca` is "baixa" or "não validada" ("not validated" in English); `mercado.nivel` stays in Portuguese.
  const confidence = (level: string) => ({ baixa: say("confiança baixa", "low confidence"), low: say("confiança baixa", "low confidence"),
    "não validada": say("ainda não validado", "not validated yet"), "not validated": say("ainda não validado", "not validated yet") })[level] ?? level;
  const marketLevel = card?.mercado && ({ alto: say("alto", "high"), "médio": say("médio", "medium"), medio: say("médio", "medium"), baixo: say("baixo", "low") })[card.mercado.nivel];
  // The engine writes BRL with a decimal point inside Portuguese text ("R$ 120.14/sc"): show a decimal comma in Portuguese.
  const local = (text: string) => (en ? text : text.replace(/(\d)\.(\d{2})(?!\d)/g, "$1,$2"));

  // Criterion differences against today, in points (0–100).
  const diffs = CRITERIA.map(c => ({ c, value: item.criterios?.[c.id], before: baseline?.criterios?.[c.id] }))
    .filter((d): d is { c: typeof CRITERIA[number]; value: number; before: number } => d.value != null && d.before != null)
    .map(d => ({ ...d, delta: pct(d.value) - pct(d.before) }));
  const better = diffs.filter(d => d.delta >= SAME_BAND).sort((a, b) => b.delta - a.delta);
  const worse = diffs.filter(d => d.delta <= -SAME_BAND).sort((a, b) => a.delta - b.delta);
  const weightLabel = (id: CriterionId) => {
    const w = pesos?.[id];
    if (w == null) return null;
    return w >= 7 ? say("pesa muito", "counts a lot") : w >= 4 ? say("pesa médio", "counts medium") : w > 0 ? say("pesa pouco", "counts little") : say("não pesa", "not counted");
  };

  function climateLine(p: number) {
    if (p <= 0) return say("nenhum dos anos analisados", "none of the years analysed");
    const every = Math.max(1, Math.round(1 / p));
    return every <= 1 ? say(`${pct(p)}% dos anos`, `${pct(p)}% of years`) : say(`~1 a cada ${every} anos`, `~1 in every ${every} years`);
  }
  const list = (items: string[]) => items.map((x, i) => <span key={x}>{i > 0 && (i === items.length - 1 ? say(" e ", " and ") : ", ")}{x}</span>);

  // Plain-language summary built from the scores, so it uses the same 0–100 scale as the screen.
  const summary = !baseline ? null : <>
    {say("Comparada com o que você planta hoje", "Compared with what you grow today")} ({todayName}): {better.length > 0
      ? <>{say("melhora em ", "better on ")}<b className="is-up">{list(better.map(d => `${short(d.c.id)} (+${d.delta})`))}</b></>
      : say("não melhora nenhum critério", "no criterion improves")}
    {worse.length > 0 && <>{say("; piora em ", "; worse on ")}<b className="is-down">{list(worse.map(d => `${short(d.c.id)} (−${Math.abs(d.delta)})`))}</b></>}.
  </>;

  // Advantages and points of attention from the data, plus the engine's own lists.
  const NO_BENEFIT = /^(sem benefício marcante|no notable benefit)/i;
  const engineBenefits = (card?.beneficios ?? []).filter(b => !NO_BENEFIT.test(b));
  const advantages: string[] = [
    ...(incomeDiff != null && incomeDiff >= SAME_MONEY ? [say(`Renda maior que hoje: ${signed(incomeDiff)}/ha por ano.`, `Higher income than today: ${signed(incomeDiff)}/ha per year.`)] : []),
    ...(engineBenefits.length ? engineBenefits.map(local) : better.map(d => say(`${cap(short(d.c.id))} melhor que hoje (+${d.delta}).`, `${cap(short(d.c.id))} better than today (+${d.delta}).`))),
  ];
  const attention: string[] = [
    ...(incomeDiff != null && incomeDiff <= -SAME_MONEY ? [say(`Renda menor que hoje: ${signed(incomeDiff)}/ha por ano.`, `Lower income than today: ${signed(incomeDiff)}/ha per year.`)] : []),
    // Only without a comparison: next to "income vs. today" a second income number would confuse.
    ...(incomeDiff == null && item.margem && item.margem.incremental_r_ha < 0 ? [say(`A 2ª safra não se paga sozinha: ${money(item.margem.incremental_r_ha)}/ha, já contando o ganho na soja seguinte.`, `The second crop does not pay for itself: ${money(item.margem.incremental_r_ha)}/ha, including the gain on the next soybean.`)] : []),
    ...worse.filter(d => d.c.id !== "renda").map(d => say(`${cap(short(d.c.id))} pior que hoje (−${Math.abs(d.delta)}).`, `${cap(short(d.c.id))} worse than today (−${Math.abs(d.delta)}).`)),
    ...(lossYears.length ? [say(`A 2ª safra deu prejuízo em ${lossYears.join(", ")}.`, `The second crop lost money in ${lossYears.join(", ")}.`)] : []),
    ...(card?.riscos ?? []).map(local), ...(card?.avisos ?? []).map(local),
  ];

  // Evidence grouped by theme; lines that match no theme go to "Outros".
  const grouped = new Map<string, string[]>();
  for (const line of card?.evidencias ?? []) {
    const theme = THEMES.find(t => t.match.test(line))?.id ?? "other";
    grouped.set(theme, [...(grouped.get(theme) ?? []), local(line)]);
  }
  const allText = [...(card?.evidencias ?? []), ...(card?.lacunas ?? [])].join(" ");
  const sources = SOURCES.filter(s => s.match.test(allText));

  const calendar = (it: ItemRanking | null) => it?.verao && it.segunda && harvest && sowing ? rotationCalendar(it.verao.id, it.segunda.id, harvest, sowing) : null;
  const calOption = calendar(item), calToday = baseline ? calendar(baseline) : null;

  function onTabKey(e: KeyboardEvent<HTMLButtonElement>) {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    const next = TABS[(TABS.indexOf(tab) + (e.key === "ArrowRight" ? 1 : TABS.length - 1)) % TABS.length];
    setTab(next);
    document.getElementById(`sd-tab-${next}`)?.focus();
  }
  const tabLabel = { summary: say("Resumo", "Summary"), trust: say("Por que confiar", "Why trust it"), technical: say("Detalhes técnicos", "Technical details") };

  return <dialog ref={ref} className="modal sd" aria-labelledby="sd-title"
    onCancel={e => { e.preventDefault(); onClose(); }}
    onClick={e => {
      if (e.target !== e.currentTarget) return;
      const r = e.currentTarget.getBoundingClientRect();
      if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) onClose();
    }}>
   <button type="button" className="close-modal" aria-label={say("Fechar", "Close")} onClick={onClose}>×</button>

   {/* Always visible: what this option is and the three numbers that answer "is it worth it?" */}
   <header className="sd-head">
    <span className="sd-eyebrow">{item.atual ? say("Sua rotação hoje", "Your rotation today") : say(`Opção #${rank}`, `Option #${rank}`)}
     {item.posicao != null && evaluated > 0 && <> · {say(`${item.posicao}ª de ${evaluated} avaliadas`, `#${item.posicao} of ${evaluated} evaluated`)}</>}</span>
    <h2 id="sd-title">{item.verao && secondName
      ? <span className="sd-crops"><span className="is-summer"><small>{say("Verão", "Summer")}</small>{item.verao.nome}</span><span aria-hidden="true" className="sd-arrow">→</span><span className="is-second"><small>{say("2ª safra", "2nd season")}</small>{secondName}</span></span>
      : item.rotacao}</h2>
    <div className="sd-badges">
     {item.zarc && <span className={"sd-badge " + (item.zarc.indicado ? "is-good" : "is-warn")}
      title={say("ZARC: zoneamento oficial de risco climático do Ministério da Agricultura, que indica onde e quando plantar cada cultura.", "ZARC: Brazil's official agricultural climate-risk zoning, which says where and when each crop can be sown.")}>
      {item.zarc.indicado ? say("✓ Indicado pelo ZARC", "✓ Recommended by ZARC") : say("! Fora do ZARC na data prevista", "! Outside ZARC on the planned date")}</span>}
     {marketLevel && <span className="sd-badge">{say("Mercado local", "Local market")}: {marketLevel}</span>}
     {tie && <span className="sd-badge is-warn">{say("Empate técnico", "Technical tie")}</span>}
    </div>
   </header>

   <div className="sd-kpis">
    <div className="sd-kpi">
     <small>{say("Nota", "Score")}</small>
     <strong className="is-score">{item.nota == null ? "—" : pct(item.nota)}<span>/100</span></strong>
     <p>{say("Para as suas prioridades. Não é a chance de dar certo.", "For your priorities. It is not the chance of success.")}</p>
    </div>
    <div className="sd-kpi">
     <small>{baseline ? say("Renda por ano, contra hoje", "Income per year, vs. today") : say("Margem da rotação", "Rotation margin")}</small>
     {incomeDiff != null
      ? <strong className={Math.abs(incomeDiff) < SAME_MONEY ? "" : incomeDiff > 0 ? "is-up" : "is-down"}>{Math.abs(incomeDiff) < SAME_MONEY ? say("≈ igual", "≈ same") : signed(incomeDiff)}{Math.abs(incomeDiff) >= SAME_MONEY && <span>/ha</span>}</strong>
      : <strong>{item.margem ? money(item.margem.total_r_ha) : "—"}<span>/ha</span></strong>}
     {item.margem && <p>{say(`Margem estimada: ${money(item.margem.total_r_ha)}/ha (soja + 2ª safra).`, `Estimated margin: ${money(item.margem.total_r_ha)}/ha (soybean + 2nd crop).`)}</p>}
    </div>
    <div className="sd-kpi">
     <small>{say("Risco de clima na 2ª safra", "Climate risk, 2nd season")}</small>
     <strong>{climate ? climateLine(climate.probabilidade) : noClimateRisk ? say("Sem risco de quebra", "No failure risk") : "—"}</strong>
     <p>{climate ? (climate.eventos.length ? climate.eventos.join(" · ") : "") : noClimateRisk ? say("Não há grão para colher.", "There is no grain to harvest.") : ""}</p>
    </div>
   </div>

   <div className="sd-tabs" role="tablist" aria-label={say("Seções do cenário", "Scenario sections")}>
    {TABS.map(t => <button key={t} type="button" role="tab" id={`sd-tab-${t}`} aria-controls={`sd-panel-${t}`} aria-selected={tab === t}
      tabIndex={tab === t ? 0 : -1} className={tab === t ? "is-active" : ""} onClick={() => setTab(t)} onKeyDown={onTabKey}>{tabLabel[t]}</button>)}
   </div>

   {/* Summary: plain language */}
   {tab === "summary" && <div className="sd-panel" role="tabpanel" id="sd-panel-summary" aria-labelledby="sd-tab-summary">
    {summary && <p className="sd-why">{summary}</p>}
    {tie && <p className="sd-note">{tie.texto}</p>}

    {calOption && <section className="sd-section" aria-labelledby="sd-cal-title">
     <h3 id="sd-cal-title">{say("O ano no campo", "The year in the field")}</h3>
     <div className="sd-cal" role="img" aria-label={say("Calendário estimado da rotação, mês a mês", "Estimated rotation calendar, month by month")}>
      <span className="sd-cal-head"/>
      {MONTH_LETTERS.map((m, i) => <span key={i} className="sd-cal-month">{m}</span>)}
      <CalendarRow label={say("Esta opção", "This option")} months={calOption}/>
      {calToday && <CalendarRow label={say("Hoje", "Today")} months={calToday} muted/>}
     </div>
     <p className="sd-legend"><i className="is-summer"/>{item.verao?.nome}<i className="is-second"/>{secondName}<i className="is-bare"/>{say("Solo descoberto", "Bare soil")}
      <span className="sd-legend-note">{say("Estimativa pelas datas de colheita e semeadura.", "Estimate from harvest and sowing dates.")}</span></p>
    </section>}

    {(roles.length > 0 || bareDays != null) && <section className="sd-section" aria-labelledby="sd-soil-title">
     <h3 id="sd-soil-title">{say(`O que ${secondName ?? "a 2ª safra"} faz pelo solo`, `What ${secondName ?? "the second crop"} does for the soil`)}</h3>
     <SoilBadges item={item} baseline={baseline} en={en}/>
     {roles.some(r => !r.scored) && <small className="sd-roles-note">{say("Selos tracejados: efeito agronômico conhecido, que não entra no cálculo da nota.", "Dashed badges: known agronomic effect, not part of the score.")}</small>}
    </section>}

    {item.criterios && <section className="sd-section" aria-labelledby="sd-score-title">
     <div className="sd-section-head"><h3 id="sd-score-title">{say("Como a nota se forma", "How the score is built")}</h3>
      {baseline && <span className="sd-legend"><i className="is-option"/>{say("esta opção", "this option")}<i className="is-today"/>{say("hoje", "today")}</span>}</div>
     <ul className="sd-bars">
      {CRITERIA.map(c => {
        const value = item.criterios![c.id];
        const before = baseline?.criterios?.[c.id];
        const weight = weightLabel(c.id);
        return <li key={c.id}>
         <span className="sd-bar-label">{name(c)}<small>{en ? levelLabel(c.id, value).en : levelLabel(c.id, value).pt}{weight && <> · {weight}</>}</small></span>
         <span className="sd-bar" role="img" aria-label={`${pct(value)} / 100${before != null ? say(`, hoje ${pct(before)}`, `, today ${pct(before)}`) : ""}`}>
          <span className="sd-bar-fill" style={{ width: `${pct(value)}%` }}/>
          {before != null && <span className="sd-bar-today" style={{ left: `${pct(before)}%` }}/>}
         </span>
         <span className="sd-bar-value">{pct(value)}{before != null && pct(value) !== pct(before) && <small className={pct(value) > pct(before) ? "is-up" : "is-down"}>{pct(value) > pct(before) ? "+" : "−"}{Math.abs(pct(value) - pct(before))}</small>}</span>
        </li>;
      })}
     </ul>
     <p className="sd-foot">{say("Cada critério vai de 0 a 100; a nota é a média deles com os pesos das suas prioridades.", "Each criterion goes from 0 to 100; the score is their average weighted by your priorities.")}</p>
    </section>}

    <section className="sd-section sd-two">
     <div><h3 className="is-good">{say("Vantagens", "Advantages")}</h3>
      {advantages.length ? <ul>{advantages.map(a => <li key={a}>{a}</li>)}</ul> : <p className="sd-foot">{say("Nenhuma vantagem clara sobre a rotação de hoje.", "No clear advantage over today’s rotation.")}</p>}
      {card?.mercado && <p className="sd-foot">{say("Mercado", "Market")}: {card.mercado.texto}</p>}</div>
     <div><h3 className="is-warn">{say("Pontos de atenção", "Points of attention")}</h3>
      {attention.length ? <ul>{attention.map(a => <li key={a}>{a}</li>)}</ul> : <p className="sd-foot">—</p>}</div>
    </section>
   </div>}

   {/* Why trust it: how the result would have varied, and the data behind it */}
   {tab === "trust" && <div className="sd-panel" role="tabpanel" id="sd-panel-trust" aria-labelledby="sd-tab-trust">
    <p className="sd-why">{say("A nota usa dados de safras passadas. Aqui você vê quanto o resultado mudaria de um ano para outro e de onde vêm os números.",
      "The score uses data from past seasons. Here you can see how much the result would change from year to year and where the numbers come from.")}</p>
    <div className="sd-trust">
     {seasons.length > 0 && <div className="sd-tile">
      <small>{say("Nota em cada safra recente", "Score in each recent season")}</small>
      <div className="sd-mini" role="img" aria-label={seasons.map(([y, v]) => `${y}: ${pct(v)}`).join(", ")}>
       {seasons.map(([year, v]) => <span key={year} className="sd-mini-col"><b style={{ height: `${pct(v)}%` }}/><em>{pct(v)}</em><i>{year.slice(2)}</i></span>)}
      </div>
      {uncertainty?.nota_faixa && uncertainty.nota_faixa[1] != null && <p>{say(`Variou de ${pct(uncertainty.nota_faixa[0])} a ${pct(uncertainty.nota_faixa[1])} conforme o ano.`, `It ranged from ${pct(uncertainty.nota_faixa[0])} to ${pct(uncertainty.nota_faixa[1])} depending on the year.`)}</p>}
     </div>}
     {firstIn != null && stability && <div className="sd-tile">
      <small>{say("Seria a melhor opção?", "Would it be the best option?")}</small>
      {firstIn > 0 ? <>
       <div className="sd-dots" role="img" aria-label={say(`${firstIn} de ${stability.safras.length} safras`, `${firstIn} of ${stability.safras.length} seasons`)}>
        {stability.safras.map((year, i) => <span key={year} className={i < firstIn ? "is-on" : ""}/>)}
       </div>
       <p><strong>{say(`Em ${firstIn} de ${stability.safras.length} safras`, `In ${firstIn} of ${stability.safras.length} seasons`)}</strong> {say("ela ficaria em 1º lugar, repetindo a renda de cada ano.", "it would rank first, repeating each year’s income.")}</p>
      </> : <p>{say(`Em nenhuma das últimas ${stability.safras.length} safras ela ficaria em 1º lugar: outra opção levou vantagem todos os anos.`, `In none of the last ${stability.safras.length} seasons would it rank first: another option came out ahead every year.`)}</p>}
     </div>}
     {income.length > 0 && <div className="sd-tile">
      <small>{say("Renda da 2ª safra em cada ano", "Second-crop income each year")}</small>
      <div className="sd-mini is-signed" role="img" aria-label={income.map(s => `${s.ano}: ${s.margem_sc_soja_ha}`).join(", ")}>
       {income.map(s => <span key={s.ano} className={"sd-mini-col" + (s.margem_sc_soja_ha < 0 ? " is-loss" : "")}><b style={{ height: `${Math.abs(s.margem_sc_soja_ha) / incomeMax * 50}%` }}/><i>{String(s.ano).slice(2)}</i></span>)}
      </div>
      {incomeRange?.origem === "historico" && incomeRange.faixa_r_ha[1] != null && <p><strong>{money(incomeRange.faixa_r_ha[0])} {say("a", "to")} {money(incomeRange.faixa_r_ha[1])}/ha</strong> {say("a mais que só soja, conforme o ano.", "more than soybean alone, depending on the year.")}</p>}
      <p>{say("Barras em sacas de soja por hectare (1 saca = 60 kg)", "Bars in soybean bags per hectare (1 bag = 60 kg)")}{lossYears.length > 0 && say(`; prejuízo em ${lossYears.join(", ")}.`, `; loss in ${lossYears.join(", ")}.`)}</p>
     </div>}
     {incomeRange?.origem === "custo_fixo" && <div className="sd-tile">
      <small>{say("Renda da 2ª safra", "Second-crop income")}</small>
      <p className="sd-big">{say("Não varia com o ano", "Does not vary by year")}</p>
      <p>{say(`Sem venda de grão: entra só o custo de implantação (${money(incomeRange.incremental_r_ha)}/ha, com o ganho na soja seguinte).`, `No grain is sold: only the establishment cost counts (${money(incomeRange.incremental_r_ha)}/ha, with the gain on the next soybean).`)}</p>
     </div>}
     {incomeRange?.origem === "ano_ruim_p20" && <div className="sd-tile">
      <small>{say("Num ano ruim (1 a cada 5)", "In a bad year (1 in 5)")}</small>
      <p className="sd-big">{say("Renda a mais", "Extra income")}: {money(incomeRange.faixa_r_ha[0])}/ha</p>
      {uncertainty?.nota_faixa && <p>{say(`A nota cairia para ${pct(uncertainty.nota_faixa[0])}.`, `The score would drop to ${pct(uncertainty.nota_faixa[0])}.`)}</p>}
     </div>}
     {climate && <div className="sd-tile">
      <small>{say("Risco de clima na 2ª safra", "Climate risk, 2nd season")}</small>
      <p className="sd-big">{say(`Evento adverso em ${climateLine(climate.probabilidade)}`, `Adverse event in ${climateLine(climate.probabilidade)}`)} <span className="sd-muted">({pct(climate.probabilidade)}%)</span></p>
      {climate.eventos.length > 0 && <p>{climate.eventos.join(" · ")}</p>}
      <details className="sd-why-more"><summary>{confidence(climate.confianca)}</summary><p>{climate.texto}</p></details>
     </div>}
     {noClimateRisk && <div className="sd-tile">
      <small>{say("Risco de clima na 2ª safra", "Climate risk, 2nd season")}</small>
      <p className="sd-big">{say("Sem risco de quebra", "No crop-failure risk")}</p>
      <p>{say("Não há grão para colher, então geada e seca não causam perda de safra.", "There is no grain to harvest, so frost and drought cause no crop loss.")}</p>
     </div>}
    </div>
    {estimated.length > 0 && <p className="sd-foot">{say("Usam valores estimados do catálogo, ainda a validar com agrônomos: ", "Based on catalog estimates, still to be checked by agronomists: ")}{estimated.map(name).join(", ")}.</p>}
    {sources.length > 0 && <section className="sd-section" aria-labelledby="sd-sources-title">
     <h3 id="sd-sources-title">{say("Dados usados neste cenário", "Data used in this scenario")}</h3>
     <ul className="sd-sources">{sources.map(s => <li key={s.name} className={s.nasa ? "is-nasa" : ""}><strong>{s.name}</strong><span>{en ? s.en : s.pt}</span></li>)}</ul>
    </section>}
   </div>}

   {/* Technical details: the engine's own words */}
   {tab === "technical" && <div className="sd-panel" role="tabpanel" id="sd-panel-technical" aria-labelledby="sd-tab-technical">
    {card?.por_que && <section className="sd-section is-first">
     <h3>{say("Resumo do motor", "Engine summary")}</h3>
     <p className="sd-tech-text">{local(card.por_que)}</p>
     <p className="sd-foot">{say("O motor usa a escala de 0 a 1 (0,71 = 71 na tela). A renda deste texto é a da 2ª safra usada na nota (média das últimas safras, quando há histórico); o número do topo compara a margem total da rotação.",
       "The engine uses a 0–1 scale (0.71 = 71 on screen). The income in this text is the second-crop income used in the score (average of recent seasons, when there is a history); the number at the top compares the whole rotation margin.")}</p>
    </section>}
    {grouped.size > 0 && <section className="sd-section">
     <h3>{say("De onde vêm esses números", "Where these numbers come from")}</h3>
     <div className="sd-tech">
      {[...THEMES.map(t => t.id), "other"].filter(id => grouped.has(id)).map(id => {
        const theme = THEMES.find(t => t.id === id);
        return <details key={id}><summary>{theme ? (en ? theme.en : theme.pt) : say("Outros", "Other")} <span>({grouped.get(id)!.length})</span></summary>
         <ul>{grouped.get(id)!.map(line => <li key={line}>{line}</li>)}</ul></details>;
      })}
     </div>
    </section>}
    {card && card.lacunas.length > 0 && <section className="sd-section">
     <h3>{say("O que a análise ainda não considera", "What the analysis does not cover yet")}</h3>
     <ul className="sd-list">{card.lacunas.map(l => <li key={l}>{local(l)}</li>)}</ul>
    </section>}
    <section className="sd-section">
     <h3>{say("Termos desta janela", "Terms in this window")}</h3>
     <dl className="sd-terms">
      <div><dt>{say("2ª safra (safrinha)", "Second season (safrinha)")}</dt><dd>{say("Cultura plantada logo depois da colheita de verão, no mesmo ano.", "Crop sown right after the summer harvest, in the same year.")}</dd></div>
      <div><dt>ZARC</dt><dd>{say("Zoneamento oficial de risco climático do Ministério da Agricultura: diz onde e quando plantar cada cultura.", "Brazil's official agricultural climate-risk zoning: where and when each crop can be sown.")}</dd></div>
      <div><dt>{say("sc/ha", "bags/ha")}</dt><dd>{say("Sacas de 60 kg por hectare.", "60 kg bags per hectare.")}</dd></div>
      <div><dt>{say("Ano ruim (p20)", "Bad year (p20)")}</dt><dd>{say("Resultado que só é pior em 1 de cada 5 anos.", "A result that is worse only in 1 of every 5 years.")}</dd></div>
      <div><dt>CAD</dt><dd>{say("Capacidade de água disponível: quanta água o solo guarda para as raízes.", "Available water capacity: how much water the soil holds for the roots.")}</dd></div>
     </dl>
    </section>
   </div>}

   <footer className="sd-footer">
    <p>{say("Estimativa de apoio à decisão: confirme com o agrônomo antes de mudar a rotação.", "Decision-support estimate: check with your agronomist before changing the rotation.")}</p>
    {onCompare && <button type="button" className="rs-card-button is-primary" onClick={onCompare}>{say("Comparar com a de hoje →", "Compare with today’s →")}</button>}
   </footer>
  </dialog>;
}

function CalendarRow({ label, months, muted = false }: { label: string; months: MonthUse[]; muted?: boolean }) {
  return <>
   <span className={"sd-cal-head" + (muted ? " is-muted" : "")}>{label}</span>
   {months.map((m, i) => <span key={i} className={"sd-cal-cell is-" + m + (muted ? " is-muted" : "")}/>)}
  </>;
}
