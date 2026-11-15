export const MAP_LAYERS = {
  satellite: { pt: "Satélite", en: "Satellite", id: "", nativeZoom: 19, legend: "" },
  precipitation: { pt: "Precipitação · média diária (mm/h)", en: "Precipitation · daily average (mm/h)", id: "IMERG_Precipitation_Rate", nativeZoom: 6, legend: "GPM_Precipitation_Rate_H.svg" },
  temperature: { pt: "Temperatura da superfície", en: "Land surface temperature", id: "MODIS_Terra_Land_Surface_Temp_Day", nativeZoom: 7, legend: "MODIS_Land_Surface_Temp_H.svg" },
  vegetation: { pt: "Vegetação · NDVI (8 dias)", en: "Vegetation · NDVI (8 days)", id: "MODIS_Terra_NDVI_8Day", nativeZoom: 9, legend: "MODIS_NDVI_H.svg" },
  moisture: { pt: "Umidade superficial do solo", en: "Surface soil moisture", id: "SMAP_L4_Analyzed_Surface_Soil_Moisture", nativeZoom: 6, legend: "SMAP_Analyzed_Soil_Moisture_H.svg" },
} as const;
export type MapLayer = keyof typeof MAP_LAYERS;
export type MapView = { layer: MapLayer; date: string; opacity: number };
export function mapDate(daysAgo: number): string {
  const date = new Date();
  date.setUTCDate(date.getUTCDate() - daysAgo);
  return date.toISOString().slice(0, 10);
}
export const initialMapView = (): MapView => ({ layer: "satellite", date: mapDate(7), opacity: 0.75 });

/** Use the same archive bounds for card clicks and the map's layer selector. */
export function layerStartDate(layer: MapLayer): string {
  return layer === "vegetation" ? "2025-02-12" : layer === "moisture" ? "2015-03-31" : "2000-06-01";
}
export function selectMapLayer(view: MapView, layer: MapLayer): MapView {
  const earliest = layerStartDate(layer);
  return { ...view, layer, date: view.date < earliest ? earliest : view.date };
}
export const INDICATOR_LAYERS: readonly MapLayer[] = ["temperature", "precipitation", "moisture", "vegetation"];
