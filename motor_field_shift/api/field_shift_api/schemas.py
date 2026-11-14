"""Schemas Pydantic (entrada e saída) da API."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Semeadura = Literal["15/01", "01/02", "15/02", "01/03", "15/03"]
RotacaoSlug = Literal[
    "milho_safrinha",
    "milho_braquiaria",
    "trigo",
    "aveia",
    "milheto_crotalaria",
    "pousio",
    "soja_safrinha",
]
CulturaCusto = Literal[
    "soja", "milho", "milho_2safra", "trigo", "aveia", "milheto_crotalaria", "braquiaria_consorcio", "pousio"
]
Peso = Annotated[float, Field(ge=0, le=10)]

POLIGONO_EXEMPLO: dict[str, Any] = {
    "type": "Polygon",
    "coordinates": [
        [
            [-53.3045, -24.9045],
            [-53.2955, -24.9045],
            [-53.2955, -24.8955],
            [-53.3045, -24.8955],
            [-53.3045, -24.9045],
        ]
    ],
}


# --------------------------------------------------------------------------
# Entrada
# --------------------------------------------------------------------------
class Area(BaseModel):
    """Área de análise. Informe EXATAMENTE UMA das formas: `geometry`, `lat`+`lon` ou `talhao_id`."""

    geometry: dict[str, Any] | None = Field(
        None,
        description="GeoJSON Polygon, MultiPolygon ou Feature em EPSG:4326 (lon, lat). Máx. 5000 ha.",
    )
    lat: float | None = Field(None, ge=-90, le=90, description="Latitude (vira um quadrado de ~100 ha).")
    lon: float | None = Field(None, ge=-180, le=180, description="Longitude (vira um quadrado de ~100 ha).")
    talhao_id: str | None = Field(None, description="Id de um talhão demo (ver GET /v1/talhoes/demo).")

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"talhao_id": "72638"}]},
    )

    @model_validator(mode="after")
    def _uma_forma(self) -> "Area":
        ponto = self.lat is not None or self.lon is not None
        if ponto and (self.lat is None or self.lon is None):
            raise ValueError("para ponto, informe 'lat' e 'lon' juntos")
        formas = sum([self.geometry is not None, ponto, self.talhao_id is not None])
        if formas != 1:
            raise ValueError("informe exatamente uma forma de área: 'geometry', 'lat'+'lon' ou 'talhao_id'")
        return self

    def para_servico(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class Ajustes(BaseModel):
    """Preços e custos próprios do produtor (sobrescrevem os valores de referência)."""

    precos: dict[Literal["soja", "milho", "trigo"], Annotated[float, Field(ge=0)]] | None = Field(
        None, description="Preço em R$/saca (60 kg)."
    )
    custos: dict[CulturaCusto, Annotated[float, Field(ge=0)]] | None = Field(
        None, description="Custo por cultura em R$/ha ('milho' é alias de 'milho_2safra')."
    )
    linha_custo: Literal["coe", "cot", "ct"] | None = Field(
        None, description="'coe' (operacional efetivo), 'cot' (operacional total) ou 'ct' (custo total)."
    )

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"precos": {"soja": 125.0, "milho": 58.0, "trigo": 82.0}}]},
    )


class Pesos(BaseModel):
    """Importância de cada critério, de 0 a 10. Omitidos usam o padrão (renda 5, demais 3)."""

    renda: Peso | None = None
    solo: Peso | None = None
    agua: Peso | None = None
    pragas: Peso | None = None
    risco: Peso | None = None

    model_config = ConfigDict(extra="forbid")


class DiagnosticoIn(BaseModel):
    area: Area
    semeadura_safrinha: Semeadura = Field("01/02", description="Data de semeadura da safrinha (dd/mm).")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"area": {"talhao_id": "72638"}, "semeadura_safrinha": "01/02"},
                {"area": {"geometry": POLIGONO_EXEMPLO}, "semeadura_safrinha": "15/02"},
                {"area": {"lat": -24.95, "lon": -53.45}},
            ]
        }
    )


class RecomendacaoIn(BaseModel):
    area: Area
    semeadura_safrinha: Semeadura = Field("01/02", description="Data de semeadura da safrinha (dd/mm).")
    pesos: Pesos | None = Field(None, description="Pesos dos critérios (0 a 10).")
    rotacao_atual: RotacaoSlug | None = Field(None, description="Rotação que o produtor usa hoje (para comparar).")
    ajustes: Ajustes | None = None
    n_alternativas: int = Field(3, ge=1, le=6, description="Quantas alternativas devolver.")
    incluir_diagnostico: bool = Field(True, description="Inclui o diagnóstico completo na resposta.")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"area": {"talhao_id": "72638"}, "semeadura_safrinha": "01/02", "n_alternativas": 3},
                {
                    "area": {"geometry": POLIGONO_EXEMPLO},
                    "semeadura_safrinha": "15/02",
                    "pesos": {"renda": 8, "solo": 3, "agua": 3, "pragas": 5, "risco": 4},
                    "rotacao_atual": "milho_safrinha",
                    "ajustes": {"precos": {"soja": 125.0, "milho": 58.0, "trigo": 82.0}, "linha_custo": "cot"},
                },
            ]
        }
    )


# --------------------------------------------------------------------------
# Saída (permissiva: campos extras do serviço passam adiante)
# --------------------------------------------------------------------------
class _Saida(BaseModel):
    model_config = ConfigDict(extra="allow")


class Centroide(_Saida):
    lat: float
    lon: float


class Municipio(_Saida):
    cod_ibge: str | int | None = None
    nome: str | None = None


class AreaOut(_Saida):
    origem: str | None = None
    talhao_id: str | None = None
    area_ha: float | None = None
    centroide: Centroide | None = None
    municipio: Municipio | None = None
    geometry: dict[str, Any] | None = None


class RotacaoDetectada(_Saida):
    rotacao: str | None = None
    fonte: str | None = None
    dias_solo_descoberto: int | float | None = None


class GeadaPorSemeadura(_Saida):
    semeadura: str
    prob: float | None = None
    anos_com_evento: int | None = None
    n_anos: int | None = None


class ClimaOut(_Saida):
    fonte: str | None = None
    celula: dict[str, Any] | str | None = None
    semeadura_safrinha: str | None = None
    riscos: dict[str, Any] | None = None
    geada_por_semeadura: list[GeadaPorSemeadura] = []
    diagnostico: dict[str, Any] | None = None


class DiagnosticoOut(_Saida):
    area: AreaOut
    relevo: dict[str, Any] | None = None
    solo: dict[str, Any] | None = None
    historico: list[dict[str, Any]] = []
    rotacao_detectada: RotacaoDetectada | None = None
    clima: ClimaOut | None = None
    produtividade: dict[str, Any] | None = None
    avisos: list[str] = []


class ItemMargem(_Saida):
    cultura: str
    rendimento_sc_ha: float | None = None
    preco: float | None = None
    custo: float | None = None
    margem_r_ha: float | None = None
    fonte: str | None = None


class Margem(_Saida):
    total_r_ha: float | None = None
    incremental_r_ha: float | None = None
    escala_S_r_ha: float | None = None
    itens: list[ItemMargem] = []
    ano_ruim_r_ha: float | None = None


class Card(_Saida):
    por_que: str | None = None
    evidencias: list[Any] = []
    beneficios: list[Any] = []
    lacunas: list[Any] = []
    riscos: list[Any] = []
    avisos: list[Any] = []


class ItemRanking(_Saida):
    posicao: int | None = None
    id: str
    rotacao: str
    nota: float | None = None
    atual: bool = False
    criterios: dict[str, float | None] = {}
    contribuicoes: dict[str, float | None] = {}
    margem: Margem | None = None
    card: Card | None = None


class ItemAtual(ItemRanking):
    """Rotação atual. Se eliminada por regra dura: posicao/nota nulos, eliminada=true e motivos."""

    id: str | None = None
    rotacao: str | None = None
    eliminada: bool = False
    motivos: list[str] = []


class Eliminada(_Saida):
    id: str
    rotacao: str | None = None
    motivos: list[str] = []


class Metodologia(_Saida):
    formula: str | None = None
    criterios: dict[str, Any] = {}
    versao: str | None = None


class RecomendacaoOut(_Saida):
    entrada: dict[str, Any] = {}
    diagnostico: DiagnosticoOut | None = None
    ranking: list[ItemRanking] = []
    atual: ItemAtual | None = None
    alternativas: list[dict[str, Any]] = []
    eliminadas: list[Eliminada] = []
    avisos: list[str] = []
    metodologia: Metodologia | None = None


class HealthOut(BaseModel):
    status: Literal["ok", "degradado"]
    dados_carregados: bool
    versao: str
    detalhe: str | None = None


class ErroOut(BaseModel):
    erro: str
    mensagem: str | None = None
