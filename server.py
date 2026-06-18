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


if __name__ == "__main__":
    log.info("Bsale MCP Server v4 iniciando... (transporte: %s)", TRANSPORT)
    if not BSALE_TOKEN:
        log.error("BSALE_API_TOKEN no configurado.")
        sys.exit(1)

    if TRANSPORT == "sse":
        log.info("Modo remoto SSE en %s:%s", SSE_HOST, SSE_PORT)
        mcp.run(transport="sse")
    else:
        mcp.run()
