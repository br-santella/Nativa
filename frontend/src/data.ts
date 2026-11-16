export const months = [
  "Jan",
  "Fev",
  "Mar",
  "Abr",
  "Mai",
  "Jun",
  "Jul",
  "Ago",
  "Set",
  "Out",
  "Nov",
  "Dez",
];
export const initialFarm = {
  name: "Fazenda Boa Vista",
  city: "Toledo, PR",
  country: "Brasil",
  latitude: "-24.81473",
  longitude: "-53.55361",
  area: "103.87",
  texture: "Argiloso",
  ph: "5.8",
  drainage: "Moderada",
  organic: "3.2",
  irrigation: "Sim",
  irrigationType: "Pivô central",
  waterRestriction: "Limite de captação no período seco",
  crop: "Soja",
  address: "",
};
export type Farm = typeof initialFarm;
export const initialCrops = [
  {
    id: 1,
    crop: "Soja",
    season: "2026/27",
    plant: "2026-09-25",
    harvest: "2027-01-10",
    area: "103.87",
    yield: "",
    status: "Em crescimento",
  },
  {
    id: 2,
    crop: "Milho",
    season: "2026",
    plant: "2026-02-01",
    harvest: "2026-06-25",
    area: "103.87",
    yield: "98",
    status: "Concluído",
  },
  {
    id: 3,
    crop: "Soja",
    season: "2025/26",
    plant: "2025-09-28",
    harvest: "2026-01-15",
    area: "103.87",
    yield: "58",
    status: "Concluído",
  },
  {
    id: 4,
    crop: "Milho",
    season: "2025",
    plant: "2025-02-03",
    harvest: "2025-06-28",
    area: "103.87",
    yield: "92",
    status: "Concluído",
  },
];
export type Crop = (typeof initialCrops)[number];
export const series = {
  temperature: [25, 26.2, 25, 23.8, 21.5, 20.5, 21.5, 23.8, 27, 28.2, 26, 25],
  rain: [220, 190, 170, 110, 60, 25, 15, 25, 75, 140, 190, 230],
  moisture: [38, 40, 39, 34, 29, 25, 24, 25, 29, 34, 38, 40],
  ndvi: [0.7, 0.76, 0.68, 0.5, 0.62, 0.7, 0.6, 0.4, 0.32, 0.5, 0.62, 0.74],
};
export const info = {
  sources: {
    title: "Fontes, escala e incerteza",
    subtitle:
      "Como cada fonte entra na NATIVA. Indicadores e cenários usam dados reais do ponto cadastrado; no Histórico, temperatura e chuva vêm da NASA POWER e umidade e NDVI são ilustrativos.",
    items: [
      [
        "NASA POWER",
        "Meteorologia em grade: temperatura e precipitação. A escala regional não substitui uma estação local.",
      ],
      [
        "NASA SMAP",
        "Umidade na camada superficial do solo. A conversão para percentual é ilustrativa e não descreve toda a zona de raízes.",
      ],
      [
        "NASA MODIS / NDVI",
        "Índice espectral relacionado ao vigor vegetal. Nuvens, resolução e época do ano afetam a leitura.",
      ],
      [
        "Sem validação agronômica",
        "Os cenários do motor são estimativas: confirme a adequação com assistência técnica local.",
      ],
    ],
  },
  indicators: {
    title: "O que os indicadores significam?",
    subtitle: "Uma leitura simples para apoiar a exploração.",
    items: [
      [
        "NDVI",
        "Índice de −1 a 1 relacionado ao vigor vegetal. Não equivale à produtividade.",
      ],
      [
        "Umidade do solo",
        "Água na camada superficial. A umidade das raízes pode ser diferente.",
      ],
      [
        "pH do solo",
        "Indica acidez ou alcalinidade. A interpretação depende da cultura e da análise laboratorial.",
      ],
    ],
  },
  help: {
    title: "Da órbita à sua terra",
    subtitle: "Um roteiro rápido para explorar a NATIVA.",
    items: [
      [
        "1. Conheça a propriedade",
        "Explore os indicadores e o mapa ilustrativo.",
      ],
      [
        "2. Registre seu contexto",
        "Veja os campos de solo, água e histórico de cultivo.",
      ],
      [
        "3. Compare possibilidades",
        "Explore os perfis solo, água/clima e rentabilidade ou ajuste suas prioridades.",
      ],
    ],
  },
  technology: {
    title: "Tecnologia espacial. Propósito no campo.",
    subtitle: "Da observação do espaço às possibilidades da sua próxima safra.",
    items: [
      [
        "Dados em perspectiva",
        "Referências NASA POWER, SMAP e MODIS contextualizam indicadores de clima, umidade superficial e vegetação.",
      ],
      [
        "Da observação à decisão",
        "Localize sua propriedade, explore condições ambientais e compare estratégias de rotação.",
      ],
      [
        "Sobre esta demonstração",
        "Indicadores e cenários usam NASA POWER, MODIS e outras bases públicas para a localização cadastrada. No Histórico, temperatura e chuva vêm da NASA POWER; umidade e NDVI são ilustrativos.",
      ],
    ],
  },
};
// Single list of data sources shown in Settings, grouped by where each one feeds the app.
export const dataSources = {
  engine: [
    ["NASA POWER", "Clima diário desde 1991 • chuva, temperatura, geada e veranicos"],
    ["SoilGrids", "Argila, areia, carbono orgânico, pH e água disponível no solo"],
    ["MapBiomas", "Histórico de uso da terra, 2019–2024"],
    ["IBGE PAM", "Produtividade municipal das culturas"],
  ],
  indicators: [
    ["NASA POWER", "Temperatura média e precipitação acumulada"],
    ["Open-Meteo • ERA5-Land", "Umidade do solo"],
    ["NASA MODIS • ORNL DAAC", "Índice de vegetação (NDVI), a cada 16 dias"],
    ["Esri World Imagery", "Imagem de satélite do mapa"],
  ],
  illustrative: [
    ["NASA POWER", "Séries de temperatura e precipitação"],
    ["NASA SMAP", "Série de umidade superficial do solo"],
    ["NASA MODIS", "Série de vigor da vegetação (NDVI)"],
  ],
};

/** Texture class from a soil test (simplified SiBCS textural groups), so the texture label never contradicts clay/sand values. */
export function textureFromSoil(clay: number, sand: number): string {
  const silt = 100 - clay - sand;
  if (clay >= 35) return "Argiloso";
  if (sand - clay > 70) return "Arenoso";
  if (silt >= 50) return "Siltoso";
  return "Franco";
}
