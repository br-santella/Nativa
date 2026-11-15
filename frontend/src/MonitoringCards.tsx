import { useEffect, useState } from "react";
import L from "leaflet";
import type { GeoJsonObject } from "geojson";
import { getMonitoring, type Area, type Monitoring } from "./api";
import type { Farm } from "./data";
import options from "./setup-options.json";
import { locale, t, useLanguage } from "./i18n";
import { INDICATOR_LAYERS, MAP_LAYERS, selectMapLayer, type MapView } from "./mapLayers";
function point(farm: Farm, area?: Area): [number, number] | null {
  if (area && "geometry" in area) {
    try { const b = L.geoJSON(area.geometry as GeoJsonObject).getBounds(); return b.isValid() ? [b.getCenter().lat, b.getCenter().lng] : null; } catch { return null; }
  }
  if (farm.latitude.trim() && farm.longitude.trim()) return [Number(farm.latitude), Number(farm.longitude)];
  if (area && "lat" in area) return [area.lat, area.lon];
  if (area && "talhao_id" in area) { const d = options.talhoes_demo.find(d => d.id === area.talhao_id); if (d) return [d.lat, d.lon]; }
  return null;
}
export default function MonitoringCards({ farm, area, fahrenheit, view, onChange }: { farm: Farm; area?: Area; fahrenheit: boolean; view: MapView; onChange: (view: MapView) => void }) {
  const { language } = useLanguage(); const en = language === "en";
  const coords = point(farm, area), lat = coords?.[0], lon = coords?.[1], key = `${lat},${lon}`;
  const [state, setState] = useState<{ key: string; data?: Monitoring; loading: boolean }>({ key: "", loading: true });
  useEffect(() => {
    const abort = new AbortController();
    if (lat === undefined || lon === undefined || !Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat)>90 || Math.abs(lon)>180) { setState({ key, loading: false }); return; }
    setState({ key, loading: true });
    const timeout = window.setTimeout(() => { abort.abort(); setState({ key, loading: false }); }, 50000);
    getMonitoring(lat, lon, abort.signal).then(data => { window.clearTimeout(timeout); if (!abort.signal.aborted) setState({ key, data, loading: false }); }).catch(() => { window.clearTimeout(timeout); if (!abort.signal.aborted) setState({ key, loading: false }); });
    return () => { window.clearTimeout(timeout); abort.abort(); };
  }, [lat, lon, key]);
  const current = state.key === key ? state : { loading: true, data: undefined };
  const number = (v: number, digits=1) => v.toLocaleString(locale(), { maximumFractionDigits: digits });
  const date = (v: string) => new Date(v+"T12:00:00").toLocaleDateString(locale(), { day: "2-digit", month: "short", year: "numeric" });
  return <div className="metrics" aria-busy={current.loading}>{["temperature", "precipitation", "moisture", "vegetation"].map((id, i) => {
    const item = current.data?.indicators[id], value = item?.value ?? null;
    const shown = value !== null && i===0 && fahrenheit ? value*9/5+32 : value;
    const unit = i===0 && fahrenheit ? "°F" : ["°C", "mm", "%", "NDVI"][i];
    const delta = item?.delta == null ? null : item.delta*(i===0 && fahrenheit ? 9/5 : 1);
    const series = item?.series ?? [], values = series.flatMap(p => p.value === null ? [] : [p.value]);
    const low = Math.min(...values), range = Math.max(...values)-low || 1;
    const paths: string[] = []; let segment: string[] = [];
    for (let n=0; n<=series.length; n++) { const v = series[n]?.value; if (v == null) { if(segment.length) paths.push(segment.join(" ")); segment=[]; } else segment.push(`${4+n*80/Math.max(1,series.length-1)},${38-(v-low)*30/range}`); }
    const comparison = i<2 ? (en ? "vs previous 30 days" : "vs 30 dias anteriores") : i===2 ? (en ? "vs previous week" : "vs semana anterior") : (en ? "vs previous composite" : "vs composição anterior");
    const detail = i<2 ? (en ? "30-day gridded estimate." : "Estimativa em grade de 30 dias.") : i===2 ? (en ? "Daily volumetric soil water at 0–7 cm. ERA5-Land reanalysis." : "Água volumétrica diária no solo a 0–7 cm. Reanálise ERA5-Land.") : (en ? "16-day MOD13Q1 composite, ~250 m pixel; cloud/snow excluded." : "Composição MOD13Q1 de 16 dias, pixel de ~250 m; nuvem/neve excluídas.");
    return <button key={id} type="button" className={"metric panel"+(view.layer===INDICATOR_LAYERS[i] ? " is-selected" : "")} aria-pressed={view.layer===INDICATOR_LAYERS[i]} aria-controls="property-map" title={`${detail} ${en ? "Point estimate, not farm average. Map:" : "Estimativa pontual, não média da fazenda. Mapa:"} ${en ? MAP_LAYERS[INDICATOR_LAYERS[i]].en : MAP_LAYERS[INDICATOR_LAYERS[i]].pt}`} onClick={() => onChange(selectMapLayer(view, INDICATOR_LAYERS[i]))}>
      <span className="metric-title">{t(["Temperatura média", "Precipitação acumulada", "Umidade do solo", "Índice de vegetação"][i])}</span>
      <div className="metric-value"><strong>{shown===null ? "—" : number(shown,i===3?2:1)}</strong><small>{unit}</small></div>
      <span className={"delta "+(i<2?"warm":"")}>{current.loading ? (en?"Loading observations…":"Carregando observações…") : value===null ? (en?"Data unavailable":"Dados indisponíveis") : delta===null ? (en?"Comparison unavailable":"Comparação indisponível") : `${delta>0?"↗ +":delta<0?"↘ ":""}${number(delta,i===3?2:1)} ${i===0?unit:i===1?"%":i===2?"p.p.":""} ${comparison}`}</span>
      <small className="metric-source">{item?.source ?? ["NASA POWER","NASA POWER","Open-Meteo · ERA5-Land","NASA MODIS · ORNL DAAC"][i]}{item?.end && <><br/>{i<2 && item.start ? `${date(item.start)} – `:""}{date(item.end)}{i===3 ? (en?" · 16 days":" · 16 dias"):""}</>}</small>
      {value!==null && (i===2 ? <div className="metric-ring" aria-hidden="true"><svg viewBox="0 0 64 64" fill="none"><circle cx="32" cy="32" r="26" strokeWidth="6"/><circle cx="32" cy="32" r="26" strokeWidth="6" pathLength="100" strokeDasharray={`${Math.max(0,Math.min(100,value))} 100`} transform="rotate(-90 32 32)"/></svg></div> : <svg className="metric-spark" viewBox="0 0 88 44" aria-hidden="true">{paths.map((p,n)=><polyline key={n} points={p} fill="none" stroke={i===0?"#ffbf22":"#9ad3a4"} strokeWidth="1.8"/>)}</svg>)}
    </button>;
  })}</div>;
}
