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
      "De onde vêm os dados e até onde eles valem. No Histórico, umidade do solo e NDVI são ilustrativos; o restante usa dados reais do ponto cadastrado.",
    items: [
      [
        "NASA POWER",
        "Clima diário desde 1991 (chuva, temperatura e evapotranspiração) em células de ~50 km. Representa a região, não o talhão.",
      ],
      [
        "Umidade do solo",
        "O indicador usa ERA5-Land (camada de 0–7 cm) e a camada do mapa usa NASA SMAP. Nenhum dos dois mede a zona das raízes.",
      ],
      [
        "NASA MODIS · NDVI",
        "Vigor da vegetação em pixels de 250 m, a cada 16 dias. No indicador, leituras com nuvem são descartadas.",
      ],
      [
        "O que entra na nota",
        "Clima (NASA POWER), relevo (NASADEM), solo (SoilGrids), uso da terra (MapBiomas), produtividade municipal (IBGE) e preços e custos (DERAL e CONAB).",
      ],
      [
        "Satélite × estação",
        "Comparada com 7 estações do INMET, a NASA POWER acompanha bem a temperatura mínima (correlação de 0,94), mas registra cerca de 40% menos dias de geada. Em baixadas, o risco real de geada pode ser maior que o estimado.",
      ],
      [
        "Validado com dados, sem revisão agronômica",
        "As regras foram conferidas com o ZARC e com safras passadas (IBGE), mas ainda não foram revisadas por agrônomos. Confirme com a assistência técnica local.",
      ],
    ],
  },
  indicators: {
    title: "O que os indicadores significam?",
    subtitle:
      "Termos usados nos indicadores, no Histórico e nas estratégias de rotação.",
    items: [
      [
        "NDVI",
        "Vigor da vegetação, de −1 a 1. Abaixo de 0,2: solo exposto ou palha; acima de 0,6: lavoura vigorosa. Não mede produtividade.",
      ],
      [
        "pH do solo",
        "Acidez do solo. Cada cultura tem uma faixa adequada; abaixo dela, a correção costuma ser a calagem.",
      ],
      [
        "Umidade do solo",
        "Água nos primeiros centímetros do solo (0–7 cm no indicador). As raízes exploram camadas mais fundas, que podem estar diferentes.",
      ],
      [
        "Anomalia de umidade do solo",
        "Diferença em relação ao normal da mesma época. Separa uma seca fora do comum da estação seca esperada.",
      ],
      [
        "Fixadoras de nitrogênio",
        "Leguminosas, como crotalária e soja, captam nitrogênio do ar com bactérias nas raízes e deixam parte dele no solo para a cultura seguinte.",
      ],
      [
        "Plantas de cobertura",
        "Aveia, milheto e braquiária mantêm o solo coberto entre safras. A palha reduz erosão e evaporação e, ao se decompor, aumenta a matéria orgânica.",
      ],
      [
        "Raízes profundas",
        "Nabo forrageiro e braquiária abrem canais em camadas compactadas, melhoram a infiltração da água e trazem nutrientes do fundo para a superfície.",
      ],
      [
        "Tolerantes à seca",
        "Sorgo e milheto produzem com menos água que o milho, o que reduz o risco de perda em anos de veranico.",
      ],
      [
        "Evapotranspiração de referência (ET0)",
        "Água que solo e plantas perdem para o ar, em mm por dia. Quanto maior, mais água a lavoura consome.",
      ],
      [
        "Balanço hídrico",
        "Chuva menos evapotranspiração, calculado dia a dia (método FAO-56). Mostra se falta água na fase crítica da cultura.",
      ],
      [
        "Déficit hídrico",
        "A cultura recebe menos de 55% da água de que precisa na fase crítica. O risco é a fração dos 34 anos (1991–2024) em que isso ocorreu.",
      ],
      [
        "Veranico",
        "15 dias ou mais com menos de 1 mm de chuva por dia, em março e abril. Usado quando faltam dados de solo para o balanço hídrico.",
      ],
      [
        "Risco de geada",
        "Fração dos 34 anos com mínima de 3 °C ou menos na floração e no enchimento de grão. Semear mais tarde aumenta o risco.",
      ],
      [
        "Célula de grade",
        "Área com um único valor. Na NASA POWER, cerca de 50 km: o dado descreve a região, não o talhão.",
      ],
    ],
  },
  help: {
    title: "Da órbita à sua terra",
    subtitle:
      "Um roteiro rápido para explorar a NATIVA.",
    items: [
      [
        "1. Conheça a propriedade",
        "Na Visão Geral, veja os indicadores de clima e o mapa com camadas da NASA.",
      ],
      [
        "2. Registre seu contexto",
        "No Histórico e em Configurações, informe cultivos anteriores, solo e água.",
      ],
      [
        "3. Compare possibilidades",
        "Em Estratégias de Rotação, escolha um perfil de prioridade ou ajuste os controles.",
      ],
    ],
  },
  technology: {
    title: "Tecnologia espacial. Propósito no campo.",
    subtitle:
      "Da observação do espaço às possibilidades da sua próxima safra.",
    items: [
      [
        "Dados em perspectiva",
        "NASA POWER traz o clima, MODIS o vigor da vegetação e SMAP a umidade do solo no mapa.",
      ],
      [
        "Da observação à decisão",
        "Localize sua propriedade, explore condições ambientais e compare estratégias de rotação.",
      ],
      [
        "Sobre esta demonstração",
        "Os cultivos de exemplo e as séries de umidade do solo e NDVI do Histórico são ilustrativos. O restante usa dados públicos para a localização cadastrada.",
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
