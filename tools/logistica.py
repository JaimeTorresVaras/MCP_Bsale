from config import mcp, MAX_LIMIT
from http_client import _request
from transforms import _slim_devolucion, _slim_despacho, _compact, _fecha, _parse_periodo
from monitor import _monitor


@mcp.tool()
@_monitor
async def listar_devoluciones(
    fecha_inicio: str = None, fecha_fin: str = None,
    sucursal_id: int = None, limite: int = 25,
) -> dict:
    """Lista devoluciones de un período. Fechas en lenguaje natural ('hoy', 'mes',
    'mes_pasado', ...) o YYYY-MM-DD; sin fecha lista las más recientes."""
    params: dict = {"limit": min(max(1, limite), MAX_LIMIT), "offset": 0}
    if sucursal_id: params["officeid"] = sucursal_id
    ts_i, ts_f, _, _ = _parse_periodo(fecha_inicio, fecha_fin, por_defecto=None)
    if ts_i is not None:
        params["returndatestart"] = ts_i
        params["returndateend"]   = ts_f
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
    """Despachos/envíos de un período. state: 0=pendiente, 1=despachado.
    Fechas en lenguaje natural o YYYY-MM-DD; sin fecha lista los más recientes."""
    params: dict = {"limit": min(max(1, limite), MAX_LIMIT), "offset": 0}
    if sucursal_id: params["officeid"] = sucursal_id
    ts_i, ts_f, _, _ = _parse_periodo(fecha_inicio, fecha_fin, por_defecto=None)
    if ts_i is not None:
        params["shippingdatestart"] = ts_i
        params["shippingdateend"]   = ts_f
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
    """Facturas de proveedores de un mes. fecha_inicio acepta 'mes', 'mes_pasado',
    YYYY-MM o YYYY-MM-DD (se usa su mes). rut_proveedor para filtrar uno."""
    params: dict = {"limit": min(max(1, limite), MAX_LIMIT), "offset": 0}
    if rut_proveedor: params["clientcode"] = rut_proveedor.strip().upper()
    _, _, desde, _ = _parse_periodo(fecha_inicio, None, por_defecto=None)
    if desde:
        params["year"]  = int(desde[:4])
        params["month"] = int(desde[5:7])
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
