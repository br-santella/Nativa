"""HTTP routes. `def` (synchronous) endpoints run in the FastAPI threadpool."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from field_shift.motor import servico

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
    Semeadura,
)

ERROS = {
    400: {"model": ErroOut, "description": "Input rejected by the engine (`entrada_invalida`)."},
    422: {"model": ErroOut, "description": "Outside Western Paraná (`fora_da_regiao`) or body validation error."},
    500: {"model": ErroOut, "description": "Internal error (`interno`)."},
}

health_router = APIRouter(tags=["health"])
router = APIRouter(prefix="/v1")


def _dump(m: Any) -> dict[str, Any] | None:
    return m.model_dump(exclude_none=True) if m is not None else None


@health_router.get("/health", response_model=HealthOut, summary="Service status")
def health(request: Request) -> HealthOut:
    ok = bool(getattr(request.app.state, "dados_ok", False))
    return HealthOut(
        status="ok" if ok else "degradado",
        dados_carregados=ok,
        versao=__version__,
        detalhe=getattr(request.app.state, "dados_erro", None),
    )


@router.get(
    "/opcoes",
    tags=["metadata"],
    summary="Summer and second-window crops, combinations, default weights and engine metadata",
)
def opcoes() -> dict[str, Any]:
    return servico.opcoes()


@router.get("/talhoes/demo", tags=["metadata"], summary="Demo fields")
def talhoes_demo() -> Any:
    return servico.opcoes().get("talhoes_demo", [])


@router.post(
    "/diagnostico",
    response_model=DiagnosticoOut,
    responses=ERROS,
    tags=["engine"],
    summary="Diagnosis of the area (terrain, soil, history, climate, yield)",
)
def diagnostico(corpo: DiagnosticoIn) -> dict[str, Any]:
    extra = {}
    if corpo.analise_solo is not None:
        extra["analise_solo"] = corpo.analise_solo.model_dump(exclude_none=True)
    return servico.diagnosticar(corpo.area.para_servico(), semeadura_safrinha=corpo.semeadura_safrinha, **extra)


@router.post(
    "/recomendacao",
    response_model=RecomendacaoOut,
    responses=ERROS,
    tags=["engine"],
    summary="What goes in after the summer harvest and how it improves production (`agora`), plus the next season",
)
def recomendacao(corpo: RecomendacaoIn) -> dict[str, Any]:
    pesos = corpo.pesos.model_dump(exclude_none=True) if corpo.pesos else None
    ajustes = corpo.ajustes.model_dump(exclude_none=True) if corpo.ajustes else None
    return servico.recomendar(
        corpo.area.para_servico(),
        semeadura_safrinha=corpo.semeadura_safrinha,
        pesos=pesos or None,
        rotacao_atual=corpo.rotacao_atual,
        estagio_verao=corpo.estagio_verao,
        colheita_prevista=corpo.colheita_prevista,
        data_referencia=corpo.data_referencia,
        rotacoes=[r.model_dump() for r in corpo.rotacoes] if corpo.rotacoes else None,
        ajustes=ajustes or None,
        n_alternativas=corpo.n_alternativas,
        incluir_diagnostico=corpo.incluir_diagnostico,
        analise_solo=_dump(corpo.analise_solo),
        restricoes=_dump(corpo.restricoes),
        irrigacao=_dump(corpo.irrigacao),
    )


@router.get(
    "/clima",
    response_model=ClimaOut,
    responses=ERROS,
    tags=["engine"],
    summary="Shortcut: only the climate block for a point",
)
def clima(
    lat: float = Query(..., ge=-90, le=90, examples=[-24.95]),
    lon: float = Query(..., ge=-180, le=180, examples=[-53.45]),
    semeadura_safrinha: Semeadura = "01/02",
) -> dict[str, Any]:
    diag = servico.diagnosticar({"lat": lat, "lon": lon}, semeadura_safrinha=semeadura_safrinha)
    return diag["clima"]


def _contexto_da_area(area: dict[str, Any], semeadura: str) -> dict[str, Any]:
    from field_shift import contexto

    a = servico._resolver_area(area)  # same validations and errors (400/422) as the recommendation
    return contexto.montar(a["lat"], a["lon"], semeadura)


@router.post(
    "/contexto",
    tags=["context"],
    summary="Current conditions (informational): ENSO, SMAP soil moisture, MJO, pest outbreaks",
    responses=ERROS,
)
def contexto_post(corpo: ContextoIn) -> dict[str, Any]:
    """Queries official sources (NOAA, NASA SMAP, IDR-PR/ADAPAR) about ongoing events. It forecasts nothing and does not change
    the ranking or the score. Each source fails independently: `{"disponivel": false, "motivo": ...}`."""
    return _contexto_da_area(corpo.area.para_servico(), corpo.semeadura_safrinha)


@router.get(
    "/contexto",
    tags=["context"],
    summary="Current conditions (informational) by talhao_id or lat/lon point",
    responses=ERROS,
)
def contexto_get(
    talhao_id: str | None = Query(None, examples=["72638"]),
    lat: float | None = Query(None, ge=-90, le=90, examples=[-24.95]),
    lon: float | None = Query(None, ge=-180, le=180, examples=[-53.45]),
    semeadura_safrinha: Semeadura = "01/02",
) -> dict[str, Any]:
    """Same context as the POST, for a demo field or a point. For a polygon use `POST /v1/contexto`."""
    try:
        area = Area(talhao_id=talhao_id, lat=lat, lon=lon)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _contexto_da_area(area.para_servico(), semeadura_safrinha)
