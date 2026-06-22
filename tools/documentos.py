from config import mcp, MAX_LIMIT
from http_client import _request
from transforms import _slim_documento, _compact, _parse_periodo, _fecha
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


@mcp.tool()
@_monitor
async def buscar_documento(numero: int, tipo_documento_id: int = None) -> dict:
    """Busca un documento por su NÚMERO (boleta/factura). Para 'muéstrame la boleta N° 12345'.
    Un mismo número puede existir en varios tipos; usa tipo_documento_id para acotar
    (ver configuracion('tipos_documento')). Devuelve cada documento con sus líneas."""
    params: dict = {"number": numero, "limit": 10,
                    "expand": "[details,document_type,office,client]"}
    if tipo_documento_id:
        params["documenttypeid"] = tipo_documento_id
    data = await _request("GET", "documents.json", params=params)
    if "error" in data:
        return data
    docs = data.get("items", [])
    if not docs:
        return {"nota": f"No se encontró documento con número {numero}."}

    resultado = []
    for d in docs:
        cl = d.get("client") or {}
        cliente = f"{cl.get('firstName','')} {cl.get('lastName','')}".strip() or cl.get("company")
        resultado.append(_compact({
            "id":       d.get("id"),
            "numero":   d.get("number"),
            "tipo":     (d.get("document_type") or {}).get("name"),
            "fecha":    _fecha(d.get("emissionDate")),
            "cliente":  cliente,
            "rut":      cl.get("code"),
            "sucursal": (d.get("office") or {}).get("name"),
            "neto":     d.get("netAmount"),
            "total":    d.get("totalAmount"),
            "lineas": [
                _compact({
                    "producto":    li.get("note") or (li.get("variant") or {}).get("description"),
                    "variante_id": (li.get("variant") or {}).get("id"),
                    "cantidad":    li.get("quantity"),
                    "precio_unit": li.get("netUnitValue"),
                    "total_neto":  li.get("netAmount"),
                })
                for li in ((d.get("details") or {}).get("items") or [])
            ],
        }))
    return {"total": len(resultado), "documentos": resultado}
