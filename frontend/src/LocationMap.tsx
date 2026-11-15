import { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { useLanguage } from './i18n';

type Props = { latitude: string; longitude: string; onChange: (lat: string, lon: string) => void };
export default function LocationMap({ latitude, longitude, onChange }: Props) {
 const { language } = useLanguage();
 const en = language === 'en';
 const container = useRef<HTMLDivElement>(null);
 const map = useRef<L.Map | null>(null);
 const marker = useRef<L.Marker | null>(null);
 const update = useRef(onChange);
 const [tileError, setTileError] = useState(false);
 update.current = onChange;
 const valid = latitude.trim() !== '' && longitude.trim() !== '' && Number.isFinite(Number(latitude)) && Number.isFinite(Number(longitude)) && Math.abs(Number(latitude)) <= 90 && Math.abs(Number(longitude)) <= 180;
 const coordinates = useRef<L.LatLngTuple>([-24.81, -53.55]);
 if (valid) coordinates.current = [Number(latitude), Number(longitude)];
 useEffect(() => {
  if (!container.current) return;
  const instance = L.map(container.current, {scrollWheelZoom: false, zoomControl: false}).setView(coordinates.current, 12);
  map.current = instance;
  L.control.zoom({zoomInTitle: en ? 'Zoom in' : 'Aproximar', zoomOutTitle: en ? 'Zoom out' : 'Afastar'}).addTo(instance);
  const tiles = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'}).addTo(instance);
  tiles.on('tileerror', () => setTileError(true));
  tiles.on('load', () => { if (container.current?.querySelector('.leaflet-tile-loaded')) setTileError(false); });
  const pin = L.marker(coordinates.current, {draggable: true, title: en ? 'Selected location' : 'Localização selecionada', icon: L.divIcon({className:'wizard-map-pin', html:'<span></span>',iconSize:[28,36],iconAnchor:[14,36]})}).addTo(instance);
  marker.current = pin;
  const select = (position: L.LatLng) => update.current(Math.max(-90, Math.min(90,position.lat)).toFixed(6), position.wrap().lng.toFixed(6));
  instance.on('click', (e: L.LeafletMouseEvent) => {pin.setLatLng(e.latlng); select(e.latlng);});
  pin.on('dragend', () => select(pin.getLatLng()));
  const observer = new ResizeObserver(() => instance.invalidateSize());
  observer.observe(container.current);
  return () => {observer.disconnect();instance.remove();map.current=null;marker.current=null;};
 }, [en]);
 useEffect(() => {
  if (!valid || !map.current || !marker.current) return;
  const point = L.latLng(Number(latitude),Number(longitude));
  marker.current.setLatLng(point);
  if (!map.current.getBounds().contains(point)) map.current.panTo(point, {animate:false});
 }, [latitude,longitude,valid]);
 return <div className="wizard-location-map">
  <p className="wizard-map-instruction">{en ? 'Tap the map to mark your land. You can also drag the pin.' : 'Toque no mapa para marcar sua terra. Você também pode arrastar o pino.'}</p>
  <div ref={container} className="wizard-map-canvas" role="region" aria-label={en ? 'Select your farm location on the map' : 'Selecione a localização da sua propriedade no mapa'}/>
  {tileError && <p className="wizard-hint" role="status">{en ? 'The map could not fully load. You can still enter coordinates below.' : 'O mapa não carregou por completo. Você pode informar as coordenadas abaixo.'}</p>}
 </div>;
}
