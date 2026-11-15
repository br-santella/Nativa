"""Shared infrastructure of the context sources: disk cache with TTL, fallback and timestamps.

Rules: each source has a short timeout, never raises an exception to the caller and always returns
`consultado_em` and `fonte` (name + URL). A failure becomes {"disponivel": False, "motivo": ...}.
The context is informational: nothing here changes the engine's ranking or score.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger("field_shift.contexto")

ROOT = Path(__file__).resolve().parents[3]
CACHE_DIR = Path(os.environ.get("FIELD_SHIFT_CACHE_CONTEXTO", ROOT / "data/cache_contexto"))
CURADO_DIR = ROOT / "data/contexto"
TIMEOUT_HTTP = 15  # s
UA = "FieldShift/0.1 (NASA Space Apps 2026; informational context)"

TTL_ENSO = 24 * 3600
TTL_SMAP = 24 * 3600
TTL_MJO = 6 * 3600
TTL_PRAGAS = 24 * 3600
TTL_ALERTAS = 30 * 60


def agora_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def fonte(nome: str, url: str) -> dict[str, str]:
    return {"nome": nome, "url": url}


def indisponivel(motivo: str, fonte_: dict[str, str]) -> dict[str, Any]:
    return {"disponivel": False, "motivo": motivo, "consultado_em": agora_iso(), "fonte": fonte_}


def _arquivo(chave: str) -> Path:
    h = hashlib.sha1(chave.encode()).hexdigest()[:16]
    seguro = "".join(c if c.isalnum() or c in "-_" else "_" for c in chave)[:60]
    return CACHE_DIR / f"{seguro}_{h}.json"


def ler_cache(chave: str, ttl: float, permitir_vencido: bool = False) -> Any | None:
    p = _arquivo(chave)
    try:
        if not p.exists():
            return None
        if not permitir_vencido and time.time() - p.stat().st_mtime > ttl:
            return None
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # a corrupted cache must not break anything
        return None


def gravar_cache(chave: str, valor: Any) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = _arquivo(chave).with_suffix(".tmp")
        tmp.write_text(json.dumps(valor, ensure_ascii=False), encoding="utf-8")
        tmp.replace(_arquivo(chave))
    except Exception:
        log.warning("could not write cache %s", chave, exc_info=True)


def com_cache(chave: str, ttl: float, buscar: Callable[[], Any]) -> tuple[Any, bool]:
    """Raw value of the source with cache. Returns (value, came_from_cache). `buscar` may raise:
    in that case, it uses the expired cache (if any) and flags it; without a cache, it re-raises the exception."""
    v = ler_cache(chave, ttl)
    if v is not None:
        return v, True
    try:
        v = buscar()
    except Exception:
        velho = ler_cache(chave, ttl, permitir_vencido=True)
        if velho is not None:
            log.warning("source %s failed; using expired cache", chave)
            return velho, True
        raise
    gravar_cache(chave, v)
    return v, False


def baixar_texto(url: str, timeout: float = TIMEOUT_HTTP, params: dict | None = None) -> str:
    import requests

    r = requests.get(url, timeout=timeout, headers={"User-Agent": UA}, params=params)
    r.raise_for_status()
    return r.text


def seguro(nome: str, fonte_: dict[str, str], fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """Runs a source query while guaranteeing the contract (never raises)."""
    try:
        out = fn()
        out.setdefault("consultado_em", agora_iso())
        out.setdefault("fonte", fonte_)
        out.setdefault("disponivel", True)
        return out
    except Exception as exc:
        log.warning("context source %s unavailable: %s: %s", nome, type(exc).__name__, exc)
        return indisponivel(f"{type(exc).__name__}: {exc}"[:300], fonte_)
