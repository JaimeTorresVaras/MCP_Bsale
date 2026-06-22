#!/usr/bin/env python3
"""Bsale MCP Server v4 — Entry point.
Importa todos los módulos de tools para registrar las herramientas en el objeto mcp,
luego arranca el servidor en el transporte configurado.
"""

import os
import sys

# Garantiza que el directorio de este archivo esté en sys.path,
# independientemente de desde dónde se invoque el script.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import mcp, TRANSPORT, SSE_HOST, SSE_PORT, BSALE_TOKEN, log

# Importar los módulos de tools registra los @mcp.tool() automáticamente
import tools.clientes     # noqa: F401
import tools.productos    # noqa: F401
import tools.stock        # noqa: F401
import tools.analisis     # noqa: F401
import tools.documentos   # noqa: F401
import tools.ventas       # noqa: F401
import tools.logistica    # noqa: F401
import tools.referencia   # noqa: F401
import tools.estadisticas # noqa: F401

from starlette.requests import Request
from starlette.responses import JSONResponse


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """Endpoint público de salud. No requiere autorización."""
    return JSONResponse({"status": "ok", "service": "bsale-mcp"})


# ── Cache warming ────────────────────────────────────────────────────────────
# Pre-calienta los escaneos pesados (documentos del mes/mes pasado/año y stock)
# en un hilo aparte, para que las consultas de períodos comunes respondan al
# instante y no haya timeouts en la primera consulta. El resultado se guarda en
# el caché compartido en memoria; un hilo separado es seguro porque solo escribe
# en ese dict (los clientes httpx se crean y cierran por request).
import threading
import time as _time
import asyncio as _asyncio


async def _warm_once() -> None:
    from transforms import _parse_periodo
    from domain import _resumen_documentos, _agrupar_stocks
    for kw in ("mes", "mes_pasado", "anio"):
        try:
            ts_i, ts_f, _, _ = _parse_periodo(kw)
            await _resumen_documentos(ts_i, ts_f)
        except Exception as e:  # noqa: BLE001
            log.warning("warm %s: %s", kw, e)
    try:
        await _agrupar_stocks()
    except Exception as e:  # noqa: BLE001
        log.warning("warm stock: %s", e)


def _warm_loop() -> None:
    while True:
        try:
            _asyncio.run(_warm_once())
            log.info("cache warming OK")
        except Exception as e:  # noqa: BLE001
            log.warning("warm loop: %s", e)
        _time.sleep(1200)  # cada 20 min (el caché dura 30, deja margen)


if __name__ == "__main__":
    log.info("Bsale MCP Server v4 iniciando... (transporte: %s)", TRANSPORT)
    if not BSALE_TOKEN:
        log.error("BSALE_API_TOKEN no configurado.")
        sys.exit(1)

    if TRANSPORT == "sse":
        log.info("Modo remoto SSE en %s:%s", SSE_HOST, SSE_PORT)
        threading.Thread(target=_warm_loop, daemon=True).start()  # pre-calienta caché
        mcp.run(transport="sse")
    else:
        mcp.run()
