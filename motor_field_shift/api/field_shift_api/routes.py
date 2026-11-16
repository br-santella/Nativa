"""HTTP routes. `def` (sync) endpoints run in the FastAPI threadpool."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from field_shift import crop_sheets, i18n
from field_shift.core import service

from . import __version__
from .schemas import (
    Area,
    ClimaOut,
    ContextoIn,
    DiagnosticoIn,
    DiagnosticoOut,
    ErroOut,
    HealthOut,
    RecomendacaoIn,
    RecomendacaoOut,
    Sowing,
)

ERRORS = {
    400: {"model": ErroOut, "description": "Entrada inválida segundo o motor (`entrada_invalida`)."},
    422: {"model": ErroOut, "description": "Fora do Paraná (`fora_da_regiao`) ou erro de validação do corpo."},
    500: {"model": ErroOut, "description": "Erro interno (`interno`)."},
}

health_router = APIRouter(tags=["saúde"])
router = APIRouter(prefix="/v1")


def _dump(m: Any) -> dict[str, Any] | None:
    return m.model_dump(exclude_none=True) if m is not None else None


@health_router.get("/health", response_model=HealthOut, summary="Estado do serviço")
def health(request: Request) -> HealthOut:
    ok = bool(getattr(request.app.state, "dados_ok", False))
    return HealthOut(
        status="ok" if ok else "degradado",
        dados_carregados=ok,
        versao=__version__,
        detalhe=getattr(request.app.state, "data_error", None),
    )


@router.get(
    "/opcoes",
    tags=["metadados"],
    summary="Culturas de verão e da 2ª janela, combinações, pesos padrão e metadados do motor",
    operation_id="opcoes_v1_opcoes_get",  # kept from the Portuguese function name: public OpenAPI contract
)
def options() -> dict[str, Any]:
    return i18n.localize(service.options())


@router.get("/talhoes/demo", tags=["metadados"], summary="Talhões de demonstração", operation_id="talhoes_demo_v1_talhoes_demo_get")
def demo_fields() -> Any:
    return i18n.localize(service.options().get("talhoes_demo", []))


@router.get(
    "/culturas/fichas",
    tags=["metadados"],
    summary="Fichas agronômicas das culturas (catalog/crops.yaml): faixas com unidade e fonte, e o mapa id do motor -> ficha",
    operation_id="fichas_culturas_v1_culturas_fichas_get",
)
def crop_sheet_catalog() -> dict[str, Any]:
    return i18n.localize(crop_sheets.public_sheets())


@router.post(
    "/diagnostico",
    response_model=DiagnosticoOut,
    responses=ERRORS,
    tags=["motor"],
    summary="Diagnóstico da área (relevo, solo, histórico, clima, produtividade)",
    operation_id="diagnostico_v1_diagnostico_post",  # kept from the Portuguese function name: public OpenAPI contract
)
def diagnosis(body: DiagnosticoIn) -> dict[str, Any]:
    extra = {}
    if body.analise_solo is not None:
        extra["soil_analysis"] = body.analise_solo.model_dump(exclude_none=True)
    return i18n.localize(service.diagnose(body.area.to_service(), sowing_second=body.semeadura_safrinha, **extra))


@router.post(
    "/recomendacao",
    response_model=RecomendacaoOut,
    responses=ERRORS,
    tags=["motor"],
    summary="O que entra depois da colheita do verão e como melhora a produção (`agora`), mais a próxima safra",
    operation_id="recomendacao_v1_recomendacao_post",  # kept from the Portuguese function name: public OpenAPI contract
)
def recommendation(body: RecomendacaoIn) -> dict[str, Any]:
    pesos = body.pesos.model_dump(exclude_none=True) if body.pesos else None
    adjustments = body.ajustes.model_dump(exclude_none=True) if body.ajustes else None
    return i18n.localize(service.recommend(
        body.area.to_service(),
        sowing_second=body.semeadura_safrinha,
        pesos=pesos or None,
        current_rotation=body.rotacao_atual,
        summer_stage=body.estagio_verao,
        expected_harvest=body.colheita_prevista,
        reference_date=body.data_referencia,
        rotations=[r.model_dump() for r in body.rotacoes] if body.rotacoes else None,
        adjustments=adjustments or None,
        n_alternatives=body.n_alternativas,
        include_diagnosis=body.incluir_diagnostico,
        soil_analysis=_dump(body.analise_solo),
        constraints=_dump(body.restricoes),
        irrigation=_dump(body.irrigacao),
        area_problems=body.problemas_area or None,
    ))



@router.get(
    "/clima",
    response_model=ClimaOut,
    responses=ERRORS,
    tags=["motor"],
    summary="Atalho: só o bloco de clima para um ponto",
    operation_id="clima_v1_clima_get",  # kept from the Portuguese function name: public OpenAPI contract
)
def climate(
    lat: float = Query(..., ge=-90, le=90, examples=[-24.95]),
    lon: float = Query(..., ge=-180, le=180, examples=[-53.45]),
    sowing_second: Sowing = Query("01/02", alias="semeadura_safrinha"),
) -> dict[str, Any]:
    diag = service.diagnose({"lat": lat, "lon": lon}, sowing_second=sowing_second)
    return i18n.localize(diag["clima"])


def _area_context(area: dict[str, Any], sowing: str) -> dict[str, Any]:
    from field_shift import context

    a = service._resolver_area(area)  # same validations and errors (400/422) as the recommendation
    return i18n.localize(context.build(a["lat"], a["lon"], sowing))


@router.post(
    "/contexto",
    tags=["contexto"],
    summary="Situação atual (informativa): ENSO, umidade do solo SMAP, MJO, pragas em surto",
    responses=ERRORS,
    operation_id="contexto_post_v1_contexto_post",  # kept from the Portuguese function name: public OpenAPI contract
)
def context_post(body: ContextoIn) -> dict[str, Any]:
    """Consulta fontes oficiais (NOAA, NASA SMAP, IDR-PR/ADAPAR) sobre eventos em curso. Não prevê nada e não altera
    ranking nem nota. Cada fonte falha isoladamente: `{"disponivel": false, "motivo": ...}`."""
    return _area_context(body.area.to_service(), body.semeadura_safrinha)


@router.get(
    "/contexto",
    tags=["contexto"],
    summary="Situação atual (informativa) por talhao_id ou ponto lat/lon",
    responses=ERRORS,
    operation_id="contexto_get_v1_contexto_get",  # kept from the Portuguese function name: public OpenAPI contract
)
def context_get(
    field_id: str | None = Query(None, alias="talhao_id", examples=["72638"]),
    lat: float | None = Query(None, ge=-90, le=90, examples=[-24.95]),
    lon: float | None = Query(None, ge=-180, le=180, examples=[-53.45]),
    sowing_second: Sowing = Query("01/02", alias="semeadura_safrinha"),
) -> dict[str, Any]:
    """Mesmo contexto do POST, para talhão demo ou ponto. Para polígono use `POST /v1/contexto`."""
    try:
        area = Area(talhao_id=field_id, lat=lat, lon=lon)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _area_context(area.to_service(), sowing_second)


@router.get("/monitoramento", tags=["clima"], summary="Indicadores recentes no ponto de referência da propriedade")
def monitoring(lat: float = Query(ge=-90, le=90), lon: float = Query(ge=-180, le=180)) -> dict[str, Any]:
    from field_shift.monitoring import monitor

    return monitor(lat, lon)


@router.get("/clima/mensal", tags=["clima"], summary="Temperatura média e chuva mensais de um ano no ponto (NASA POWER)")
def monthly_climate(
    lat: float = Query(ge=-90, le=90, examples=[-24.81]),
    lon: float = Query(ge=-180, le=180, examples=[-53.55]),
    year: int = Query(alias="ano", ge=1981, le=2100, examples=[2025]),
) -> dict[str, Any]:
    """Doze meses (jan–dez) de temperatura média do ar a 2 m (°C) e chuva total (mm), célula NASA POWER de ~50 km.
    Meses ainda não publicados pela POWER vêm `null`. Falha do provedor: 504 `timeout_externo`."""
    import requests

    from field_shift.monitoring import monthly_climate as fetch

    try:
        return fetch(lat, lon, year)
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        raise service.ExternalQueryError("NASA POWER indisponível.") from exc
