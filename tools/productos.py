from config import mcp, MAX_LIMIT
from http_client import _request
from transforms import _slim_producto, _compact
from domain import _buscar_productos, _costo_variante, _precio_neto, _lista_precio_default
from monitor import _monitor


@mcp.tool()
@_monitor
async def buscar_producto(consulta: str = None, limite: int = 10) -> dict:
    """Busca productos por nombre. Coincidencia parcial e insensible a mayúsculas
    sobre todo el catálogo; admite varias palabras en cualquier orden
    (ej: 'vasos frozen'). Sin consulta lista los primeros activos."""
    lim = min(max(1, limite), MAX_LIMIT)
    if not consulta:
        data = await _request("GET", "products.json", params={"limit": lim, "state": 0})
        if "error" in data:
            return data
        return {"total": data.get("count", 0),
                "productos": [_slim_producto(p) for p in data.get("items", [])]}

    items = await _buscar_productos(consulta, lim)
    if not items:
        return {"total": 0, "productos": [],
                "nota": f"No se encontraron productos para '{consulta}'."}
    return {"total": len(items), "productos": [_slim_producto(p) for p in items]}


@mcp.tool()
@_monitor
async def buscar_variante(consulta: str, por: str = "codigo") -> dict:
    """Busca variantes por código de barras, SKU o descripción.
    por: 'barcode'|'codigo'|'serial'|'descripcion'"""
    mapa = {"barcode": "barcode", "codigo": "code", "serial": "serialnumber", "descripcion": "description"}
    campo = mapa.get(por, "code")
    data = await _request("GET", "variants.json", params={campo: consulta.strip(), "limit": 10})
    if "error" in data:
        return data
    items = data.get("items") or (data if isinstance(data, list) else [])
    return {
        "total": data.get("count", len(items)) if isinstance(data, dict) else len(items),
        "variantes": [
            _compact({
                "variante_id": v.get("id"),
                "desc":        v.get("description"),
                "sku":         v.get("code"),
                "barcode":     v.get("barCode"),
                "producto_id": (v.get("product") or {}).get("id"),
            })
            for v in items
        ],
    }


@mcp.tool()
@_monitor
async def precio_variante(variante_id: int, lista_precio_id: int = None) -> dict:
    """Precio de venta de una variante (neto y bruto con IVA). Para '¿a cuánto vendo X?'.
    Si no indicas lista_precio_id usa la primera lista activa
    (ver configuracion('listas_precio') para elegir otra)."""
    lista_precio_id = lista_precio_id or await _lista_precio_default()
    if not lista_precio_id:
        return {"error": "No se encontró una lista de precio activa."}
    neto = await _precio_neto(variante_id, lista_precio_id)
    if not neto:
        return {"error": f"Variante {variante_id} sin precio en lista {lista_precio_id}."}
    return _compact({
        "variante_id":     variante_id,
        "lista_precio_id": lista_precio_id,
        "precio_neto":     round(neto),
        "precio_bruto":    round(neto * 1.19),
        "moneda":          "CLP",
    })


@mcp.tool()
@_monitor
async def costo_variante(variante_id: int, precio_venta: float = None) -> dict:
    """Costo, valorización y margen de una variante. Para '¿cuánto me cuesta / cuánto margino en X?'.
    Devuelve costo promedio unitario, capital valorizado en inventario, y margen $ y %
    (si no pasas precio_venta neto, lo obtiene de la lista de precio por defecto)."""
    if variante_id <= 0:
        return {"error": "variante_id debe ser positivo."}
    c = await _costo_variante(variante_id)
    costo = c["costo"]
    result: dict = {
        "variante_id":           variante_id,
        "costo_promedio":        round(costo),
        "valorizado_inventario": round(c["valorizado"]),
        "moneda":                "CLP",
    }
    if not precio_venta:
        precio_venta = await _precio_neto(variante_id)
    if precio_venta and precio_venta > 0:
        result["precio_venta_neto"] = round(precio_venta)
    if costo > 0 and precio_venta and precio_venta > 0:
        margen = precio_venta - costo
        result["margen_neto"] = round(margen)
        result["margen_pct"]  = round(margen / precio_venta * 100, 1)
    elif costo <= 0:
        result["nota"] = "Sin costo registrado en Bsale para esta variante."
    return _compact(result)
