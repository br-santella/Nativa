import { useEffect, useRef, useState } from 'react';
import { useReducedMotion } from 'motion/react';
function interpolate(p: number, xs: number[], ys: number[]) {
  if (p <= xs[0]) return ys[0];
  for(let i=1;i<xs.length;i++) if(p <= xs[i]) return ys[i-1]+(ys[i]-ys[i-1])*(p-xs[i-1])/(xs[i]-xs[i-1]);
  return ys[ys.length-1];
}
import './climate-story.css';

const quotes = [
  'A chuva chegou quando a gente menos esperava.',
  'O período de plantio já não é tão previsível.',
  'Cada safra parece trazer um desafio diferente.',
];
const windows = [[0, .04, .15, .23], [.19, .27, .47, .54], [.49, .56, .74, .82], [.77, .85, 1, 1]];
function Scene({ progress, index, children }: { progress: number; index: number; children: React.ReactNode }) {
  const opacity = interpolate(progress, windows[index], [index === 0 ? 1 : 0, 1, 1, index === 3 ? 1 : 0]);
  const y = interpolate(progress, windows[index], [24, 0, 0, -20]);
  return <div className={`climate-scene climate-scene-${index}`} style={{ opacity, transform: `translateY(${y}px)` }} aria-hidden="true">{children}</div>;
}
function Photo({ progress, src, range, initial = false }: { progress: number; src: string; range: number[]; initial?: boolean }) {
  const opacity = interpolate(progress, range, [initial ? 1 : 0, 1, 1, 0]);
  const y = interpolate(progress, [0, 1], [2, -4]);
  const [failed, setFailed] = useState(false);
  return <div className="climate-photo" style={{ opacity, transform: `translateY(${y}%)` }}>
    {failed ? <span className="climate-image-placeholder">Imagem de referência indisponível · paisagem agrícola</span> : <img src={src} alt="" loading="lazy" decoding="async" onError={() => setFailed(true)} />}
  </div>;
}
function Quote({ progress, index }: { progress: number; index: number }) {
  const starts = [.50, .59, .68]; const start = starts[index];
  const opacity = interpolate(progress, [start, start + .025, start + .07, start + .095], [0, 1, 1, 0]);
  const y = interpolate(progress, [start, start + .025, start + .095], [25, 0, -12]);
  return <blockquote className={`climate-quote climate-quote-${index}`} style={{ opacity, transform: `translateY(${y}px)` }} aria-hidden="true"><span className="climate-quote-mark">“</span><p>{quotes[index]}</p><small>Relato ilustrativo</small></blockquote>;
}
export default function ClimateStory({ calmImage }: { calmImage: string }) {
  const ref = useRef<HTMLElement>(null);
  const reduced = useReducedMotion();
  const [p, setProgress] = useState(0);
  useEffect(() => {
    if(reduced) return;
    let frame = 0;
    const update = () => {
      frame = 0;
      const el = ref.current;
      if(el) { const rect = el.getBoundingClientRect(); setProgress(Math.max(0, Math.min(1, -rect.top / Math.max(1, rect.height - innerHeight)))); }
    };
    const schedule = () => { if(!frame) frame = requestAnimationFrame(update); };
    update(); addEventListener('scroll', schedule, {passive:true}); addEventListener('resize', schedule);
    return () => { cancelAnimationFrame(frame); removeEventListener('scroll', schedule); removeEventListener('resize', schedule); };
  }, [reduced]);
  const darkness = interpolate(p, [0, .2, .5, .75, .88], [.12, .38, .45, .6, 1]);
  const rain = interpolate(p, [.27, .30], [0, 1]);
  const dry = interpolate(p, [.34, .37], [0, 1]);
  const heat = interpolate(p, [.41, .44], [0, 1]);
  return <section ref={ref} id="produto" className={`climate-story${reduced ? ' climate-story-reduced' : ''}`} aria-labelledby="climate-story-title">
    <div className="climate-accessible">
      <h2 id="climate-story-title">Por gerações, aprendemos a cultivar seguindo os ciclos da natureza.</h2>
      <p>Mas o clima já não segue o mesmo calendário.</p><p>Chuvas imprevisíveis. Secas prolongadas. Temperaturas extremas.</p>
      {quotes.map(q => <blockquote key={q}>{q}<small>Relato ilustrativo</small></blockquote>)}
      <p>Como planejar a próxima safra quando o clima se torna imprevisível?</p>
    </div>
    {reduced ? <div className="climate-static">
      <article style={{ backgroundImage: `linear-gradient(#010e1155,#010e11cc),url(${calmImage})` }}><small>01 / O PROBLEMA</small><h3>Por gerações, aprendemos a cultivar seguindo os ciclos da natureza.</h3></article>
      <article style={{ backgroundImage: 'linear-gradient(#010e1166,#010e11dd),url(/assets/story-flood.webp)' }}><h3>Mas o clima já não segue o mesmo calendário.</h3><p>Chuvas imprevisíveis.<br/>Secas prolongadas.<br/>Temperaturas extremas.</p></article>
      <article className="climate-static-quotes"><small>VOZES DO CAMPO · RELATOS ILUSTRATIVOS</small>{quotes.map(q=><blockquote key={q}>“{q}”</blockquote>)}</article>
      <article><h3>Como planejar a <em>próxima safra</em> quando o clima se torna imprevisível?</h3></article>
    </div> : <div className="climate-sticky">
      <div className="climate-images" aria-hidden="true">
        <Photo progress={p} src={calmImage} range={[0,.05,.16,.28]} initial />
        <Photo progress={p} src="/assets/story-flood.webp" range={[.17,.25,.30,.38]} />
        <Photo progress={p} src="/assets/story-submerged.webp" range={[.30,.38,.42,.51]} />
        <Photo progress={p} src="/assets/story-drought.webp" range={[.43,.51,.56,.65]} />
        <Photo progress={p} src="/assets/story-heat.webp" range={[.57,.65,.76,.87]} />
      </div>
      <div className="climate-darkness" style={{opacity:darkness}} />
      <div className="climate-vignette" />
      <div className="climate-chapter" aria-hidden="true"><span>01</span> O PROBLEMA</div>
      <Scene progress={p} index={0}><h2>Por gerações, aprendemos a cultivar seguindo os ciclos da natureza.</h2><span className="climate-scroll-cue">Uma história que está mudando <i>↓</i></span></Scene>
      <Scene progress={p} index={1}><h2>Mas o clima já não segue o mesmo calendário.</h2><div className="climate-weather"><p style={{opacity:rain}}>Chuvas imprevisíveis.</p><p style={{opacity:dry}}>Secas prolongadas.</p><p style={{opacity:heat}}>Temperaturas extremas.</p></div></Scene>
      <Scene progress={p} index={2}><div className="climate-human"><small>POR TRÁS DE CADA SAFRA, UMA VIDA.</small><h2>A incerteza também<br/>chega ao campo.</h2></div></Scene>
      {quotes.map((q,i)=><Quote key={q} progress={p} index={i}/>)}
      <Scene progress={p} index={3}><h2>Como planejar a <em>próxima safra</em> quando o clima se torna imprevisível?</h2></Scene>
      <span className="climate-photo-note" aria-hidden="true">Fotografias de referência · cenas sem associação aos relatos</span>
    </div>}
  </section>;
}
