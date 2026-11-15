import { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { useLanguage } from './i18n';

export type LatLon = [number, number];
/** Where to move the map; a new `key` re-applies the same place. */
export type MapFocus = { lat: number; lon: number; zoom: number; key: number };
type Props = {
 /** point: click/drag sets the pin; polygon: clicks add boundary corners; view: read-only pin. */
 mode: 'point' | 'polygon' | 'view';
 latitude: string; longitude: string;
 onChange?: (lat: string, lon: string) => void;
 vertices?: LatLon[];
 onVerticesChange?: (vertices: LatLon[]) => void;
 focus?: MapFocus | null;
 zoom?: number;
};

export default function LocationMap({ mode, latitude, longitude, onChange, vertices = [], onVerticesChange, focus, zoom = 12 }: Props) {
 const { language } = useLanguage();
 const en = language === 'en';
 const container = useRef<HTMLDivElement>(null);
 const map = useRef<L.Map | null>(null);
 const marker = useRef<L.Marker | null>(null);
 const shape = useRef<L.LayerGroup | null>(null);
 const handlers = useRef({ onChange, onVerticesChange, mode, vertices });
 handlers.current = { onChange, onVerticesChange, mode, vertices };
 const [tileError, setTileError] = useState(false);
 // Bumped each time the Leaflet map is (re)created, so the layer effects below redraw on the new map.
 const [generation, setGeneration] = useState(0);
 const valid = latitude.trim() !== '' && longitude.trim() !== '' && Number.isFinite(Number(latitude)) && Number.isFinite(Number(longitude)) && Math.abs(Number(latitude)) <= 90 && Math.abs(Number(longitude)) <= 180;
 const coordinates = useRef<L.LatLngTuple>([-24.81, -53.55]);
 if (valid) coordinates.current = [Number(latitude), Number(longitude)];

 useEffect(() => {
  if (!container.current) return;
  const instance = L.map(container.current, { scrollWheelZoom: true, zoomControl: false }).setView(coordinates.current, zoom);
  map.current = instance;
  L.control.zoom({ zoomInTitle: en ? 'Zoom in' : 'Aproximar', zoomOutTitle: en ? 'Zoom out' : 'Afastar' }).addTo(instance);
  const tiles = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' }).addTo(instance);
  tiles.on('tileerror', () => setTileError(true));
  tiles.on('load', () => { if (container.current?.querySelector('.leaflet-tile-loaded')) setTileError(false); });
  const pin = L.marker(coordinates.current, { draggable: handlers.current.mode === 'point', title: en ? 'Selected location' : 'Localização selecionada', icon: L.divIcon({ className: 'wizard-map-pin', html: '<span></span>', iconSize: [28, 36], iconAnchor: [14, 36] }) });
  marker.current = pin;
  shape.current = L.layerGroup().addTo(instance);
  const select = (position: L.LatLng) => handlers.current.onChange?.(Math.max(-90, Math.min(90, position.lat)).toFixed(6), position.wrap().lng.toFixed(6));
  instance.on('click', (e: L.LeafletMouseEvent) => {
   const { mode: current, vertices: corners, onVerticesChange: addCorner } = handlers.current;
   if (current === 'point') { pin.setLatLng(e.latlng); select(e.latlng); }
   if (current === 'polygon') addCorner?.([...corners, [Number(e.latlng.lat.toFixed(6)), Number(e.latlng.wrap().lng.toFixed(6))]]);
  });
  pin.on('dragend', () => select(pin.getLatLng()));
  setGeneration(g => g + 1);
  const observer = new ResizeObserver(() => instance.invalidateSize());
  observer.observe(container.current);
  return () => { observer.disconnect(); instance.remove(); map.current = null; marker.current = null; shape.current = null; };
 }, [en, zoom]);

 // Pin: visible outside the drawing mode, draggable only when marking a point.
 useEffect(() => {
  const instance = map.current, pin = marker.current;
  if (!instance || !pin) return;
  if (mode === 'polygon') { pin.remove(); return; }
  pin.addTo(instance);
  if (mode === 'point') pin.dragging?.enable(); else pin.dragging?.disable();
 }, [mode, generation]);

 useEffect(() => {
  if (!valid || !map.current || !marker.current) return;
  const point = L.latLng(Number(latitude), Number(longitude));
  marker.current.setLatLng(point);
  if (!map.current.getBounds().contains(point)) map.current.panTo(point, { animate: false });
 }, [latitude, longitude, valid, generation]);

 // Drawn boundary: corners as dots, closed as a polygon from 3 corners on.
 useEffect(() => {
  const group = shape.current;
  if (!group) return;
  group.clearLayers();
  if (mode !== 'polygon' || !vertices.length) return;
  const style = { color: '#ffbf22', weight: 2, fillColor: '#ffbf22', fillOpacity: 0.18 };
  if (vertices.length >= 3) L.polygon(vertices, style).addTo(group);
  else if (vertices.length === 2) L.polyline(vertices, style).addTo(group);
  vertices.forEach(v => L.circleMarker(v, { radius: 5, color: '#fff4cc', weight: 2, fillColor: '#ffbf22', fillOpacity: 1, interactive: false }).addTo(group));
 }, [vertices, mode, generation]);

 useEffect(() => {
  if (focus && map.current) map.current.setView([focus.lat, focus.lon], focus.zoom);
 }, [focus]);

 const instruction = mode === 'polygon'
  ? (en ? 'Click each corner of your field, in order. From 3 corners the boundary closes.' : 'Clique em cada canto da sua área, em ordem. Com 3 cantos ou mais o contorno se fecha.')
  : mode === 'point'
   ? (en ? 'Tap the map to mark your land. You can also drag the pin. Use the mouse wheel or the +/− buttons to zoom.' : 'Toque no mapa para marcar sua terra. Você também pode arrastar o pino. Use a rolagem do mouse ou os botões +/− para aproximar.')
   : '';
 return <div className="wizard-location-map">
  {instruction && <p className="wizard-map-instruction">{instruction}</p>}
  <div ref={container} className={'wizard-map-canvas' + (mode === 'view' ? ' is-view' : '')} role="region" aria-label={mode === 'view' ? (en ? 'Location of the sample field' : 'Localização do talhão de exemplo') : (en ? 'Select your farm location on the map' : 'Selecione a localização da sua propriedade no mapa')}/>
  {tileError && <p className="wizard-hint" role="status">{en ? 'The map could not fully load. You can still enter coordinates below.' : 'O mapa não carregou por completo. Você pode informar as coordenadas abaixo.'}</p>}
 </div>;
}
