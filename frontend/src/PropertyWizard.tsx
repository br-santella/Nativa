import { useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import type { Farm } from './data';
import { textureFromSoil } from './data';
import type { Area, Pesos } from './api';
import { LanguageSwitcher, t, useLanguage } from './i18n';
import options from './setup-options.json';
import './property-wizard.css';
import LocationMap from './LocationMap';
import type { LatLon, MapFocus } from './LocationMap';
import { insideParana } from './coverage';
import { PRIORITIES } from './priorities';

export type SetupInputs = {
  area: Area; rotacao_atual: string; pesos: Pesos; n_alternativas: number;
  estagio_verao?: string; colheita_prevista?: string; data_referencia: string; semeadura_safrinha?: string;
  problemas_area: string[]; analise_solo?: Record<string, number>;
  ajustes?: { precos: Record<string, number> };
  restricoes: { sem_comprador: string[]; maquinas: { plataforma_milho: boolean; semeadora_consorcio: boolean } };
  irrigacao: { disponivel: boolean };
};
export const soilFields = [['argila_pct','Argila (%)'],['silte_pct','Silte (%)'],['areia_pct','Areia (%)'],['materia_organica_pct','Matéria orgânica (%)'],['ph','pH'],['p_mg_dm3','Fósforo (mg/dm³)'],['k_cmolc_dm3','Potássio (cmolc/dm³)'],['ca_cmolc_dm3','Cálcio (cmolc/dm³)'],['mg_cmolc_dm3','Magnésio (cmolc/dm³)'],['al_cmolc_dm3','Alumínio (cmolc/dm³)'],['v_pct','Saturação por bases (%)'],['ctc_cmolc_dm3','CTC (cmolc/dm³)']];
export const soilMax: Record<string, number> = {ph:9, p_mg_dm3:500, k_cmolc_dm3:10, ca_cmolc_dm3:40, mg_cmolc_dm3:20, al_cmolc_dm3:15, ctc_cmolc_dm3:60};
/** Clay, silt and sand add up to 100%: two typed values fill in the third. Silt is not sent to the engine. */
const TEXTURE = ['argila_pct', 'silte_pct', 'areia_pct'];
export const PROBLEMS = [['nematoide','Nematoide'],['mofo_branco','Mofo-branco'],['cigarrinha','Cigarrinha'],['compactacao','Compactação']];
export const commodities = [['soja','Soja'],['milho','Milho'],['trigo','Trigo'],['feijao','Feijão'],['sorgo','Sorgo']];
const copy = [
 ['Vamos começar','Um novo olhar começa aqui.','Vamos conhecer um pouquinho da sua terra. No seu tempo.'],
 ['Sua lavoura','O que você cultiva hoje?','Começamos com o que já faz parte da sua rotina.'],
 ['Sua área','Problemas conhecidos','Marque as pragas, doenças ou problemas de solo que já apareceram na sua área.'],
 ['Seu solo','Vamos olhar para o solo?','Preencha o que souber ou siga sem análise.'],
 ['Seu próximo ciclo','O que importa para você?','Escolha uma prioridade e ajuste se quiser.'],
 ['Sua operação','Como é a sua operação?','Responda com sim ou não. Assim sugerimos só o que dá para fazer na sua terra.'],
 ['Tudo pronto','Vamos aos seus cenários?','Os detalhes abaixo são opcionais.'],
];
/** Index of the last step (summary, prices and scenario count). */
const LAST = copy.length - 1;
/** Steps the user can skip without filling anything. */
const OPTIONAL_STEPS = [2, 3, 5, 6];
const isoToday = () => new Date().toLocaleDateString('en-CA', { timeZone: 'America/Sao_Paulo' });
/** Approximate area (ha) of a boundary drawn on the map, projected around its centroid. */
export function hectares(vertices: LatLon[]): number {
 if (vertices.length < 3) return 0;
 const lat0 = vertices.reduce((s, [lat]) => s + lat, 0) / vertices.length * Math.PI / 180;
 const xy = vertices.map(([lat, lon]) => [lon * 111320 * Math.cos(lat0), lat * 110540]);
 const twice = xy.reduce((s, [x, y], i) => { const [nx, ny] = xy[(i + 1) % xy.length]; return s + x * ny - nx * y; }, 0);
 return Math.abs(twice) / 2 / 10000;
}
type Place = { label: string; lat: number; lon: number };
/** Square of `ha` hectares centred on a point, as [lat, lon] corners. */
export function square(lat: number, lon: number, ha: number): LatLon[] {
 const half = Math.sqrt(ha * 10000) / 2, dLat = half / 110540, dLon = half / (111320 * Math.cos(lat * Math.PI / 180));
 return [[lat - dLat, lon - dLon], [lat - dLat, lon + dLon], [lat + dLat, lon + dLon], [lat + dLat, lon - dLon]];
}
/** The engine evaluates fixed second-window sowing dates (dd/mm, Jan–Mar): first one on or after the chosen day. */
function engineSowing(isoDate: string, allowed: string[]): string {
 const month = Number(isoDate.slice(5, 7)), day = Number(isoDate.slice(8, 10));
 if (month >= 8) return allowed[0];
 const key = month * 100 + day;
 return allowed.find(x => { const [d, m] = x.split('/').map(Number); return m * 100 + d >= key; }) ?? allowed[allowed.length - 1];
}
export default function PropertyWizard({ initial, brand, onHome, onComplete }: { initial: Farm; brand: ReactNode; onHome: () => void; onComplete: (farm: Farm, inputs: SetupInputs) => void }) {
 const { language } = useLanguage();
 const en = language === 'en';
 const say = (pt: string, english: string) => en ? english : pt;
 const [step, setStep] = useState(0);
 const [priority, setPriority] = useState('balanced');
 const [farm, setFarm] = useState(initial);
 const [mode, setMode] = useState('demo');
 const [demo, setDemo] = useState('72638');
 const [vertices, setVertices] = useState<LatLon[]>([]);
 const [focus, setFocus] = useState<MapFocus | null>(null);
 const [cityQuery, setCityQuery] = useState(initial.city.replace(/,\s*PR$/i, ''));
 const [address, setAddress] = useState(initial.address ?? '');
 const [places, setPlaces] = useState<Place[]>([]);
 const [searching, setSearching] = useState(false), [searchNote, setSearchNote] = useState('');
 const [summerCrop, setSummerCrop] = useState('soja');
 const [rotationsByCrop, setRotationsByCrop] = useState<Record<string, string>>({soja: 'soja__milho_safrinha', milho_verao: 'milho_verao__milho_safrinha'});
 const rotation = rotationsByCrop[summerCrop];
 const [stage, setStage] = useState('');
 const [harvest, setHarvest] = useState('');
 const today = useMemo(isoToday, []);
 const [date, setDate] = useState(today);
 const [sowingDate, setSowingDate] = useState('');
 const [pointHa, setPointHa] = useState('100');
 const [textureAuto, setTextureAuto] = useState<string | null>(null), [textureOrder, setTextureOrder] = useState<string[]>([]);
 const [problems, setProblems] = useState<string[]>([]);
 const [soil, setSoil] = useState<Record<string,string>>({});
 const [prices, setPrices] = useState<Record<string,string>>({});
 const [weights, setWeights] = useState<Pesos>({renda:5,solo:5,agua:5,pragas:5,risco:5});
 const [buyers, setBuyers] = useState<string[]>([]);
 const [header, setHeader] = useState(true), [seeder, setSeeder] = useState(true), [irrigation, setIrrigation] = useState(false);
 const [count, setCount] = useState(3), [error, setError] = useState('');
 const heading = useRef<HTMLHeadingElement>(null);
 useEffect(() => { window.scrollTo({ top: 0 }); heading.current?.focus({ preventScroll: true }); }, [step]);
 const toggle = (values: string[], value: string) => values.includes(value) ? values.filter(x => x !== value) : [...values, value];
 const field = (label: string, control: ReactNode) => {
   const optional = ['Fase da cultura de verão', 'Colheita prevista', 'Semeadura da 2ª safra', 'Cidade de referência', 'Endereço de referência'].includes(label);
   return <label className="field"><span className="wizard-field-label">{t(label)}{optional && <span className="wizard-field-optional">{say('opcional','optional')}</span>}</span>{control}</label>;
 };
 const more = (label: string, children: ReactNode) => <section className="wizard-open-section"><h2>{label}</h2><div className="wizard-more-content">{children}</div></section>;
 const choice = (selected: boolean, title: string, description: string, onClick: () => void, icon: string) => <button type="button" className={'wizard-choice-card' + (selected ? ' selected' : '')} aria-pressed={selected} onClick={onClick}><span className="wizard-choice-icon" aria-hidden="true">{icon}</span><span><strong>{title}</strong><span>{description}</span></span><span className="wizard-choice-check" aria-hidden="true">{selected ? '✓' : ''}</span></button>;
 function setTexture(key: string, value: string) {
   const order = [...textureOrder.filter(x => x !== key), ...(value !== '' ? [key] : [])];
   const next = { ...soil, [key]: value };
   const typed = order.filter(x => x !== textureAuto || x === key).slice(-2);
   const third = TEXTURE.find(x => !typed.includes(x))!;
   if (typed.length === 2) {
     const rest = 100 - typed.reduce((sum, x) => sum + Number(next[x] || 0), 0);
     next[third] = rest >= 0 ? String(Math.round(rest * 10) / 10) : '';
     setTextureAuto(third);
   } else {
     if (textureAuto && textureAuto !== key) next[textureAuto] = '';
     setTextureAuto(null);
   }
   setTextureOrder(typed);
   setSoil(next);
 }
 const numeric = (entries: Record<string,string>) => Object.fromEntries(Object.entries(entries).filter(([,v]) => v !== '').map(([k,v]) => [k, Number(v)]));
 /** Points that must fall inside Paraná (MVP coverage) for the marked area, or [] in demo mode. */
 function markedPoints(): LatLon[] {
   if (mode === 'point') {
     const lat = Number(farm.latitude), lon = Number(farm.longitude), ha = Number(pointHa);
     return ha > 0 ? [[lat, lon], ...square(lat, lon, ha)] : [[lat, lon]];
   }
   return mode === 'polygon' ? vertices : [];
 }
 const outsideCoverage = markedPoints().some(([lat, lon]) => !insideParana(lat, lon))
   && !(mode === 'point' && (!farm.latitude.trim() || !farm.longitude.trim()));
 function area(): Area {
   if (mode === 'demo') return { talhao_id: demo };
   if (outsideCoverage) throw Error(say('Sua área está fora da cobertura: nesta versão só analisamos propriedades no Paraná (PR). Ajuste o ponto ou o contorno para dentro do estado.','Your field is outside our coverage: this version only analyses properties in Paraná (PR). Move the pin or the boundary inside the state.'));
   if (mode === 'point') {
     const ha = Number(pointHa);
     if (!(ha >= 1 && ha <= 10000)) throw Error(say('Informe o tamanho da área entre 1 e 10.000 ha.','Enter a field size between 1 and 10,000 ha.'));
     // The engine turns a bare point into ~100 ha; any other size is sent as a square around the point.
     if (ha === 100) return { lat: Number(farm.latitude), lon: Number(farm.longitude) };
     const corners = square(Number(farm.latitude), Number(farm.longitude), ha);
     return { geometry: { type: 'Polygon', coordinates: [[...corners, corners[0]].map(([lat, lon]) => [lon, lat])] } };
   }
   if (vertices.length < 3) throw Error(say('Marque pelo menos 3 cantos da sua área no mapa.','Mark at least 3 corners of your field on the map.'));
   return { geometry: { type: 'Polygon', coordinates: [[...vertices, vertices[0]].map(([lat, lon]) => [lon, lat])] } };
 }
 /** Moves the map (and, when marking a point, the pin) to a city or an address. */
 function place(lat: number, lon: number, zoom: number) {
   setFocus({ lat, lon, zoom, key: Date.now() });
   if (mode === 'point') setFarm(current => ({ ...current, latitude: lat.toFixed(6), longitude: lon.toFixed(6) }));
 }
 function pickCity(value: string) {
   setCityQuery(value);
   const city = options.municipios.find(x => x.nome.toLocaleLowerCase('pt-BR') === value.trim().toLocaleLowerCase('pt-BR'));
   setFarm(current => ({ ...current, city: city ? `${city.nome}, PR` : value }));
   if (city) place(city.lat, city.lon, 13);
 }
 async function searchAddress() {
   const query = address.trim();
   if (!query) return;
   setSearching(true); setSearchNote(''); setPlaces([]);
   const city = cityQuery.trim();
   const params = new URLSearchParams({ q: `${query}${city && !query.toLocaleLowerCase('pt-BR').includes(city.toLocaleLowerCase('pt-BR')) ? `, ${city}` : ''}, Paraná`, format: 'jsonv2', limit: '5', countrycodes: 'br', viewbox: '-54.7,-22.4,-47.9,-26.8', bounded: '1', 'accept-language': en ? 'en' : 'pt-BR' });
   try {
     const response = await fetch('https://nominatim.openstreetmap.org/search?' + params);
     if (!response.ok) throw Error(String(response.status));
     const found = (await response.json() as { display_name: string; lat: string; lon: string }[]).map(x => ({ label: x.display_name, lat: Number(x.lat), lon: Number(x.lon) }));
     setPlaces(found);
     if (!found.length) setSearchNote(say('Não encontramos esse endereço no Paraná. Tente incluir a cidade ou marque direto no mapa.','We couldn’t find this address in Paraná. Try adding the city or mark it on the map.'));
   } catch {
     setSearchNote(say('Não foi possível buscar o endereço agora. Marque direto no mapa ou informe as coordenadas.','The address search is unavailable right now. Mark it on the map or enter the coordinates.'));
   } finally { setSearching(false); }
 }
 function choosePlace(found: Place) {
   setPlaces([]); setSearchNote('');
   setFarm(current => ({ ...current, address: found.label }));
   place(found.lat, found.lon, 16);
 }
 function advance() {
   setError('');
   try {
     if (step === 0) area();
     if (step === 3 && ((soil.argila_pct ?? '') === '') !== ((soil.areia_pct ?? '') === '')) throw Error(say('Para informar a textura, preencha argila e areia juntas.','To provide soil texture, enter both clay and sand.'));
     if (step === 3 && Object.values(soil).some(v => v !== '') && !['argila_pct','p_mg_dm3','k_cmolc_dm3','ca_cmolc_dm3','mg_cmolc_dm3','al_cmolc_dm3','v_pct','ctc_cmolc_dm3'].some(k => (soil[k] ?? '') !== '')) throw Error(say('Inclua argila e areia ou um dado de fertilidade para usar a análise. Você também pode continuar sem análise.','Include clay and sand or a fertility value to use this test. You can also continue without a soil test.'));
     if (step === 3 && Number(soil.argila_pct || 0) + Number(soil.areia_pct || 0) > 100) throw Error(say('Argila e areia devem somar no máximo 100%.','Clay and sand must total no more than 100%.'));
     if (step === 4 && !Object.values(weights).some(v => v > 0)) throw Error(say('Dê um peso maior que zero a pelo menos uma prioridade.','Give at least one priority a weight above zero.'));
     if (step < LAST) { setStep(step + 1); return; }
     const selected = options.talhoes_demo.find(x => x.id === demo)!;
     const { silte_pct: _silt, ...soilForEngine } = soil;
     const completed = { ...farm, irrigation: irrigation ? 'Sim' : 'Não', crop: rotation.startsWith('soja__') ? 'Soja' : 'Milho', ...(mode === 'demo' ? {latitude: String(selected.lat), longitude: String(selected.lon), area: String(selected.area_ha), city: `${selected.municipio}, PR`} : mode === 'point' ? {area: pointHa} : mode === 'polygon' ? {latitude: (vertices.reduce((s, [lat]) => s + lat, 0) / vertices.length).toFixed(6), longitude: (vertices.reduce((s, [, lon]) => s + lon, 0) / vertices.length).toFixed(6), area: hectares(vertices).toFixed(1)} : {}), ...(soil.argila_pct && soil.areia_pct ? {texture: textureFromSoil(Number(soil.argila_pct), Number(soil.areia_pct))} : {}), ...(soil.ph ? {ph: soil.ph} : {}), ...(soil.materia_organica_pct ? {organic: soil.materia_organica_pct} : {}) };
     onComplete(completed, { area: area(), rotacao_atual: rotation, pesos: weights, n_alternativas: count,
       ...(stage ? {estagio_verao: stage} : {}), ...(harvest ? {colheita_prevista: `${harvest.slice(8, 10)}/${harvest.slice(5, 7)}`} : {}), data_referencia: date,
       ...(sowingDate ? {semeadura_safrinha: engineSowing(sowingDate, options.semeaduras)} : {}), problemas_area: problems,
       ...(Object.keys(numeric(soilForEngine)).length ? {analise_solo: numeric(soilForEngine)} : {}),
       ...(Object.keys(numeric(prices)).length ? {ajustes: {precos: numeric(prices)}} : {}),
       restricoes: {sem_comprador: buyers, maquinas: {plataforma_milho: header, semeadora_consorcio: seeder}}, irrigacao: {disponivel: irrigation} });
   } catch (e) { setError((e as Error).message); }
 }
 const chosen = PRIORITIES.find(p => p.id === priority);
 const priorityName = chosen ? (en ? chosen.short.en : chosen.short.pt) : say('Do seu jeito','Your own balance');
 const soilCount = Object.values(soil).filter(v => v !== '').length;
 const summer = options.culturas_verao.find(x => x.id === options.combinacoes.find(c => c.id === rotation)?.verao);
 const sample = options.talhoes_demo.find(x => x.id === demo)!;
 const sampleFocus = useMemo<MapFocus>(() => ({ lat: sample.lat, lon: sample.lon, zoom: 14, key: Number(sample.id) }), [sample]);
 const number = (value: number, digits = 1) => value.toLocaleString(en ? 'en-US' : 'pt-BR', { maximumFractionDigits: digits });
 const sowingLabel = (ddmm: string) => { const [day, month] = ddmm.split('/').map(Number); return `${day} ${new Date(2026, month - 1, 15).toLocaleDateString(en ? 'en-US' : 'pt-BR', { month: 'short' }).replace('.', '')}`; };
 const yesNo = (name: string, label: string, value: boolean, set: (v: boolean) => void) => <div className="wizard-buyer-row" key={name}><span>{label}</span><span className="wizard-segmented is-compact" role="radiogroup" aria-label={label}>
  <label><input type="radio" name={`yn-${name}`} checked={value} onChange={() => set(true)}/><span>{say('Sim','Yes')}</span></label>
  <label><input type="radio" name={`yn-${name}`} checked={!value} onChange={() => set(false)}/><span>{say('Não','No')}</span></label>
 </span></div>;
 const goBack = () => { setError(''); if (step === 0) onHome(); else setStep(step - 1); };
 const drawnHa = hectares(vertices);
 return <div className={`signup property-wizard wizard-step-${step}`}>
  <section className="signup-photo"><img src="/assets/hero-br-parana-v1.webp" alt={t('Campos de cultivo')}/>{brand}<div><h1>{t('Sua terra merece')}<br/>{t('um novo olhar.')}</h1><p>{t(copy[step][2])}</p></div></section>
  <section className="signup-form">
   <div className="signup-header wizard-header"><button type="button" className="wizard-top-back" onClick={goBack}><span aria-hidden="true">←</span>{step === 0 ? t('Voltar ao início') : t('Voltar')}</button><LanguageSwitcher/></div>
   <nav className="wizard-progress" aria-label={say('Etapas do cadastro','Setup steps')}><span>{say('Etapa','Step')} {step + 1} {say('de','of')} {copy.length}</span><ol>{copy.map(([label], i) => <li key={label} aria-current={step === i ? 'step' : undefined} className={i <= step ? 'is-active' : ''}><span className="sr-only">{t(label)}</span></li>)}</ol></nav>
   <small>{t(copy[step][0])}{OPTIONAL_STEPS.includes(step) && <span className="wizard-optional">{say('Etapa opcional','Optional step')}</span>}</small>
   <h1 ref={heading} tabIndex={-1}>{t(copy[step][1])}</h1><p>{t(copy[step][2])}</p>
   <form onSubmit={e => { e.preventDefault(); advance(); }}>
    <div className="wizard-fields" key={step}>
    {step === 0 && <>
     <p className="coverage-notice" role="note"><strong>{say('Cobertura: somente Paraná (PR).','Coverage: Paraná (PR) only.')}</strong> {say('Os dados de solo, relevo, clima e custos usados nas recomendações foram preparados apenas para propriedades no estado.','The soil, relief, climate and cost data behind the recommendations were prepared only for properties in that state.')}</p>
     <div className="wizard-card-stack">
      {choice(mode === 'demo', say('Quero conhecer primeiro','I’d like to explore first'), say('Experimente com uma área de exemplo.','Try things out with a sample field.'), () => setMode('demo'), '✦')}
      {choice(mode !== 'demo', say('Vamos olhar para minha terra','Let’s look at my land'), say('Marque sua área no mapa.','Mark your land on the map.'), () => setMode('point'), '⌖')}
     </div>
     {mode === 'demo' && more(say('Sua área de exemplo','Your sample field'), <>
      {field('Talhão', <select value={demo} onChange={e => setDemo(e.target.value)}>{options.talhoes_demo.map(x => <option key={x.id} value={x.id}>{`${say('Talhão','Field')} ${x.id} · ${x.municipio} · ${number(x.area_ha)} ha`}</option>)}</select>)}
      <div className="wizard-sample">
       <dl className="wizard-sample-facts">
        <div><dt>{say('Município','Municipality')}</dt><dd>{sample.municipio}, PR</dd></div>
        <div><dt>{say('Área','Area')}</dt><dd>{number(sample.area_ha)} ha</dd></div>
        <div><dt>{say('Coordenadas','Coordinates')}</dt><dd>{number(sample.lat, 4)}, {number(sample.lon, 4)}</dd></div>
        <div><dt>{say('Origem','Source')}</dt><dd>{say('Contorno real de lavoura, mapeado por satélite (Fields of The World)','Real field boundary mapped from satellite imagery (Fields of The World)')}</dd></div>
       </dl>
       <LocationMap mode="view" latitude={String(sample.lat)} longitude={String(sample.lon)} focus={sampleFocus} zoom={14}/>
      </div>
     </>)}
     {mode !== 'demo' && <>
      <div className="wizard-grid wizard-finder">
       {field('Cidade de referência', <><input list="wizard-cities" value={cityQuery} onChange={e => pickCity(e.target.value)} placeholder={say('Digite para buscar','Type to search')} autoComplete="off"/><datalist id="wizard-cities">{options.municipios.map(x => <option key={x.id} value={x.nome}/>)}</datalist></>)}
       {field('Endereço de referência', <div className="wizard-search"><input value={address} onChange={e => setAddress(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); searchAddress(); } }} placeholder={say('Ex.: Linha Gaúcha, km 4','e.g. Linha Gaúcha, km 4')}/><button type="button" onClick={searchAddress} disabled={searching || !address.trim()}>{searching ? say('Buscando…','Searching…') : say('Buscar','Search')}</button></div>)}
      </div>
      {places.length > 0 && <ul className="wizard-places" aria-label={say('Endereços encontrados','Addresses found')}>{places.map(x => <li key={`${x.lat},${x.lon}`}><button type="button" onClick={() => choosePlace(x)}>{x.label}</button></li>)}</ul>}
      {searchNote && <p className="wizard-hint" role="status">{searchNote}</p>}
      <div className="wizard-segmented" role="radiogroup" aria-label={say('Como marcar sua área','How to mark your field')}>
       <label><input type="radio" name="mark-mode" checked={mode === 'point'} onChange={() => setMode('point')}/><span><span aria-hidden="true">⌖</span>{say('Marcar um ponto','Drop a pin')}</span></label>
       <label><input type="radio" name="mark-mode" checked={mode === 'polygon'} onChange={() => setMode('polygon')}/><span><span aria-hidden="true">⬠</span>{say('Desenhar o contorno','Draw the boundary')}</span></label>
      </div>
      <LocationMap mode={mode === 'polygon' ? 'polygon' : 'point'} latitude={farm.latitude} longitude={farm.longitude} onChange={(latitude, longitude) => setFarm(current => ({...current, latitude, longitude}))} vertices={vertices} onVerticesChange={setVertices} focus={focus} pointHa={Number(pointHa) > 0 ? Number(pointHa) : undefined}/>
      {mode === 'point' && <><div className="wizard-grid wizard-point-grid">{(['latitude','longitude'] as const).map(k => <div key={k}>{field(k === 'latitude' ? 'Latitude' : 'Longitude', <input required type="number" step="any" min={k === 'latitude' ? -27 : -55} max={k === 'latitude' ? -22 : -48} value={farm[k]} onChange={e => setFarm({...farm,[k]:e.target.value})}/>)}</div>)}<div>{field('Tamanho da área (ha)', <input required type="number" min="1" max="10000" step="any" value={pointHa} onChange={e => setPointHa(e.target.value)}/>)}</div></div><p className="wizard-hint">{say('O quadrado no mapa mostra a área analisada ao redor do ponto. Para o formato exato, desenhe o contorno.','The square on the map shows the area analysed around the point. For the exact shape, draw the boundary.')}</p></>}
      {outsideCoverage && <p className="wizard-error" role="alert">{say('Fora da área de cobertura: marque um ponto ou contorno dentro do Paraná.','Outside the coverage area: mark a pin or boundary inside Paraná.')}</p>}
      {mode === 'polygon' && <div className="wizard-polygon-bar">
       <span role="status">{vertices.length < 3 ? say(`${vertices.length} de 3 cantos marcados`, `${vertices.length} of 3 corners marked`) : say(`Contorno com ${vertices.length} cantos · cerca de ${number(drawnHa)} ha`, `Boundary with ${vertices.length} corners · about ${number(drawnHa)} ha`)}</span>
       <span><button type="button" className="wizard-inline-link" disabled={!vertices.length} onClick={() => setVertices(vertices.slice(0, -1))}>{say('Desfazer último canto','Undo last corner')}</button><button type="button" className="wizard-inline-link" disabled={!vertices.length} onClick={() => setVertices([])}>{say('Limpar','Clear')}</button></span>
      </div>}
     </>}
     {more(say('Sua propriedade · opcional','Your farm · optional'), field('Nome da propriedade', <input value={farm.name} onChange={e => setFarm({...farm,name:e.target.value})}/>))}
    </>}
    {step === 1 && <>
     <fieldset className="wizard-rotation"><legend>{t('Rotação atual (verão → 2ª safra)')}</legend><div className="wizard-grid">
      {options.culturas_verao.map(crop => {
       const selected = summer?.id === crop.id;
       const rotations = options.combinacoes.filter(x => x.valida && x.verao === crop.id);
       const cropRotation = rotationsByCrop[crop.id];
       const selectRotation = (id: string) => {setRotationsByCrop(current => ({...current, [crop.id]: id}));setSummerCrop(crop.id);if (!selected) setStage('');};
       return <div key={crop.id} className={'wizard-rotation-group' + (selected ? ' selected' : '')}>
        <label className="wizard-rotation-heading"><input type="radio" name="summer-crop" checked={selected} onChange={() => selectRotation(cropRotation)}/><span>{crop.id === 'soja' ? t('Soja') : t('Milho')}</span><small>{say('no verão','in summer')}</small></label>
        <label className="field"><span className="wizard-field-label">{say('Depois, na 2ª safra','Then, in the second season')}</span><select aria-label={say(`Segunda safra depois de ${crop.id === 'soja' ? 'soja' : 'milho'}`, `Second crop after ${crop.id === 'soja' ? 'soybean' : 'corn'}`)} value={cropRotation} onChange={e => selectRotation(e.target.value)}>{rotations.map(x => <option key={x.id} value={x.id}>{(() => { const label = t(x.nome).split('→').slice(1).join('→').trim(); return label.charAt(0).toLocaleUpperCase(en ? 'en-US' : 'pt-BR') + label.slice(1); })()}</option>)}</select></label>
       </div>;
      })}
     </div></fieldset>
     {more(say('O momento da sua lavoura · opcional','Your crop timing · optional'), <>
     {field('Fase da cultura de verão', <select value={stage} onChange={e => setStage(e.target.value)}><option value="">{say('Não sei informar','I’m not sure')}</option>{summer?.estagios.map(x => <option key={x.id} value={x.id}>{t(x.nome)}</option>)}</select>)}
     <div className="wizard-grid wizard-dates">{field('Colheita prevista', <input type="date" value={harvest} onChange={e => setHarvest(e.target.value)}/>)}
      {field('Semeadura da 2ª safra', <div className="wizard-reference-input is-inline"><input type="date" value={sowingDate} onChange={e => setSowingDate(e.target.value)}/>{sowingDate && <button type="button" className="wizard-inline-link" onClick={() => setSowingDate('')}>{say('Deixar automática','Make it automatic')}</button>}</div>)}</div>
     <p className="wizard-hint" role="status">{!sowingDate
      ? say('Em branco, calculamos a semeadura a partir da colheita do verão.','If left blank, we work out the sowing date from the summer harvest.')
      : (() => { const used = engineSowing(sowingDate, options.semeaduras); const exact = `${sowingDate.slice(8, 10)}/${sowingDate.slice(5, 7)}` === used;
        return exact ? say(`O motor vai avaliar a semeadura em ${sowingLabel(used)}.`, `The engine will evaluate sowing on ${sowingLabel(used)}.`)
         : say(`O motor avalia a semeadura em datas de referência entre 15 jan e 15 mar. Para essa data, vamos usar ${sowingLabel(used)}.`, `The engine evaluates sowing on reference dates from 15 Jan to 15 Mar. For this date, we’ll use ${sowingLabel(used)}.`); })()}</p>
     <div className="wizard-reference">
      <div><strong>{t('Data de referência')}</strong><p>{say('É o “hoje” da simulação: usamos essa data para saber em que fase a lavoura está e o que ainda dá tempo de plantar. Mude só se quiser simular outra época.','It is the “today” of the simulation: we use it to know where your crop stands and what there is still time to plant. Change it only to simulate another time of year.')}</p></div>
      <div className="wizard-reference-input"><input aria-label={t('Data de referência')} required type="date" value={date} onChange={e => setDate(e.target.value)}/>{date !== today && <button type="button" className="wizard-inline-link" onClick={() => setDate(today)}>{say('Usar hoje','Use today')}</button>}</div>
     </div>
     <p className="wizard-hint">{say('Se você não souber a fase nem a colheita, usaremos uma estimativa de calendário.','If you don’t know the stage or harvest date, we’ll use a calendar estimate.')}</p>
     </>)}
     
    </>}
    {step === 2 && <><fieldset className="wizard-choices"><legend>{say('Problemas conhecidos','Known issues')}</legend>{PROBLEMS.map(([id,label]) => <label key={id}><input type="checkbox" checked={problems.includes(id)} onChange={() => setProblems(toggle(problems,id))}/>{t(label)}</label>)}</fieldset><p className="wizard-hint">{say('Nenhum conhecido? Pode continuar sem marcar nada.','No known issues? You can continue without selecting anything.')}</p></>}
    {step === 3 && <>
      
      <div className="wizard-grid wizard-soil-grid">{soilFields.map(([id,label]) => <div key={id} className={textureAuto === id ? 'is-calculated' : undefined}>{field(label, <input type="number" step="any" min={id === 'ph' ? 3 : 0} max={soilMax[id] ?? 100} value={soil[id] ?? ''} onChange={e => TEXTURE.includes(id) ? setTexture(id, e.target.value) : setSoil({...soil,[id]:e.target.value})}/>)}{textureAuto === id && <span className="wizard-calculated">{say('calculado','calculated')}</span>}</div>)}</div><p className="wizard-hint">{say('Argila, silte e areia somam 100%: preencha duas e calculamos a terceira.','Clay, silt and sand add up to 100%: fill in two and we work out the third.')}</p>
      <div className="wizard-live-note" role="status">{Object.values(soil).filter(v => v !== '').length ? say(`${Object.values(soil).filter(v => v !== '').length} informações do seu solo adicionadas.`, `${Object.values(soil).filter(v => v !== '').length} soil values added.`) : say('Por enquanto, vamos usar dados públicos de solo quando disponíveis.','For now, we’ll use public soil data where available.')}</div>
    </>}
    {step === 4 && <>
      <div className="wizard-card-stack">{PRIORITIES.map(p => <div key={p.id}>{choice(priority === p.id, en ? p.title.en : p.title.pt, en ? p.description.en : p.description.pt, () => {setPriority(p.id);setWeights(p.pesos);}, p.icon)}</div>)}</div>
      {more(say('Ajuste do seu jeito','Make it your own'), <div className="wizard-slider-grid">{options.criterios.map(({id,nome}) => <label className="wizard-slider" key={id}><span>{t(nome)}<output className="wizard-weight-value">{weights[id as keyof Pesos]}<span>/10</span></output></span><input type="range" min="0" max="10" value={weights[id as keyof Pesos]} onChange={e => {setPriority('custom');setWeights({...weights,[id]:Number(e.target.value)});}}/><span className="wizard-range-labels"><span>{say('Menor prioridade','Lower priority')}</span><span>{say('Maior prioridade','Higher priority')}</span></span></label>)}</div>)}
    </>}
    {step === 5 && <>
     <div className="wizard-column">
     {more(say('Comprador para a 2ª safra','Buyers for the second crop'), <fieldset className="wizard-buyers"><legend>{say('Você tem comprador para…','Do you have a buyer for…')}</legend>
      {commodities.filter(([id]) => id !== 'soja').map(([id,label]) => <div className="wizard-buyer-row" key={id}><span>{t(label)}</span><span className="wizard-segmented is-compact" role="radiogroup" aria-label={say(`Tem comprador para ${label.toLocaleLowerCase('pt-BR')}?`, `Buyer for ${t(label).toLocaleLowerCase('en-US')}?`)}>
       <label><input type="radio" name={`buyer-${id}`} checked={!buyers.includes(id)} onChange={() => setBuyers(buyers.filter(x => x !== id))}/><span>{say('Sim','Yes')}</span></label>
       <label><input type="radio" name={`buyer-${id}`} checked={buyers.includes(id)} onChange={() => setBuyers([...buyers.filter(x => x !== id), id])}/><span>{say('Não','No')}</span></label>
      </span></div>)}
      <p className="wizard-hint">{say('Culturas marcadas com “Não” saem das sugestões.','Crops marked “No” are left out of the suggestions.')}</p>
     </fieldset>)}
     </div>
     <div className="wizard-column">
     {more(say('Máquinas e irrigação','Equipment and irrigation'), <fieldset className="wizard-buyers"><legend>{say('Você tem…','Do you have…')}</legend>
      {yesNo('header', say('Plataforma de milho','Corn header'), header, setHeader)}
      {yesNo('seeder', say('Semeadora de consórcio','Intercropping seeder'), seeder, setSeeder)}
      {yesNo('irrigation', say('Irrigação','Irrigation'), irrigation, setIrrigation)}
     </fieldset>)}
     </div>
    </>}
    {step === LAST && <>
     <div className="wizard-ready"><span>{say('Seu ponto de partida','Your starting point')}</span><strong>{t(options.combinacoes.find(x => x.id === rotation)?.nome ?? rotation)}</strong><p>{priorityName} · {soilCount ? say(`${soilCount} dados de solo`, `${soilCount} soil values`) : say('Solo com dados públicos','Public soil data')}</p></div>
     {more(say('Seus preços','Your prices'), <><p className="wizard-hint">{say('R$/saca. Em branco, usamos os preços de referência.','BRL per sack. Leave blank to use reference prices.')}</p><div className="wizard-prices">{commodities.map(([id,label]) => <label key={id} className="wizard-price-row"><span>{t(label)}</span><span className="wizard-price-input"><input type="number" min="0" step="any" placeholder={say('referência','reference')} value={prices[id] ?? ''} onChange={e => setPrices({...prices,[id]:e.target.value})}/><small>R$/sc</small></span></label>)}</div>
</>)}
     {more(say('Quantos cenários ver','How many scenarios to see'), <fieldset className="wizard-buyers"><legend>{say('Alternativas à sua rotação atual','Alternatives to your current rotation')}</legend>
      <div className="wizard-pills">{[1,2,3,4,5,6].map(n => <label key={n}><input type="radio" name="count" checked={count === n} onChange={() => setCount(n)}/><span>{n}</span></label>)}</div>
      <p className="wizard-hint">{say('O motor mostra até esse número de opções, ordenadas pela nota. Mais opções deixam a comparação mais ampla.','The engine shows up to this many options, sorted by score. More options widen the comparison.')}</p>
     </fieldset>)}
    </>}
    </div>
    {error && <p className="wizard-error" role="alert">{error}</p>}
    <div className="wizard-actions"><button className="button yellow" type="submit">{step === LAST ? say('Explorar meus cenários →','Explore my scenarios →') : step === 2 && !problems.length ? say('Continuar sem marcar →','Continue without selecting →') : step === 3 && !Object.values(soil).some(v => v !== '') ? say('Vamos seguir sem análise →','Let’s continue without a soil test →') : say('Vamos continuar →','Let’s continue →')}</button></div>
    <small>{say('Seus dados ficam salvos neste navegador.','Your data is saved in this browser.')}</small>
   </form>
  </section>
 </div>;
}
