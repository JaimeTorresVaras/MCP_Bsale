import time
import httpx
import contextvars
from typing import Optional
from config import BSALE_TOKEN, BASE_URL, TIMEOUT, MAX_LIMIT, MAX_PAGES, log

_ctx_api_calls: contextvars.ContextVar[list | None] = contextvars.ContextVar(
    "api_calls", default=None
)


def _headers() -> dict:
    if not BSALE_TOKEN:
        raise RuntimeError("BSALE_API_TOKEN no configurado en el entorno.")
    return {"access_token": BSALE_TOKEN, "Content-Type": "application/json"}


async def _request(
    method: str, endpoint: str,
    params: Optional[dict] = None, data: Optional[dict] = None,
) -> dict:
    url = f"{BASE_URL}/{endpoint}"
    clean_params = {k: v for k, v in (params or {}).items() if v is not None}
    log.info("→ %s %s %s", method, endpoint, clean_params)
    try:
        t_req = time.monotonic()
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            res = await client.request(
                method=method, url=url, headers=_headers(),
                params=clean_params, json=data,
            )
        elapsed_req = round((time.monotonic() - t_req) * 1000)
        log.info("← %s %s (%dms)", res.status_code, endpoint, elapsed_req)
        calls = _ctx_api_calls.get(None)
        if calls is not None:
            calls.append({"endpoint": endpoint, "method": method,
                          "status": res.status_code, "bytes": len(res.content), "ms": elapsed_req})
        if res.status_code == 401: return {"error": "Token inválido o expirado."}
        if res.status_code == 403: return {"error": "Sin permisos para este recurso."}
        if res.status_code == 404: return {"error": f"No encontrado: {endpoint}"}
        if res.status_code == 429: return {"error": "Rate limit alcanzado. Espera unos segundos."}
        res.raise_for_status()
        return res.json()
    except httpx.TimeoutException:
        return {"error": f"Timeout ({TIMEOUT}s) al conectar con Bsale."}
    except httpx.ConnectError:
        return {"error": "No se pudo conectar con api.bsale.cl."}
    except httpx.HTTPStatusError as e:
        return {"error": f"HTTP {e.response.status_code}: {e.response.text[:200]}"}
    except Exception as e:
        log.exception("Error inesperado en %s", endpoint)
        return {"error": f"Error inesperado: {e}"}


async def _paginar(endpoint: str, params: dict, max_registros: int = 1000) -> list:
    """Acumula todos los items paginando automáticamente."""
    items_total = []
    p = dict(params)
    p["limit"]  = MAX_LIMIT
    p["offset"] = 0
    pages = 0
    while pages < MAX_PAGES and len(items_total) < max_registros:
        data = await _request("GET", endpoint, params=p)
        if "error" in data:
            break
        items = data.get("items", [])
        if not items:
            break
        items_total.extend(items)
        if p["offset"] + MAX_LIMIT >= data.get("count", 0):
            break
        p["offset"] += MAX_LIMIT
        pages += 1
    return items_total
