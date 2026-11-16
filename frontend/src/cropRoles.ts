// What each second crop does for the soil, shown as badges in the scenario window.
// Mirrors the engine catalog (`SECOND` in motor_field_shift/src/field_shift/app/engine.py); update both together.
// `scored` roles come from attributes the engine scores: n_fix >= 0.7 (nitrogen), cobertura >= 0.8 (cover) and the sorghum
// drought flag (no water deficit in its climate risk). The others are general agronomy and do not change the score.
export type SoilRole = "nitrogen" | "cover" | "roots" | "drought";
type Text = { pt: string; en: string };

export const SOIL_ROLES: Record<SoilRole, { label: Text; hint: Text }> = {
  nitrogen: { label: { pt: "Fixa nitrogênio", en: "Fixes nitrogen" },
    hint: { pt: "Leguminosa: capta nitrogênio do ar e deixa parte no solo para a cultura seguinte.", en: "Legume: takes nitrogen from the air and leaves part in the soil for the next crop." } },
  cover: { label: { pt: "Cobre o solo", en: "Covers the soil" },
    hint: { pt: "Muita palha: reduz erosão e evaporação e aumenta a matéria orgânica.", en: "Plenty of straw: reduces erosion and evaporation and adds organic matter." } },
  roots: { label: { pt: "Raízes profundas", en: "Deep roots" },
    hint: { pt: "Abre canais em camadas compactadas e melhora a infiltração da água.", en: "Opens channels through compacted layers and improves water infiltration." } },
  drought: { label: { pt: "Tolera seca", en: "Drought tolerant" },
    hint: { pt: "Produz com menos água que o milho; menos risco em anos de veranico.", en: "Yields with less water than corn; lower risk in dry-spell years." } },
};

/** Roles of each second crop (engine ids). */
export const CROP_ROLES: Record<string, { role: SoilRole; scored: boolean }[]> = {
  milho_braquiaria: [{ role: "cover", scored: true }, { role: "roots", scored: false }],
  milheto_crotalaria: [{ role: "nitrogen", scored: true }, { role: "cover", scored: true }, { role: "drought", scored: false }],
  aveia: [{ role: "cover", scored: true }],
  aveia_nabo: [{ role: "cover", scored: true }, { role: "roots", scored: false }],
  nabo_forrageiro: [{ role: "roots", scored: false }],
  sorgo: [{ role: "drought", scored: true }],
};

/** Bare-soil days per year, read from the engine's evidence line ("~35 dias" / "~35 days"). */
export function bareSoilDays(evidence: string[] | undefined): number | null {
  for (const line of evidence ?? []) {
    const match = /(?:solo descoberto|bare soil)[^~]*~\s*(\d+)/i.exec(line);
    if (match) return Number(match[1]);
  }
  return null;
}
