"""HTTP routes. `def` (sync) endpoints run in the FastAPI threadpool."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

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
    return service.options()


@router.get("/talhoes/demo", tags=["metadados"], summary="Talhões de demonstração", operation_id="talhoes_demo_v1_talhoes_demo_get")
def demo_fields() -> Any:
    return service.options().get("talhoes_demo", [])


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
    return service.diagnose(body.area.to_service(), sowing_second=body.semeadura_safrinha, **extra)


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
    return service.recommend(
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
    )



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
    return diag["clima"]


def _area_context(area: dict[str, Any], sowing: str) -> dict[str, Any]:
    from field_shift import context

    a = service._resolver_area(area)  # same validations and errors (400/422) as the recommendation
    return context.build(a["lat"], a["lon"], sowing)


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
