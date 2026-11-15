import type L from "leaflet";

export const IMAGERY_URL = "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer";

/** Check the actual viewport, not just the service's advertised maximum zoom. */
export async function imageryCoversView(map: L.Map, zoom: number, signal: AbortSignal): Promise<boolean> {
  const center = map.project(map.getCenter(), zoom);
  const half = map.getSize().divideBy(2);
  const count = 2 ** zoom;
  const left = Math.floor((center.x - half.x) / 256);
  const right = Math.floor((center.x + half.x) / 256);
  const top = Math.max(0, Math.floor((center.y - half.y) / 256));
  const bottom = Math.min(count - 1, Math.floor((center.y + half.y) / 256));
  // Split at the date line so wrapped maps still query valid tile columns.
  const columns = Array.from({ length: right - left + 1 }, (_, i) => ((left + i) % count + count) % count);
  const groups: number[][] = [];
  for (const column of columns) {
    const group = groups.at(-1);
    if (group && column === group[group.length - 1] + 1) group.push(column);
    else groups.push([column]);
  }
  for (const group of groups) {
    const width = group.length, height = bottom - top + 1;
    const response = await fetch(`${IMAGERY_URL}/tilemap/${zoom}/${top}/${group[0]}/${width}/${height}?f=json`, { signal });
    if (!response.ok) throw new Error("Imagery coverage lookup failed");
    const result = await response.json();
    if (result.error || !Array.isArray(result.data)) throw new Error("Invalid imagery coverage response");
    if (result.data.length !== width * height || result.data.some((value: number) => value !== 1)) return false;
  }
  return true;
}
