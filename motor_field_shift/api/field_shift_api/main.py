"""Field Shift FastAPI application."""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from field_shift import i18n
from field_shift.core import service

from . import __version__
from .routes import health_router, router

log = logging.getLogger("field_shift_api")

DESCRIPTION = """
API do **Field Shift**: apoio à decisão de **rotação de culturas** (safrinha / entressafra) para o
**Paraná inteiro** (399 municípios, código IBGE 41). Dado um talhão (id demo), um polígono GeoJSON
ou um ponto lat/lon, devolve um diagnóstico da área e um ranking de rotações com nota, margem
estimada (R$/ha) e um cartão explicativo por opção.

Áreas fora do Paraná retornam **422** (`fora_da_regiao`).

**Atenção:** fora do **Oeste do Paraná**, os custos e preços usados na renda e o calendário (vazio
sanitário e janela de semeadura da soja) continuam sendo a referência do Oeste e podem diferir na
região; a resposta traz um aviso nesse caso. Confirme a portaria vigente da ADAPAR e o ZARC do município.

**Fontes de dados:** NASA POWER (clima), SoilGrids (solo), MapBiomas (uso e cobertura do solo),
NASADEM (relevo), IBGE PAM (produtividade municipal), SEAB/DERAL (custos e preços regionais) e
CONAB (preços e custos de referência).

Os números de renda e risco são **estimativas** para apoiar a conversa com o agrônomo, não
substituem o ZARC nem a recomendação técnica.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.dados_ok = False
    app.state.data_error = None
    try:
        service.warm_up()
        app.state.dados_ok = True
    except Exception as exc:  # the API starts even without data; /health reports "degradado"
        log.exception("failed to load data at startup")
        app.state.data_error = f"{type(exc).__name__}: {exc}"
    yield


def _language(
    lang: Annotated[str | None, Query(
        description="Idioma dos textos da resposta: `pt-BR` (padrão) ou `en`. Tem precedência sobre o header "
                    "`Accept-Language`; valor desconhecido = pt-BR. Só os textos mudam: chaves, ids e números são os mesmos.",
    )] = None,
) -> None:
    """Documents the `lang` parameter; the response is translated by the middleware below."""


app = FastAPI(
    title="Field Shift API",
    description=DESCRIPTION,
    version=__version__,
    lifespan=lifespan,
    dependencies=[Depends(_language)],
)
_UNTRANSLATED_PATHS = ("/openapi.json", "/docs", "/redoc")  # the OpenAPI schema stays in Portuguese


@app.middleware("http")
async def _response_language(request: Request, call_next):
    """Translate the JSON body to the requested language (`lang` > Accept-Language > pt-BR) and set Content-Language.

    The engine always writes pt-BR; English is produced here, at the edge, so the pt-BR response is untouched."""
    locale = i18n.resolve_locale(request.query_params.get("lang"), request.headers.get("accept-language"))
    response = await call_next(request)
    if request.url.path.startswith(_UNTRANSLATED_PATHS):
        return response
    response.headers["Content-Language"] = locale
    response.headers["Vary"] = "Accept-Language"
    if locale == i18n.DEFAULT_LOCALE or not response.headers.get("content-type", "").startswith("application/json"):
        return response
    body = b"".join([chunk async for chunk in response.body_iterator])
    translated = i18n.translate(json.loads(body), locale)
    headers = {k: v for k, v in response.headers.items() if k.lower() != "content-length"}
    return Response(content=json.dumps(translated, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode(),
                    status_code=response.status_code, headers=headers, media_type="application/json")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health_router)
app.include_router(router)


@app.exception_handler(service.OutOfRegion)
async def _out_of_region(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=422, content={"erro": "fora_da_regiao", "mensagem": str(exc)})


@app.exception_handler(service.InvalidInput)
async def _invalid_input(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=400, content={"erro": "entrada_invalida", "mensagem": str(exc)})


@app.exception_handler(service.ExternalQueryError)
async def _external_query_error(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=504, content={"erro": "timeout_externo", "mensagem": str(exc)})


@app.exception_handler(Exception)
async def _internal(request: Request, exc: Exception) -> JSONResponse:
    log.error("unexpected error in %s %s", request.method, request.url.path, exc_info=exc)
    # this handler runs outside the language middleware (Starlette's server-error layer), so it translates itself
    locale = i18n.resolve_locale(request.query_params.get("lang"), request.headers.get("accept-language"))
    return JSONResponse(
        status_code=500,
        content=i18n.translate({"erro": "interno", "mensagem": "Erro interno do servidor."}, locale),
        headers={"Content-Language": locale, "Vary": "Accept-Language"},
    )
