import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import type { GeoJsonObject } from "geojson";
import "leaflet/dist/leaflet.css";
import type { Area } from "./api";
import type { Farm } from "./data";
import options from "./setup-options.json";
import { t, useLanguage } from "./i18n";
import { IMAGERY_URL, imageryCoversView } from "./imageryCoverage";
import { MAP_LAYERS, mapDate, layerStartDate, selectMapLayer } from "./mapLayers";
import type { MapLayer, MapView } from "./mapLayers";

type Props = { id?: string; farm: Farm; area?: Area; expanded?: boolean; view: MapView; onViewChange: (view: MapView) => void; onExpand: () => void };

export default function FarmMap({ id, farm, area, expanded = false, view, onViewChange, onExpand }: Props) {
  const { language } = useLanguage();
  const en = language === "en";
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const overlay = useRef<L.TileLayer | null>(null);
  const currentView = useRef(view);
  currentView.current = view;
  const homeZoom = () => currentView.current.layer === "satellite" ? 15 : MAP_LAYERS[currentView.current.layer].nativeZoom;
  const previousLayer = useRef<MapLayer>(view.layer);
  const home = useRef<() => void>(() => {});
  const [satelliteLimit, setSatelliteLimit] = useState(15);
  const [coveragePending, setCoveragePending] = useState(false);
  const [tileError, setTileError] = useState(false);
  const [overlayError, setOverlayError] = useState(false);
  const [loading, setLoading] = useState(false);
  const config = MAP_LAYERS[view.layer];
  const thematic = view.layer !== "satellite";
  const maxZoom = thematic ? config.nativeZoom : satelliteLimit;
  const [locationError, setLocationError] = useState(false);
  const [zoom, setZoom] = useState(13);

  useEffect(() => {
    if (!container.current) return;
    const instance = L.map(container.current, {
      zoomControl: false, scrollWheelZoom: false, minZoom: 3, maxZoom: 19,
      // Leaflet 1.9 can finish a CSS zoom transition after React unmounts the map.
      zoomAnimation: false, markerZoomAnimation: false,
    }).setView([-24.81, -53.55], 13);
    map.current = instance;
    const tiles = L.tileLayer(`${IMAGERY_URL}/tile/{z}/{y}/{x}?blankTile=false`, {
      maxZoom: 19, maxNativeZoom: 19,
      attribution: 'Imagery &copy; <a href="https://www.esri.com/">Esri</a>, Maxar, Earthstar Geographics, and the GIS User Community',
    }).addTo(instance);
    tiles.on("loading", () => setTileError(false));
    tiles.on("tileerror", () => setTileError(true));
    instance.on("zoomend", () => setZoom(instance.getZoom()));
    let active = true;
    const observer = new ResizeObserver(() => {
      if (active) instance.invalidateSize({ pan: false });
    });
    observer.observe(container.current);
    return () => {
      active = false;
      observer.disconnect();
      instance.stop();
      instance.remove();
      map.current = null;
      home.current = () => {};
    };
  }, []);

  useEffect(() => { map.current?.setMaxZoom(maxZoom); }, [maxZoom]);

  useEffect(() => {
    const instance = map.current;
    if (!instance) return;
    const features = L.featureGroup().addTo(instance);
    setLocationError(false);
    try {
      // A supplied polygon is the only source of a property boundary.
      if (area && "geometry" in area) {
        L.geoJSON(area.geometry as GeoJsonObject, {
          style: { color: "#62dca1", weight: 1.5, opacity: 0.7, fillOpacity: 0.035 },
        }).addTo(features);
        const bounds = features.getBounds();
        if (!bounds.isValid()) throw new Error("Invalid geometry");
        home.current = () => instance.fitBounds(bounds, { padding: [40, 40], maxZoom: homeZoom(), animate: false });
      } else {
        let lat = Number(farm.latitude), lon = Number(farm.longitude);
        let valid = farm.latitude.trim() !== "" && farm.longitude.trim() !== "";
        if (!valid && area && "lat" in area) {
          lat = area.lat; lon = area.lon; valid = true;
        }
        if (!valid && area && "talhao_id" in area) {
          const demo = options.talhoes_demo.find(item => item.id === area.talhao_id);
          if (demo) { lat = demo.lat; lon = demo.lon; valid = true; }
        }
        if (!valid || !Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) {
          throw new Error("Invalid coordinates");
        }
        const point = L.latLng(lat, lon);
        L.circleMarker(point, { radius: 9, color: "#edf1e6", weight: 2, fillColor: "#00a66c", fillOpacity: 1, className: "farm-property-marker" }).addTo(features);
        home.current = () => instance.setView(point, homeZoom(), { animate: false });
      }
      home.current();
    } catch {
      features.clearLayers();
      home.current = () => instance.setView([-24.81, -53.55], 10, { animate: false });
      home.current();
      setLocationError(true);
    }
    return () => { features.remove(); };
  }, [farm.latitude, farm.longitude, area]);

  useEffect(() => {
    const instance = map.current;
    if (!instance || view.layer !== "satellite") return;
    let active = true;
    let request: AbortController | undefined;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const checkCoverage = async () => {
      request?.abort();
      const controller = new AbortController();
      request = controller;
      setCoveragePending(true);
      // Hold zoom at the current level until higher-resolution coverage is known.
      setSatelliteLimit(Math.min(19, instance.getZoom()));
      try {
        for (let level = 19; level >= 3; level--) {
          const available = await imageryCoversView(instance, level, controller.signal);
          if (!active || controller.signal.aborted) return;
          if (available) {
            setSatelliteLimit(level);
            return;
          }
        }
        setTileError(true);
      } catch {
        if (active && !controller.signal.aborted) setTileError(true);
      } finally {
        if (active && !controller.signal.aborted) setCoveragePending(false);
      }
    };
    const scheduleCheck = () => {
      request?.abort();
      clearTimeout(timer);
      timer = setTimeout(() => void checkCoverage(), 120);
    };
    instance.on("moveend resize", scheduleCheck);
    void checkCoverage();
    return () => {
      active = false;
      request?.abort();
      clearTimeout(timer);
      instance.off("moveend resize", scheduleCheck);
    };
  }, [view.layer]);

  useEffect(() => {
    const instance = map.current;
    if (!instance) return;
    setOverlayError(false);
    setLoading(false);
    if (previousLayer.current !== view.layer) {
      instance.setZoom(thematic ? Math.min(instance.getZoom(), config.nativeZoom) : Math.min(15, instance.getMaxZoom()), { animate: false });
      previousLayer.current = view.layer;
    }
    if (!thematic) return;
    let active = true;
    const tiles = L.tileLayer(`https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/${config.id}/default/${view.date}/GoogleMapsCompatible_Level${config.nativeZoom}/{z}/{y}/{x}.png`, {
      maxNativeZoom: config.nativeZoom, maxZoom: config.nativeZoom, opacity: 0.75,
      attribution: '<a href="https://worldview.earthdata.nasa.gov/">NASA EOSDIS GIBS</a>',
    });
    overlay.current = tiles;
    tiles.on("loading", () => { if (active) setLoading(true); });
    tiles.on("load", () => { if (active) setLoading(false); });
    tiles.on("tileerror", () => { if (active) setOverlayError(true); });
    tiles.addTo(instance);
    return () => {
      active = false;
      // Removal fires Leaflet's internal cleanup; keep its listeners until then.
      tiles.remove();
      tiles.off();
      overlay.current = null;
    };
  }, [view.layer, view.date, config, thematic]);

  useEffect(() => { overlay.current?.setOpacity(view.opacity); }, [view.opacity, view.layer, view.date]);

  useEffect(() => {
    if (expanded) map.current?.scrollWheelZoom.enable();
    else map.current?.scrollWheelZoom.disable();
  }, [expanded]);

  return <div id={id} className={`farm-map live-farm-map${expanded ? " expanded" : ""}`}>
    <div ref={container} className="farm-map-canvas" role="region" aria-label={en ? "Property map" : "Mapa da propriedade"} />
    <div className="farm-map-layers">
      <label>
        <span>{en ? "Map layer" : "Camada do mapa"}</span>
        <select value={view.layer} onChange={event => onViewChange(selectMapLayer(view, event.target.value as MapLayer))}>
          {Object.entries(MAP_LAYERS).map(([id, layer]) => <option key={id} value={id}>{en ? layer.en : layer.pt}</option>)}
        </select>
      </label>
      {thematic && <>
        <label><span>{en ? "Observation date" : "Data da observação"}</span>
          <input type="date" value={view.date} min={layerStartDate(view.layer)} max={mapDate(1)} onChange={event => { if (event.target.validity.valid && event.target.value) onViewChange({ ...view, date: event.target.value }); }} />
        </label>
        <label><span>{en ? "Layer opacity" : "Opacidade da camada"} · {Math.round(view.opacity * 100)}%</span>
          <input type="range" min="0" max="1" step="0.05" value={view.opacity} onChange={event => onViewChange({ ...view, opacity: Number(event.target.value) })} />
        </label>
      </>}
    </div>
    {(tileError || locationError || overlayError) && <p className="farm-map-status" role="status">
      {locationError
        ? (en ? "Enter valid coordinates in Settings to locate your property." : "Informe coordenadas válidas em Configurações para localizar sua propriedade.")
        : overlayError ? (en ? "This layer could not load for the selected date. Try another date." : "A camada não carregou para esta data. Tente outra data.")
        : (en ? "Some map tiles could not load. Check your connection." : "Parte do mapa não carregou. Confira sua conexão.")}
    </p>}
    {thematic && <div className="farm-map-data" aria-live="polite">
      <strong>{en ? config.en : config.pt}</strong>
      <small>{view.date} · NASA GIBS</small>
      <img src={`https://gibs.earthdata.nasa.gov/legends/${config.legend}`} alt={en ? "Layer color scale" : "Escala de cores da camada"} />
      <small>{loading ? (en ? "Loading layer…" : "Carregando camada…") : (en ? "Regional observations; gaps may indicate no data. Not a forecast." : "Observações regionais; áreas sem cor podem indicar ausência de dados. Não é previsão.")}</small>
    </div>}
    <div className="map-controls">
      <button type="button" aria-label={t("Aproximar mapa")} disabled={zoom >= maxZoom || (!thematic && coveragePending)} onClick={() => map.current?.zoomIn()}><MapControlIcon kind="plus" /></button>
      <button type="button" aria-label={t("Afastar mapa")} disabled={zoom <= 3} onClick={() => map.current?.zoomOut()}><MapControlIcon kind="minus" /></button>
      <button type="button" aria-label={t("Centralizar propriedade")} onClick={() => home.current()}><MapControlIcon kind="center" /></button>
    </div>
    <div className="map-farm">
      <strong>{farm.name}</strong>
      <small>{farm.area} ha · {en ? "Registered location" : "Localização cadastrada"}</small>
    </div>
    <button type="button" className="map-fullscreen" aria-label={t(expanded ? "Fechar mapa ampliado" : "Ampliar mapa")} onClick={onExpand}><MapControlIcon kind={expanded ? "collapse" : "expand"} /></button>
  </div>;
}

function MapControlIcon({ kind }: { kind: "plus" | "minus" | "center" | "expand" | "collapse" }) {
  const paths = {
    plus: "M12 5v14M5 12h14",
    minus: "M5 12h14",
    center: "M12 3v4M12 17v4M3 12h4M17 12h4",
    expand: "M8 3H3v5M16 3h5v5M21 16v5h-5M8 21H3v-5",
    collapse: "M3 8h5V3M16 3v5h5M21 16h-5v5M8 21v-5H3",
  };
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {kind === "center" && <circle cx="12" cy="12" r="6" />}
    <path d={paths[kind]} />
  </svg>;
}
