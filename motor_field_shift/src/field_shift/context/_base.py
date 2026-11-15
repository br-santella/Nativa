"""Infraestrutura comum das fontes de contexto: cache em disco com TTL, fallback e carimbos.

Regras: cada fonte tem timeout curto, nunca levanta exceção para o chamador e devolve sempre
`consultado_em` e `fonte` (nome + URL). Falha vira {"disponivel": False, "motivo": ...}.
O contexto é informativo: nada aqui altera ranking ou nota do motor.
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

log = logging.getLogger("field_shift.context")

ROOT = Path(__file__).resolve().parents[3]
CACHE_DIR = Path(os.environ.get("FIELD_SHIFT_CACHE_CONTEXTO", ROOT / "data/cache_contexto"))
CURATED_DIR = ROOT / "data/contexto"
TIMEOUT_HTTP = 15  # s
UA = "FieldShift/0.1 (NASA Space Apps 2026; contexto informativo)"

TTL_ENSO = 24 * 3600
TTL_SMAP = 24 * 3600
TTL_MJO = 6 * 3600
TTL_PESTS = 24 * 3600
TTL_ALERTS = 30 * 60


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def source(nome: str, url: str) -> dict[str, str]:
    return {"nome": nome, "url": url}


def unavailable(reason: str, source_: dict[str, str]) -> dict[str, Any]:
    return {"disponivel": False, "motivo": reason, "consultado_em": now_iso(), "fonte": source_}


def _file(key: str) -> Path:
    h = hashlib.sha1(key.encode()).hexdigest()[:16]
    insurance = "".join(c if c.isalnum() or c in "-_" else "_" for c in key)[:60]
    return CACHE_DIR / f"{insurance}_{h}.json"


def read_cache(key: str, ttl: float, allow_expired: bool = False) -> Any | None:
    p = _file(key)
    try:
        if not p.exists():
            return None
        if not allow_expired and time.time() - p.stat().st_mtime > ttl:
            return None
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # cache corrompido não pode quebrar nada
        return None


def write_cache(key: str, valor: Any) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = _file(key).with_suffix(".tmp")
        tmp.write_text(json.dumps(valor, ensure_ascii=False), encoding="utf-8")
        tmp.replace(_file(key))
    except Exception:
        log.warning("não foi possível gravar cache %s", key, exc_info=True)


def com_cache(key: str, ttl: float, fetch: Callable[[], Any]) -> tuple[Any, bool]:
    """Valor bruto da fonte com cache. Devolve (valor, veio_do_cache). `buscar` pode levantar exceção:
    nesse caso, usa o cache vencido (se existir) e marca; sem cache, repassa a exceção."""
    v = read_cache(key, ttl)
    if v is not None:
        return v, True
    try:
        v = fetch()
    except Exception:
        old_ = read_cache(key, ttl, allow_expired=True)
        if old_ is not None:
            log.warning("fonte %s falhou; usando cache vencido", key)
            return old_, True
        raise
    write_cache(key, v)
    return v, False


def download_text(url: str, timeout: float = TIMEOUT_HTTP, params: dict | None = None) -> str:
    import requests

    r = requests.get(url, timeout=timeout, headers={"User-Agent": UA}, params=params)
    r.raise_for_status()
    return r.text


def insurance(nome: str, source_: dict[str, str], fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """Executa a consulta de uma fonte garantindo o contrato (nunca levanta)."""
    try:
        out = fn()
        out.setdefault("consultado_em", now_iso())
        out.setdefault("fonte", source_)
        out.setdefault("disponivel", True)
        return out
    except Exception as exc:
        log.warning("fonte de contexto %s indisponível: %s: %s", nome, type(exc).__name__, exc)
        return unavailable(f"{type(exc).__name__}: {exc}"[:300], source_)
