"""Field Shift FastAPI application."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from field_shift.motor import servico

from . import __version__
from .rotas import health_router, router

log = logging.getLogger("field_shift_api")

DESCRICAO = """
**Field Shift** API: **crop-rotation** decision support (off-season / between seasons) for
**Western Paraná** (50 municipalities, IBGE code 4106). Given a field (demo id), a GeoJSON polygon
or a lat/lon point, it returns a diagnosis of the area and a ranking of rotations with a score, an estimated
margin (BRL/ha) and an explanation card per option.

Areas outside Western Paraná return **422** (`fora_da_regiao`).

**Data sources:** NASA POWER (climate), SoilGrids (soil), MapBiomas (land use and cover),
NASADEM (terrain), IBGE PAM (municipal yield), SEAB/DERAL (regional costs and prices) and
CONAB (reference prices and costs).

Income and risk figures are **estimates** to support the conversation with the agronomist; they do not
replace ZARC or a technical recommendation.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.dados_ok = False
    app.state.dados_erro = None
    try:
        servico.aquecer()
        app.state.dados_ok = True
    except Exception as exc:  # the API starts even without data; /health shows "degradado"
        log.exception("failed to load data on startup")
        app.state.dados_erro = f"{type(exc).__name__}: {exc}"
    yield


app = FastAPI(
    title="Field Shift API",
    description=DESCRICAO,
    version=__version__,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health_router)
app.include_router(router)


@app.exception_handler(servico.ForaDaRegiao)
async def _fora_da_regiao(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=422, content={"erro": "fora_da_regiao", "mensagem": str(exc)})


@app.exception_handler(servico.EntradaInvalida)
async def _entrada_invalida(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=400, content={"erro": "entrada_invalida", "mensagem": str(exc)})


@app.exception_handler(servico.ErroConsultaExterna)
async def _erro_consulta_externa(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=504, content={"erro": "timeout_externo", "mensagem": str(exc)})


@app.exception_handler(Exception)
async def _interno(request: Request, exc: Exception) -> JSONResponse:
    log.error("unexpected error in %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"erro": "interno", "mensagem": "Internal server error."},
    )
