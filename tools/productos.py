import difflib
from config import mcp, MAX_LIMIT
from http_client import _request, _paginar
from transforms import _slim_producto, _compact
from domain import _get_products_index
from monitor import _monitor


def _stem(palabra: str) -> str:
    """Plural simple a singular para tolerar 'vasos' -> 'vaso'."""
    return palabra[:-1] if palabra.endswith("s") and len(palabra) > 3 else palabra


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

    async def _por_nombre(term: str, n: int) -> tuple[list, int]:
        d = await _request("GET", "products.json",
                           params={"limit": min(n, MAX_LIMIT), "state": 0, "name": term})
        if "error" in d:
            return [], 0
        return d.get("items", []), d.get("count", 0)

    q = consulta.strip()
    tokens = [_stem(t) for t in q.lower().split() if len(t) >= 3]

    if len(tokens) <= 1:
        items, count = await _por_nombre(q, lim)
    else:
        # Filtra por el token más selectivo en el servidor y exige (AND) que el
        # resto de las palabras aparezcan en el nombre, sin importar el orden.
        principal = max(tokens, key=len)
        candidatos = await _paginar("products.json", {"state": 0, "name": principal},
                                    max_registros=300)
        items = [p for p in candidatos
                 if all(t in (p.get("name") or "").lower() for t in tokens)]
        count = len(items)
        if not items:  # la frase puede venir contigua en otro punto del nombre
            items, count = await _por_nombre(q, lim)

    if items:
        return {"total": count, "mostrados": len(items[:lim]),
                "productos": [_slim_producto(p) for p in items[:lim]]}

    # Último recurso: índice aproximado para errores de tipeo (catálogo parcial).
    index = await _get_products_index()
    matches = difflib.get_close_matches(q.lower(), list(index), n=lim, cutoff=0.6)
    if matches:
        return {"total": len(matches),
                "productos": [index[m] for m in matches],
                "nota": "Sin coincidencia exacta; resultados aproximados."}
    return {"total": 0, "productos": [],
            "nota": f"No se encontraron productos para '{consulta}'."}


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
    if not lista_precio_id:
        pls = await _request("GET", "price_lists.json", params={"limit": 50})
        activas = [p for p in pls.get("items", []) if p.get("state") == 0] if "error" not in pls else []
        if not activas:
            return {"error": "No se encontró una lista de precio activa."}
        lista_precio_id = activas[0]["id"]
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
