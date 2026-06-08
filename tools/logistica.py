from config import mcp, MAX_LIMIT
from http_client import _request
from transforms import _slim_devolucion, _slim_despacho, _compact, _ts, _fecha
from monitor import _monitor


@mcp.tool()
@_monitor
async def listar_devoluciones(
    fecha_inicio: str = None, fecha_fin: str = None,
    sucursal_id: int = None, limite: int = 25,
) -> dict:
    """Lista devoluciones de un período. Fechas en YYYY-MM-DD."""
    params: dict = {"limit": min(max(1, limite), MAX_LIMIT), "offset": 0}
    if sucursal_id: params["officeid"] = sucursal_id
    try:
        if fecha_inicio: params["returndatestart"] = _ts(fecha_inicio)
        if fecha_fin:    params["returndateend"]   = _ts(fecha_fin) + 86399
    except ValueError:
        return {"error": "Formato de fecha inválido. Usa YYYY-MM-DD."}
    data = await _request("GET", "returns.json", params=params)
    if "error" in data:
        return data
    items = data.get("items") or (data if isinstance(data, list) else [])
    return {
        "total": data.get("count", len(items)) if isinstance(data, dict) else len(items),
        "devoluciones": [_slim_devolucion(d) for d in items],
    }


@mcp.tool()
@_monitor
async def listar_despachos(
    fecha_inicio: str = None, fecha_fin: str = None,
    sucursal_id: int = None, limite: int = 25,
) -> dict:
    """Despachos/envíos de un período. state: 0=pendiente, 1=despachado."""
    params: dict = {"limit": min(max(1, limite), MAX_LIMIT), "offset": 0}
    if sucursal_id: params["officeid"] = sucursal_id
    try:
        if fecha_inicio: params["shippingdatestart"] = _ts(fecha_inicio)
        if fecha_fin:    params["shippingdateend"]   = _ts(fecha_fin) + 86399
    except ValueError:
        return {"error": "Formato de fecha inválido. Usa YYYY-MM-DD."}
    data = await _request("GET", "shippings.json", params=params)
    if "error" in data:
        return data
    items = data.get("items") or (data if isinstance(data, list) else [])
    return {
        "total": data.get("count", len(items)) if isinstance(data, dict) else len(items),
        "despachos": [_slim_despacho(d) for d in items],
    }


@mcp.tool()
@_monitor
async def documentos_proveedor(
    fecha_inicio: str = None, rut_proveedor: str = None, limite: int = 25,
) -> dict:
    """Facturas de proveedores. fecha_inicio en YYYY-MM filtra por mes (ej: 2026-05)."""
    params: dict = {"limit": min(max(1, limite), MAX_LIMIT), "offset": 0}
    if rut_proveedor: params["clientcode"] = rut_proveedor.strip().upper()
    try:
        if fecha_inicio:
            d = fecha_inicio.strip()
            params["year"]  = int(d[:4])
            params["month"] = int(d[5:7])
    except (ValueError, IndexError):
        return {"error": "Formato de fecha inválido. Usa YYYY-MM-DD."}
    data = await _request("GET", "third_party_documents.json", params=params)
    if "error" in data:
        return data
    items = data.get("items") or (data if isinstance(data, list) else [])
    return {
        "total": data.get("count", len(items)) if isinstance(data, dict) else len(items),
        "documentos": [
            _compact({
                "id":        d.get("id"),
                "numero":    d.get("number"),
                "fecha":     _fecha(d.get("emissionDate")),
                "proveedor": d.get("clientName") or d.get("name"),
                "rut":       d.get("clientCode") or d.get("code"),
                "total":     d.get("totalAmount"),
                "estado":    d.get("state"),
            })
            for d in items
        ],
    }
