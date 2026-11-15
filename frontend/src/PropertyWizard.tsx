import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import type { Farm } from './data';
import type { Area, Pesos } from './api';
import { LanguageSwitcher, t, useLanguage } from './i18n';
import options from './setup-options.json';
import './property-wizard.css';
import LocationMap from './LocationMap';

export type SetupInputs = {
  area: Area; rotacao_atual: string; pesos: Pesos; n_alternativas: number;
  estagio_verao?: string; colheita_prevista?: string; data_referencia: string; semeadura_safrinha?: string;
  problemas_area: string[]; analise_solo?: Record<string, number>;
  ajustes?: { precos: Record<string, number> };
  restricoes: { sem_comprador: string[]; maquinas: { plataforma_milho: boolean; semeadora_consorcio: boolean } };
  irrigacao: { disponivel: boolean };
};
const soilFields = [['argila_pct','Argila (%)'],['areia_pct','Areia (%)'],['materia_organica_pct','Matéria orgânica (%)'],['ph','pH'],['p_mg_dm3','Fósforo (mg/dm³)'],['k_cmolc_dm3','Potássio (cmolc/dm³)'],['ca_cmolc_dm3','Cálcio (cmolc/dm³)'],['mg_cmolc_dm3','Magnésio (cmolc/dm³)'],['al_cmolc_dm3','Alumínio (cmolc/dm³)'],['v_pct','Saturação por bases (%)'],['ctc_cmolc_dm3','CTC (cmolc/dm³)']];
const soilMax: Record<string, number> = {ph:9, p_mg_dm3:500, k_cmolc_dm3:10, ca_cmolc_dm3:40, mg_cmolc_dm3:20, al_cmolc_dm3:15, ctc_cmolc_dm3:60};
const commodities = [['soja','Soja'],['milho','Milho'],['trigo','Trigo'],['feijao','Feijão'],['sorgo','Sorgo']];
const copy = [
 ['Vamos começar','Um novo olhar começa aqui.','Vamos conhecer um pouquinho da sua terra. No seu tempo.'],
 ['Sua lavoura','O que você cultiva hoje?','Começamos com o que já faz parte da sua rotina.'],
 ['Seu olhar','Como sua terra tem estado?','Se algo tem preocupado você, pode nos contar.'],
 ['Seu solo','Vamos olhar para o solo?','Preencha o que souber ou siga sem análise.'],
 ['Seu próximo ciclo','O que importa para você?','Escolha uma prioridade e ajuste se quiser.'],
 ['Tudo pronto','Vamos aos seus cenários?','Os detalhes abaixo são opcionais.'],
];
export default function PropertyWizard({ initial, brand, onHome, onComplete }: { initial: Farm; brand: ReactNode; onHome: () => void; onComplete: (farm: Farm, inputs: SetupInputs) => void }) {
 const { language } = useLanguage();
 const en = language === 'en';
 const say = (pt: string, english: string) => en ? english : pt;
 const [step, setStep] = useState(0);
 const [priority, setPriority] = useState('balanced');
 const [farm, setFarm] = useState(initial);
 const [mode, setMode] = useState('demo');
 const [demo, setDemo] = useState('72638');
 const [polygon, setPolygon] = useState('');
 const [summerCrop, setSummerCrop] = useState('soja');
 const [rotationsByCrop, setRotationsByCrop] = useState<Record<string, string>>({soja: 'soja__milho_safrinha', milho_verao: 'milho_verao__milho_safrinha'});
 const rotation = rotationsByCrop[summerCrop];
 const [stage, setStage] = useState('');
 const [harvest, setHarvest] = useState('');
 const [date, setDate] = useState(() => new Date().toLocaleDateString('en-CA', { timeZone: 'America/Sao_Paulo' }));
 const [sowing, setSowing] = useState('');
 const [problems, setProblems] = useState<string[]>([]);
 const [soil, setSoil] = useState<Record<string,string>>({});
 const [prices, setPrices] = useState<Record<string,string>>({});
 const [weights, setWeights] = useState<Pesos>({renda:5,solo:5,agua:5,pragas:5,risco:5});
 const [buyers, setBuyers] = useState<string[]>([]);
 const [header, setHeader] = useState(true), [seeder, setSeeder] = useState(true), [irrigation, setIrrigation] = useState(false);
 const [count, setCount] = useState(3), [error, setError] = useState('');
 const heading = useRef<HTMLHeadingElement>(null);
 useEffect(() => { heading.current?.focus(); }, [step]);
 const toggle = (values: string[], value: string) => values.includes(value) ? values.filter(x => x !== value) : [...values, value];
 const field = (label: string, control: ReactNode) => {
   const optional = ['Fase da cultura de verão', 'Colheita prevista (dia/mês)', 'Semeadura da 2ª safra'].includes(label);
   return <label className="field"><span className="wizard-field-label">{t(label)}{optional && <span className="wizard-field-optional">{say('opcional','optional')}</span>}</span>{control}</label>;
 };
 const more = (label: string, children: ReactNode) => <section className="wizard-open-section"><h2>{label}</h2><div className="wizard-more-content">{children}</div></section>;
 const choice = (selected: boolean, title: string, description: string, onClick: () => void, icon: string) => <button type="button" className={'wizard-choice-card' + (selected ? ' selected' : '')} aria-pressed={selected} onClick={onClick}><span className="wizard-choice-icon" aria-hidden="true">{icon}</span><span><strong>{title}</strong><span>{description}</span></span><span className="wizard-choice-check" aria-hidden="true">{selected ? '✓' : ''}</span></button>;
 const numeric = (entries: Record<string,string>) => Object.fromEntries(Object.entries(entries).filter(([,v]) => v !== '').map(([k,v]) => [k, Number(v)]));
 function area(): Area {
   if (mode === 'demo') return { talhao_id: demo };
   if (mode === 'point') return { lat: Number(farm.latitude), lon: Number(farm.longitude) };
   const parsed = JSON.parse(polygon);
   const geometry = parsed.type === 'Feature' ? parsed.geometry : parsed;
   if (!geometry || !['Polygon','MultiPolygon'].includes(geometry.type) || !Array.isArray(geometry.coordinates) || !geometry.coordinates.length) throw Error(say('Informe um polígono GeoJSON válido.','Enter a valid GeoJSON polygon.'));
   return { geometry };
 }
 function advance() {
   setError('');
   try {
     if (step === 0) area();
     if (step === 1 && harvest) {
       const [day, month] = harvest.split('/').map(Number);
       if (!/^\d{2}\/\d{2}$/.test(harvest) || month < 1 || month > 12 || day < 1 || day > new Date(2028, month, 0).getDate()) throw Error(say('Confira a colheita prevista: use dia/mês, como 05/01.','Check the expected harvest: use day/month, such as 05/01.'));
     }
     if (step === 3 && ((soil.argila_pct ?? '') === '') !== ((soil.areia_pct ?? '') === '')) throw Error(say('Para informar a textura, preencha argila e areia juntas.','To provide soil texture, enter both clay and sand.'));
     if (step === 3 && Object.values(soil).some(v => v !== '') && !['argila_pct','p_mg_dm3','k_cmolc_dm3','ca_cmolc_dm3','mg_cmolc_dm3','al_cmolc_dm3','v_pct','ctc_cmolc_dm3'].some(k => (soil[k] ?? '') !== '')) throw Error(say('Inclua argila e areia ou um dado de fertilidade para usar a análise. Você também pode continuar sem análise.','Include clay and sand or a fertility value to use this test. You can also continue without a soil test.'));
     if (step === 3 && Number(soil.argila_pct || 0) + Number(soil.areia_pct || 0) > 100) throw Error(say('Argila e areia devem somar no máximo 100%.','Clay and sand must total no more than 100%.'));
     if (step === 4 && !Object.values(weights).some(v => v > 0)) throw Error(say('Dê um peso maior que zero a pelo menos uma prioridade.','Give at least one priority a weight above zero.'));
     if (step < 5) { setStep(step + 1); return; }
     const selected = options.talhoes_demo.find(x => x.id === demo)!;
     const completed = { ...farm, irrigation: irrigation ? 'Sim' : 'Não', crop: rotation.startsWith('soja__') ? 'Soja' : 'Milho', ...(mode === 'demo' ? {latitude: String(selected.lat), longitude: String(selected.lon), area: String(selected.area_ha)} : mode === 'polygon' ? {latitude: '', longitude: ''} : {}), ...(soil.ph ? {ph: soil.ph} : {}), ...(soil.materia_organica_pct ? {organic: soil.materia_organica_pct} : {}) };
     onComplete(completed, { area: area(), rotacao_atual: rotation, pesos: weights, n_alternativas: count,
       ...(stage ? {estagio_verao: stage} : {}), ...(harvest ? {colheita_prevista: harvest} : {}), data_referencia: date,
       ...(sowing ? {semeadura_safrinha: sowing} : {}), problemas_area: problems,
       ...(Object.keys(numeric(soil)).length ? {analise_solo: numeric(soil)} : {}),
       ...(Object.keys(numeric(prices)).length ? {ajustes: {precos: numeric(prices)}} : {}),
       restricoes: {sem_comprador: buyers, maquinas: {plataforma_milho: header, semeadora_consorcio: seeder}}, irrigacao: {disponivel: irrigation} });
   } catch (e) { setError(e instanceof SyntaxError ? say('Confira o GeoJSON antes de continuar.','Check the GeoJSON before continuing.') : (e as Error).message); }
 }
 const priorityName = priority === 'income' ? say('Mais retorno','More return') : priority === 'soil' ? say('Cuidar da terra','Care for the land') : priority === 'risk' ? say('Mais tranquilidade','More peace of mind') : priority === 'custom' ? say('Do seu jeito','Your own balance') : say('Equilíbrio','Balance');
 const soilCount = Object.values(soil).filter(v => v !== '').length;
 const summer = options.culturas_verao.find(x => x.id === options.combinacoes.find(c => c.id === rotation)?.verao);
 return <div className={`signup property-wizard wizard-step-${step}`}>
  <section className="signup-photo"><img src="/assets/hero-br-parana-v1.webp" alt={t('Campos de cultivo')}/>{brand}<div><h1>{t('Sua terra merece')}<br/>{t('um novo olhar.')}</h1><p>{t(copy[step][2])}</p></div></section>
  <section className="signup-form">
   <div className="signup-header"><button className="back-link" onClick={onHome}>{t('Voltar ao início')}</button><LanguageSwitcher/></div>
   <nav className="wizard-progress" aria-label={say('Etapas do cadastro','Setup steps')}><span>{say('Etapa','Step')} {step + 1} {say('de','of')} 6</span><ol>{copy.map(([label], i) => <li key={label} aria-current={step === i ? 'step' : undefined} className={i <= step ? 'is-active' : ''}><span className="sr-only">{t(label)}</span></li>)}</ol></nav>
   <small>{t(copy[step][0])}{[2,3,5].includes(step) && <span className="wizard-optional">{say('Etapa opcional','Optional step')}</span>}</small>
   <h1 ref={heading} tabIndex={-1}>{t(copy[step][1])}</h1><p>{t(copy[step][2])}</p>
   <form onSubmit={e => { e.preventDefault(); advance(); }}>
    <div className="wizard-fields" key={step}>
    {step === 0 && <>
     <div className="wizard-card-stack">
      {choice(mode === 'demo', say('Quero conhecer primeiro','I’d like to explore first'), say('Experimente com uma área de exemplo.','Try things out with a sample field.'), () => setMode('demo'), '✦')}
      {choice(mode !== 'demo', say('Vamos olhar para minha terra','Let’s look at my land'), say('Marque sua área no mapa.','Mark your land on the map.'), () => setMode('point'), '⌖')}
     </div>
     {mode === 'demo' && more(say('Sua área de exemplo','Your sample field'), field('Talhão', <select value={demo} onChange={e => setDemo(e.target.value)}>{options.talhoes_demo.map(x => <option key={x.id} value={x.id}>{x.id} · {x.area_ha} ha</option>)}</select>))}
     {mode !== 'demo' && <>
      {mode === 'point' && <><LocationMap latitude={farm.latitude} longitude={farm.longitude} onChange={(latitude, longitude) => setFarm(current => ({...current, latitude, longitude}))}/><div className="wizard-grid">{(['latitude','longitude'] as const).map(k => <div key={k}>{field(k === 'latitude' ? 'Latitude' : 'Longitude', <input required type="number" step="any" min={k === 'latitude' ? -90 : -180} max={k === 'latitude' ? 90 : 180} value={farm[k]} onChange={e => setFarm({...farm,[k]:e.target.value})}/>)}</div>)}</div><p className="wizard-hint">{say('Usaremos uma área aproximada de 100 ha ao redor desse ponto.','We’ll use an area of about 100 ha around this point.')}</p></>}
      <button className="wizard-inline-link" type="button" onClick={() => setMode(mode === 'polygon' ? 'point' : 'polygon')}>{mode === 'polygon' ? say('Prefiro usar coordenadas','I’d rather use coordinates') : say('Tenho o contorno da área em GeoJSON','I have the field boundary in GeoJSON')}</button>
      {mode === 'polygon' && field('Polígono GeoJSON', <textarea required value={polygon} onChange={e => setPolygon(e.target.value)} placeholder='{"type":"Polygon","coordinates":[…]}'/>)}
     </>}
     {more(say('Sua propriedade · opcional','Your farm · optional'), <div className="wizard-grid">{field('Nome da propriedade', <input value={farm.name} onChange={e => setFarm({...farm,name:e.target.value})}/>)}{field('Cidade / UF', <input value={farm.city} onChange={e => setFarm({...farm,city:e.target.value})}/>)}</div>)}
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
     <div className="wizard-grid">{field('Colheita prevista (dia/mês)', <input placeholder="05/01" pattern="\d{2}/\d{2}" value={harvest} onChange={e => setHarvest(e.target.value)}/>)}{field('Data de referência', <input required type="date" value={date} onChange={e => setDate(e.target.value)}/>)}</div>
     {field('Semeadura da 2ª safra', <select value={sowing} onChange={e => setSowing(e.target.value)}><option value="">{say('Estimar a partir da colheita','Estimate from the harvest')}</option>{options.semeaduras.map(x => <option key={x}>{x}</option>)}</select>)}
     <p className="wizard-hint">{say('Se você não souber a fase nem a colheita, usaremos uma estimativa de calendário.','If you don’t know the stage or harvest date, we’ll use a calendar estimate.')}</p>
     </>)}
     
    </>}
    {step === 2 && <><fieldset className="wizard-choices"><legend>{say('Problemas conhecidos na área','Known issues on your land')}</legend>{[['nematoide','Nematoide'],['mofo_branco','Mofo-branco'],['cigarrinha','Cigarrinha'],['compactacao','Compactação']].map(([id,label]) => <label key={id}><input type="checkbox" checked={problems.includes(id)} onChange={() => setProblems(toggle(problems,id))}/>{t(label)}</label>)}</fieldset><p className="wizard-hint">{say('Nenhum conhecido? Pode continuar sem marcar nada.','No known issues? You can continue without selecting anything.')}</p></>}
    {step === 3 && <>
      
      <div className="wizard-grid wizard-soil-grid">{soilFields.map(([id,label]) => <div key={id}>{field(label, <input type="number" step="any" min={id === 'ph' ? 3 : 0} max={soilMax[id] ?? 100} value={soil[id] ?? ''} onChange={e => setSoil({...soil,[id]:e.target.value})}/>)}</div>)}</div><p className="wizard-hint">{say('Argila e areia: informe as duas, com soma de até 100%.','Clay and sand: enter both, totaling no more than 100%.')}</p>
      <div className="wizard-live-note" role="status">{Object.values(soil).filter(v => v !== '').length ? say(`${Object.values(soil).filter(v => v !== '').length} informações do seu solo adicionadas.`, `${Object.values(soil).filter(v => v !== '').length} soil values added.`) : say('Por enquanto, vamos usar dados públicos de solo quando disponíveis.','For now, we’ll use public soil data where available.')}</div>
    </>}
    {step === 4 && <>
      <div className="wizard-card-stack">{[
       ['balanced', say('Um pouco de equilíbrio','A little balance'), say('Olhar para renda, solo, água e riscos juntos.','Consider income, soil, water and risks together.'), {renda:5,solo:5,agua:5,pragas:5,risco:5}, '✦'],
       ['income', say('Mais retorno para a lavoura','More return from my crops'), say('Dar mais atenção ao resultado financeiro.','Give more attention to financial returns.'), {renda:9,solo:3,agua:3,pragas:3,risco:5}, '↗'],
       ['soil', say('Cuidar da terra para o futuro','Care for the land’s future'), say('Priorizar o solo e o uso da água.','Focus on soil health and water use.'), {renda:4,solo:9,agua:8,pragas:5,risco:5}, '❋'],
       ['risk', say('Mais tranquilidade no próximo ciclo','More peace of mind next season'), say('Dar mais peso aos riscos climáticos e pragas.','Give more weight to climate risks and pests.'), {renda:4,solo:4,agua:5,pragas:8,risco:9}, '◌'],
      ].map(([id,title,description,preset,icon]) => <div key={String(id)}>{choice(priority === id, String(title), String(description), () => {setPriority(String(id));setWeights(preset as Pesos);}, String(icon))}</div>)}</div>
      {more(say('Ajuste do seu jeito','Make it your own'), <div className="wizard-slider-grid">{options.criterios.map(({id,nome}) => <label className="wizard-slider" key={id}><span>{t(nome)}<output className="wizard-weight-value">{weights[id as keyof Pesos]}<span>/10</span></output></span><input type="range" min="0" max="10" value={weights[id as keyof Pesos]} onChange={e => {setPriority('custom');setWeights({...weights,[id]:Number(e.target.value)});}}/><span className="wizard-range-labels"><span>{say('Menor prioridade','Lower priority')}</span><span>{say('Maior prioridade','Higher priority')}</span></span></label>)}</div>)}
    </>}
    {step === 5 && <>
     <div className="wizard-ready"><span>{say('Seu ponto de partida','Your starting point')}</span><strong>{t(options.combinacoes.find(x => x.id === rotation)?.nome ?? rotation)}</strong><p>{priorityName} · {soilCount ? say(`${soilCount} dados de solo`, `${soilCount} soil values`) : say('Solo com dados públicos','Public soil data')}</p></div>
     
     {more(say('Seus preços · opcional','Your prices · optional'), <><p className="wizard-hint">{say('R$/saca. Em branco, usamos os preços de referência.','BRL per sack. Leave blank to use reference prices.')}</p><div className="wizard-grid">{commodities.map(([id,label]) => <div key={id}>{field(label,<input type="number" min="0" step="any" value={prices[id] ?? ''} onChange={e => setPrices({...prices,[id]:e.target.value})}/>)}</div>)}</div>
</>)}
     {more(say('Sem comprador para · opcional','No buyer for · optional'), <>     <fieldset className="wizard-choices"><legend>{say('Não tenho comprador para','I don’t have a buyer for')}</legend>{commodities.filter(([id]) => id !== 'soja').map(([id,label]) => <label key={id}><input type="checkbox" checked={buyers.includes(id)} onChange={() => setBuyers(toggle(buyers,id))}/>{t(label)}</label>)}</fieldset>
</>)}
     {more(say('Máquinas e irrigação · opcional','Equipment and irrigation · optional'), <>     <fieldset className="wizard-choices"><legend>{say('Equipamentos e água','Equipment and water')}</legend><label><input type="checkbox" checked={!header} onChange={e => setHeader(!e.target.checked)}/>{say('Não tenho plataforma de milho','I don’t have a corn header')}</label><label><input type="checkbox" checked={!seeder} onChange={e => setSeeder(!e.target.checked)}/>{say('Não tenho semeadora de consórcio','I don’t have an intercropping seeder')}</label><label><input type="checkbox" checked={irrigation} onChange={e => setIrrigation(e.target.checked)}/>{say('Tenho irrigação','I have irrigation')}</label></fieldset>
</>)}
     {more(say('Escolher quantos cenários ver','Choose how many scenarios to see'), <>     {field('Quantas alternativas mostrar', <input type="number" min="1" max="6" required value={count} onChange={e => setCount(Number(e.target.value))}/>)}
</>)}
    </>}
    </div>
    {error && <p className="wizard-error" role="alert">{error}</p>}
    <div className="wizard-actions">{step > 0 && <button type="button" className="wizard-back" onClick={() => {setError('');setStep(step-1);}}>{t('Voltar')}</button>}<button className="button yellow" type="submit">{step === 5 ? say('Explorar meus cenários →','Explore my scenarios →') : step === 2 && !problems.length ? say('Continuar sem marcar →','Continue without selecting →') : step === 3 && !Object.values(soil).some(v => v !== '') ? say('Vamos seguir sem análise →','Let’s continue without a soil test →') : say('Vamos continuar →','Let’s continue →')}</button></div>
    <small>{say('Seus dados ficam só nesta sessão.','Your data stays in this session only.')}</small>
   </form>
  </section>
 </div>;
}
