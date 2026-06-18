from config import mcp, MAX_LIMIT
from http_client import _request
from transforms import _slim_documento, _compact, _parse_periodo
from monitor import _monitor


@mcp.tool()
@_monitor
async def listar_documentos(
    fecha_inicio: str = None, fecha_fin: str = None,
    tipo_documento_id: int = None, cliente_id: int = None,
    limite: int = 25, pagina: int = 0,
) -> dict:
    """Lista documentos de venta (boletas/facturas) del más reciente al más antiguo.
    Fechas en lenguaje natural ('hoy', 'ayer', 'mes', 'mes_pasado', ...) o YYYY-MM-DD;
    sin fecha lista los más recientes.
    tipo_documento_id: obtener IDs con configuracion('tipos_documento')."""
    lim = min(max(1, limite), MAX_LIMIT)
    params: dict = {
        "limit": lim, "offset": max(0, pagina) * lim,
        "orderby": "emissiondate", "order": "DESC",
    }
    if tipo_documento_id: params["documenttypeid"] = tipo_documento_id
    if cliente_id:        params["clientid"]       = cliente_id
    ts_i, ts_f, _, _ = _parse_periodo(fecha_inicio, fecha_fin, por_defecto=None)
    if ts_i is not None:
        params["emissiondaterange"] = f"[{ts_i},{ts_f}]"
    data = await _request("GET", "documents.json", params=params)
    if "error" in data:
        return data
    return {"total": data.get("count", 0), "documentos": [_slim_documento(d) for d in data.get("items", [])]}


@mcp.tool()
@_monitor
async def detalle_documento(documento_id: int) -> dict:
    """Líneas de un documento: qué productos se vendieron y en qué cantidad."""
    if documento_id <= 0:
        return {"error": "documento_id debe ser positivo."}
    data = await _request("GET", f"documents/{documento_id}/details.json")
    if "error" in data:
        return data
    lineas = [
        _compact({
            "variante_id": (i.get("variant") or {}).get("id"),
            "producto":    i.get("comment", ""),
            "cantidad":    i.get("quantity"),
            "precio_unit": i.get("netUnitValue"),
            "total":       i.get("totalUnitValue"),
            "descuento":   i.get("discount"),
        })
        for i in data.get("items", [])
    ]
    return {"documento_id": documento_id, "total_lineas": len(lineas), "lineas": lineas}


@mcp.tool()
@_monitor
async def obtener_detalle_recurso(tipo: str, recurso_id: int) -> dict:
    """Detalle completo de un recurso. tipo: 'clients'|'products'|'documents'|'variants'"""
    if tipo not in ("clients", "products", "documents", "variants"):
        return {"error": "tipo inválido. Usa: clients, products, documents, variants"}
    if recurso_id <= 0:
        return {"error": "recurso_id debe ser positivo."}
    return _compact(await _request("GET", f"{tipo}/{recurso_id}.json"))
