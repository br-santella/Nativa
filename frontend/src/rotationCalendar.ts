// Approximate 12-month calendar of a rotation, for display only (the engine does not use it).
// Anchored on the engine's dates: the summer crop ends at the estimated harvest and the second crop
// starts at the second-window sowing date. Cycle lengths fill in the rest.

/** Summer crop cycle (days): middle of the range in catalog/crops.yaml (soja 100–145, milho 100–150). */
const SUMMER_CYCLE_DAYS: Record<string, number> = { soja: 120, milho_verao: 135 };

/**
 * Second crop cycle (days) until harvest or cover termination.
 * "catalog": middle of the range in catalog/crops.yaml (milho 100–150 for the off-season corn,
 * trigo and aveia_branca 120–150). "typical": not in the catalog; usual reference value, to be confirmed.
 */
const SECOND_CYCLE_DAYS: Record<string, { days: number; source: "catalog" | "typical" }> = {
  milho_safrinha: { days: 125, source: "catalog" },
  milho_braquiaria: { days: 125, source: "catalog" },
  soja_safrinha: { days: 120, source: "catalog" },
  trigo: { days: 135, source: "catalog" },
  aveia: { days: 135, source: "catalog" },
  aveia_nabo: { days: 135, source: "catalog" },
  nabo_forrageiro: { days: 90, source: "typical" },
  feijao_safrinha: { days: 90, source: "typical" },
  milheto_crotalaria: { days: 100, source: "typical" },
  sorgo: { days: 120, source: "typical" },
};

export type MonthUse = "summer" | "second" | "bare";

const YEAR = 365;
/** Day of a non-leap year (0–364) for a dd/mm date. */
function dayOfYear(ddmm: string): number | null {
  const [day, month] = ddmm.split("/").map(Number);
  if (!day || !month) return null;
  return Math.round((Date.UTC(2025, month - 1, day) - Date.UTC(2025, 0, 1)) / 86400000);
}
const within = (day: number, start: number, length: number) => ((day - start + YEAR) % YEAR) < length;

/** Use of each month (Jan–Dec), sampled mid-month, or null when a date or cycle is missing. */
export function rotationCalendar(summerId: string, secondId: string, summerHarvest: string, secondSowing: string): MonthUse[] | null {
  const harvest = dayOfYear(summerHarvest), sowing = dayOfYear(secondSowing);
  const summerDays = SUMMER_CYCLE_DAYS[summerId];
  if (harvest == null || sowing == null || !summerDays) return null;
  const summerStart = (harvest - summerDays + YEAR) % YEAR;
  const second = secondId === "pousio" ? null : SECOND_CYCLE_DAYS[secondId];
  if (secondId !== "pousio" && !second) return null;
  return Array.from({ length: 12 }, (_, m) => {
    const mid = dayOfYear(`15/${m + 1}`)!;
    if (within(mid, summerStart, summerDays)) return "summer";
    if (second && within(mid, sowing, second.days)) return "second";
    return "bare";
  });
}
