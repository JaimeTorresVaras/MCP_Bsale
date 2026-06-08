import time
from config import mcp
from monitor import _STATS, _STATS_START


@mcp.tool()
async def estadisticas_mcp() -> dict:
    """Métricas de uso del servidor MCP acumuladas en memoria desde que arrancó el proceso.
    Muestra llamadas totales, errores, tiempo promedio y tokens estimados por tool."""
    uptime_s     = round(time.monotonic() - _STATS_START)
    total_calls  = sum(s["calls"]  for s in _STATS.values())
    total_errors = sum(s["errors"] for s in _STATS.values())

    por_tool = sorted(
        [
            {
                "tool":        name,
                "calls":       s["calls"],
                "errors":      s["errors"],
                "avg_ms":      round(s["total_ms"] / s["calls"]) if s["calls"] else 0,
                "tokens_est":  s["total_tokens"],
                "last_called": s["last_called"],
            }
            for name, s in _STATS.items()
        ],
        key=lambda x: x["calls"],
        reverse=True,
    )

    return {
        "uptime_s":     uptime_s,
        "total_calls":  total_calls,
        "total_errors": total_errors,
        "por_tool":     por_tool,
    }
