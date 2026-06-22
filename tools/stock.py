from config import mcp, MAX_LIMIT
from http_client import _request
from transforms import _slim_stock, _compact
from domain import _agrupar_stocks, _nombres_de_productos, _stock_variante
from monitor import _monitor


@mcp.tool()
@_monitor
async def consultar_stock(variante_id: int = None, producto_id: int = None,
                          sucursal_id: int = None, limite: int = 10) -> dict:
    """Stock disponible, con nombre de variante y sucursal (omite sucursales en 0).
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
            sub, por_suc = await _stock_variante(var.get("id"), sucursal_id)
            total += sub
            detalle.append(_compact({
                "variante_id":  var.get("id"),
                "sku":          var.get("code"),
                "stock":        round(sub, 2),
                "por_sucursal": por_suc or None,
            }))
        return _compact({
            "producto_id": producto_id,
            "producto":    prod.get("name"),
            "stock_total": round(total, 2),
            "variantes":   detalle,
        })

    params: dict = {"limit": min(max(1, limite), MAX_LIMIT), "offset": 0, "expand": "[variant,office]"}
    if variante_id: params["variantid"] = variante_id
    if sucursal_id: params["officeid"]  = sucursal_id
    data = await _request("GET", "stocks.json", params=params)
    if "error" in data:
        return data
    inventario = [_slim_stock(s) for s in data.get("items", []) if float(s.get("quantity") or 0)]
    return {"total": data.get("count", 0), "mostrados": len(inventario), "inventario": inventario}


@mcp.tool()
@_monitor
async def top_stock(top: int = 10, sucursal_id: int = None) -> dict:
    """Ranking de productos con más stock (mayor inventario disponible). Incluye nombre y SKU."""
    agrupado = await _agrupar_stocks(sucursal_id)
    if not agrupado:
        return {"error": "No se encontraron registros de stock."}
    ranking = sorted(agrupado.items(), key=lambda x: x[1]["stock"], reverse=True)[:max(1, top)]
    nombres = await _nombres_de_productos({info.get("producto_id") for _, info in ranking})
    return {
        "total_variantes": len(agrupado),
        "filtro_sucursal": sucursal_id,
        "top": [
            _compact({
                "ranking":     i + 1,
                "variante_id": vid,
                "producto":    nombres.get(int(info["producto_id"])) if info.get("producto_id") else info["nombre"],
                "sku":         info["sku"],
                "stock":       round(info["stock"], 2),
            })
            for i, (vid, info) in enumerate(ranking)
        ],
    }


@mcp.tool()
@_monitor
async def analizar_stock_critico(umbral: float = 5.0, sucursal_id: int = None, limite: int = 20) -> dict:
    """Productos con stock <= umbral que requieren reposición. Incluye nombre y SKU."""
    agrupado = await _agrupar_stocks(sucursal_id)
    if not agrupado:
        return {"error": "No se encontraron registros de stock."}
    bajos = sorted(
        [{"variante_id": vid, "producto_id": info.get("producto_id"),
          "sku": info["sku"], "stock": round(info["stock"], 2)}
         for vid, info in agrupado.items() if info["stock"] <= umbral],
        key=lambda x: x["stock"],
    )
    top = bajos[:max(1, limite)]
    nombres = await _nombres_de_productos({b["producto_id"] for b in top})
    criticos = [
        _compact({
            "variante_id": b["variante_id"],
            "producto":    nombres.get(int(b["producto_id"])) if b.get("producto_id") else None,
            "sku":         b["sku"],
            "stock":       b["stock"],
        })
        for b in top
    ]
    return {"umbral": umbral, "total_criticos": len(bajos), "skus_criticos": criticos}
