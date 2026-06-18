from config import mcp, MAX_LIMIT
from http_client import _request
from transforms import _slim_stock, _compact
from domain import _agrupar_stocks
from monitor import _monitor


@mcp.tool()
@_monitor
async def consultar_stock(variante_id: int = None, producto_id: int = None,
                          sucursal_id: int = None) -> dict:
    """Stock disponible, con nombre de variante y sucursal.
    - producto_id: suma el stock de todas las variantes del producto (úsalo tras
      buscar_producto para responder '¿cuánto stock queda de X?').
    - variante_id: stock de una variante puntual.
    - sucursal_id: limita a una sucursal."""
    if producto_id:
        prod = await _request("GET", f"products/{producto_id}.json")
        if "error" in prod:
            return prod
        vs = await _request("GET", f"products/{producto_id}/variants.json")
        if "error" in vs:
            return vs
        detalle, total = [], 0.0
        for var in vs.get("items", []):
            p: dict = {"variantid": var.get("id"), "expand": "[office]", "limit": MAX_LIMIT}
            if sucursal_id: p["officeid"] = sucursal_id
            rows = (await _request("GET", "stocks.json", params=p)).get("items", [])
            sub = sum(float(r.get("quantity") or 0) for r in rows)
            total += sub
            detalle.append(_compact({
                "variante_id":  var.get("id"),
                "sku":          var.get("code"),
                "stock":        round(sub, 2),
                "por_sucursal": [{"sucursal": (r.get("office") or {}).get("name"),
                                  "stock": r.get("quantity")} for r in rows] or None,
            }))
        return _compact({
            "producto_id": producto_id,
            "producto":    prod.get("name"),
            "stock_total": round(total, 2),
            "variantes":   detalle,
        })

    params: dict = {"limit": MAX_LIMIT, "offset": 0, "expand": "[variant,office]"}
    if variante_id: params["variantid"] = variante_id
    if sucursal_id: params["officeid"]  = sucursal_id
    data = await _request("GET", "stocks.json", params=params)
    if "error" in data:
        return data
    return {"total": data.get("count", 0), "inventario": [_slim_stock(s) for s in data.get("items", [])]}


@mcp.tool()
@_monitor
async def top_stock(top: int = 10, sucursal_id: int = None) -> dict:
    """Ranking de variantes con más stock. Nombre y SKU extraídos del inventario sin llamadas extra."""
    agrupado = await _agrupar_stocks(sucursal_id)
    if not agrupado:
        return {"error": "No se encontraron registros de stock."}
    ranking = sorted(agrupado.items(), key=lambda x: x[1]["stock"], reverse=True)[:max(1, top)]
    return {
        "total_variantes": len(agrupado),
        "filtro_sucursal": sucursal_id,
        "top": [
            {"ranking": i+1, "variante_id": vid, "nombre": info["nombre"],
             "sku": info["sku"], "stock": round(info["stock"], 2)}
            for i, (vid, info) in enumerate(ranking)
        ],
    }


@mcp.tool()
@_monitor
async def analizar_stock_critico(umbral: float = 5.0, sucursal_id: int = None) -> dict:
    """SKUs con stock <= umbral que requieren reposición."""
    agrupado = await _agrupar_stocks(sucursal_id)
    if not agrupado:
        return {"error": "No se encontraron registros de stock."}
    bajos = sorted(
        [{"variante_id": vid, "nombre": info["nombre"], "sku": info["sku"],
          "stock": round(info["stock"], 2)}
         for vid, info in agrupado.items() if info["stock"] <= umbral],
        key=lambda x: x["stock"],
    )
    return {"umbral": umbral, "total_criticos": len(bajos), "skus_criticos": bajos[:50]}
