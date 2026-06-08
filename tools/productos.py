import difflib
from config import mcp, MAX_LIMIT
from http_client import _request
from transforms import _slim_producto, _compact
from domain import _get_products_index
from monitor import _monitor


@mcp.tool()
@_monitor
async def buscar_producto(consulta: str = None, limite: int = 10) -> dict:
    """Busca productos por nombre (exacto o aproximado). Sin consulta lista los primeros activos."""
    if consulta:
        data = await _request("GET", "products.json", params={
            "limit": min(limite, MAX_LIMIT), "state": 0, "search": consulta.strip(),
        })
        if "error" not in data and data.get("items"):
            return {"total": data.get("count", 0), "productos": [_slim_producto(p) for p in data["items"]]}
        cnt_data = await _request("GET", "products/count.json", params={"state": 0})
        total_productos = cnt_data.get("count", 0) if "error" not in cnt_data else 0
        index = await _get_products_index()
        q = consulta.lower().strip()
        matches = difflib.get_close_matches(q, list(index), n=limite, cutoff=0.4)
        if not matches:
            matches = [k for k in index if q in k][:limite]
        resultado = {"total": len(matches), "productos": [index[m] for m in matches]}
        if total_productos > 2000:
            resultado["aviso"] = f"Catálogo tiene {total_productos} productos. Búsqueda fuzzy cubre solo los primeros 2000."
        return resultado
    else:
        data = await _request("GET", "products.json", params={"limit": min(limite, MAX_LIMIT), "state": 0})
        if "error" in data:
            return data
        return {"total": data.get("count", 0), "productos": [_slim_producto(p) for p in data.get("items", [])]}


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
async def precio_variante(variante_id: int, lista_precio_id: int) -> dict:
    """Precio de una variante en una lista de precio.
    Usa configuracion('listas_precio') para obtener IDs de listas."""
    data = await _request("GET", f"price_lists/{lista_precio_id}/details.json",
                          params={"variantid": variante_id, "limit": 1})
    if "error" in data:
        return data
    items = data.get("items") or (data if isinstance(data, list) else [])
    if not items:
        return {"error": f"Variante {variante_id} no encontrada en lista {lista_precio_id}."}
    i     = items[0]
    neto  = float(i.get("variantValue") or i.get("value") or 0)
    bruto = round(neto * 1.19)
    return _compact({
        "variante_id":     variante_id,
        "lista_precio_id": lista_precio_id,
        "precio_neto":     round(neto),
        "precio_bruto":    bruto,
        "moneda":          "CLP",
    })


@mcp.tool()
@_monitor
async def costo_variante(variante_id: int, precio_venta: float = None) -> dict:
    """Costo promedio de una variante. Pasa precio_venta para calcular margen."""
    if variante_id <= 0:
        return {"error": "variante_id debe ser positivo."}
    data = await _request("GET", f"variants/{variante_id}/costs.json")
    if "error" in data:
        return data
    items = data.get("items") or (data if isinstance(data, list) else [data])
    costo = float((items[0] if items else data).get("cost") or
                  (items[0] if items else data).get("averageCost") or 0)
    result: dict = {"variante_id": variante_id, "costo_promedio": round(costo), "moneda": "CLP"}
    if precio_venta and precio_venta > 0:
        margen_neto = precio_venta - costo
        result["precio_venta"] = round(precio_venta)
        result["margen_neto"]  = round(margen_neto)
        result["margen_pct"]   = round((margen_neto / precio_venta) * 100, 1) if precio_venta else 0
    return _compact(result)
