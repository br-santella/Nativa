export const months = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];
export const initialFarm = {
  name: "Boa Vista Farm",
  city: "Sorriso, MT",
  country: "Brazil",
  latitude: "-12.55",
  longitude: "-55.72",
  area: "120",
  texture: "Clayey",
  ph: "5.8",
  drainage: "Moderate",
  organic: "3.2",
  irrigation: "Yes",
  irrigationType: "Center pivot",
  waterRestriction: "Withdrawal limit in the dry season",
  crop: "Soybean",
};
export type Farm = typeof initialFarm;
export const initialCrops = [
  {
    id: 1,
    crop: "Soybean",
    season: "2025/26",
    plant: "2025-10-15",
    harvest: "2026-02-20",
    area: "120",
    yield: "",
    status: "Growing",
  },
  {
    id: 2,
    crop: "Corn",
    season: "2025",
    plant: "2025-03-05",
    harvest: "2025-07-28",
    area: "120",
    yield: "98",
    status: "Completed",
  },
  {
    id: 3,
    crop: "Soybean",
    season: "2024/25",
    plant: "2024-10-12",
    harvest: "2025-02-22",
    area: "120",
    yield: "58",
    status: "Completed",
  },
  {
    id: 4,
    crop: "Corn",
    season: "2024",
    plant: "2024-03-10",
    harvest: "2024-07-30",
    area: "120",
    yield: "92",
    status: "Completed",
  },
];
export type Crop = (typeof initialCrops)[number];
export const series = {
  temperature: [25, 26.2, 25, 23.8, 21.5, 20.5, 21.5, 23.8, 27, 28.2, 26, 25],
  rain: [220, 190, 170, 110, 60, 25, 15, 25, 75, 140, 190, 230],
  moisture: [38, 40, 39, 34, 29, 25, 24, 25, 29, 34, 38, 40],
  ndvi: [0.7, 0.76, 0.68, 0.5, 0.62, 0.7, 0.6, 0.4, 0.32, 0.5, 0.62, 0.74],
};
export const scenarios = [
  {
    name: "Current rotation",
    sequence: "Soybean → Corn → Fallow",
    calendar: "Soybean / Corn / Fallow",
    water: "Higher demand",
    soil: "Limited cover",
    climate: "Exposed in drought",
    benefit: "Uses the infrastructure and experience already available.",
    risk: "Bare soil between seasons.",
    detail:
      "Fallow can leave the soil uncovered, increasing exposure to erosion and water loss through evaporation. The intensity depends on local conditions.",
    notes: [48, 52, 82, 62],
    color: "#93a8ad",
  },
  {
    name: "Soil conservation",
    sequence: "Soybean → Corn + brachiaria",
    calendar: "Soybean / Corn + Brachiaria / Cover",
    water: "Less evaporation loss",
    soil: "More cover and straw",
    climate: "Protection in the dry season",
    benefit: "Keeps cover and diversifies the root system.",
    risk: "Requires cover management and sowing adjustments.",
    detail:
      "Brachiaria straw and roots can protect the surface, favor infiltration and add organic matter over time. The result depends on establishment and management.",
    notes: [84, 92, 74, 82],
    color: "#a8c9a3",
  },
  {
    name: "Climate adaptation",
    sequence: "Sorghum → Crotalaria → Soybean",
    calendar: "Sorghum / Crotalaria / Soybean",
    water: "Lower potential demand",
    soil: "Root diversification",
    climate: "Higher drought tolerance",
    benefit: "Diversifies crops and exposure to climate risk.",
    risk: "Depends on market, seeds and planting window.",
    detail:
      "Sorghum has relative tolerance to water deficit. Crotalaria can contribute to nutrient cycling, with a response that depends on the species, the soil and management.",
    notes: [88, 78, 65, 90],
    color: "#e9b857",
  },
];
export const profiles = {
  soil: [80, 90, 60, 75],
  water: [100, 20, 20, 100],
  profit: [0, 0, 100, 0],
};
export function score(notes: number[], weights: number[]) {
  const total = weights.reduce((a, b) => a + b, 0);
  return total
    ? Math.round(notes.reduce((s, n, i) => s + n * weights[i], 0) / total)
    : 0;
}
export const info = {
  sources: {
    title: "Sources, scale and uncertainty",
    subtitle:
      "NASA product references. Every value in this experience is fictitious.",
    items: [
      [
        "NASA POWER",
        "Gridded meteorology: temperature and precipitation. The regional scale does not replace a local station.",
      ],
      [
        "NASA SMAP",
        "Moisture in the topsoil layer. The conversion to a percentage is illustrative and does not describe the whole root zone.",
      ],
      [
        "NASA MODIS / NDVI",
        "Spectral index related to vegetation vigor. Clouds, resolution and time of year affect the reading.",
      ],
      [
        "No agronomic validation",
        "Illustrative scenarios: confirm suitability with local technical assistance.",
      ],
    ],
  },
  indicators: {
    title: "What do the indicators mean?",
    subtitle: "A simple reading to support exploration.",
    items: [
      [
        "NDVI",
        "Index from −1 to 1 related to vegetation vigor. It is not equivalent to yield.",
      ],
      [
        "Soil moisture",
        "Water in the surface layer. Moisture in the root zone may differ.",
      ],
      [
        "Soil pH",
        "Indicates acidity or alkalinity. The interpretation depends on the crop and the laboratory analysis.",
      ],
    ],
  },
  help: {
    title: "From orbit to your land",
    subtitle: "A quick guide to exploring NATIVA.",
    items: [
      [
        "1. Get to know the property",
        "Explore the indicators and the illustrative map.",
      ],
      [
        "2. Record your context",
        "See the soil, water and crop history fields.",
      ],
      [
        "3. Compare possibilities",
        "Explore the soil, water/climate and profitability profiles or adjust your priorities.",
      ],
    ],
  },
  technology: {
    title: "Space technology. Purpose in the field.",
    subtitle: "From observing space to the possibilities of your next season.",
    items: [
      [
        "Data in perspective",
        "NASA POWER, SMAP and MODIS references put climate, surface moisture and vegetation indicators in context.",
      ],
      [
        "From observation to decision",
        "Locate your property, explore environmental conditions and compare rotation strategies.",
      ],
      [
        "About this demo",
        "The scenarios and indicators are illustrative. No NASA product is connected in this version.",
      ],
    ],
  },
};
