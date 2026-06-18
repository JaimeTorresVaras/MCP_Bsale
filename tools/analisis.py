from config import mcp
from transforms import _compact
from domain import (
    _buscar_productos, _variantes_de_producto, _costo_variante, _precio_neto,
    _lista_precio_default, _stock_variante, _agrupar_stocks, _nombres_de_productos,
    _en_lotes,
)
from monitor import _monitor


def _margen(neto: float, costo: float):
    """Devuelve (margen_$, margen_%) netos. (None, None) si falta precio o costo
    (costo 0 = no cargado en Bsale, no es 100% de margen)."""
    if not neto or costo <= 0:
        return None, None
    m = neto - costo
    return round(m), round(m / neto * 100, 1)


@mcp.tool()
@_monitor
async def analisis_producto(consulta: str, sucursal_id: int = None) -> dict:
    """Análisis completo de un producto: stock por sucursal, costo, precio, margen y capital invertido.
    Úsalo para 'analiza el vaso frozen', '¿cuánto margino en X?', '¿cuánto stock y a qué costo de X?'."""
    productos = await _buscar_productos(consulta, limite=5)
    if not productos:
        return {"nota": f"No se encontraron productos para '{consulta}'."}
    lista = await _lista_precio_default()

    async def _ver(v):
        vid = v.get("id")
        total, por_suc = await _stock_variante(vid, sucursal_id)
        c = await _costo_variante(vid)
        neto = await _precio_neto(vid, lista)
        costo = c["costo"]
        m, mpct = _margen(neto, costo)
        return {
            "fila": _compact({
                "variante_id":       vid,
                "sku":               v.get("code"),
                "stock":             round(total, 2),
                "costo_unitario":    round(costo) if costo else None,
                "precio_neto":       round(neto) if neto else None,
                "precio_bruto":      round(neto * 1.19) if neto else None,
                "margen_unitario":   m,
                "margen_pct":        mpct,
                "capital_invertido": round(total * costo),
                "por_sucursal":      por_suc or None,
            }),
            "stock": total, "capital": total * costo,
        }

    salida = []
    for p in productos:
        variantes = await _variantes_de_producto(p.get("id"))
        enr = await _en_lotes(_ver, variantes, batch=8)
        salida.append(_compact({
            "producto_id":       p.get("id"),
            "producto":          p.get("name"),
            "stock_total":       round(sum(e["stock"] for e in enr), 2),
            "capital_invertido": round(sum(e["capital"] for e in enr)),
            "variantes":         [e["fila"] for e in enr],
        }))
    return {"moneda": "CLP", "productos": salida}


@mcp.tool()
@_monitor
async def reposicion_sugerida(umbral: float = 5.0, limite: int = 20, sucursal_id: int = None) -> dict:
    """Qué reponer primero: productos con stock <= umbral, con costo, precio y margen,
    ordenados por margen (lo más rentable a reponer primero). Para '¿qué necesito reponer?'."""
    agrupado = await _agrupar_stocks(sucursal_id)
    if not agrupado:
        return {"error": "No se encontraron registros de stock."}
    bajos = sorted(
        ({"vid": vid, **info} for vid, info in agrupado.items() if info["stock"] <= umbral),
        key=lambda x: x["stock"],
    )
    candidatos = bajos[:max(1, limite)]
    nombres = await _nombres_de_productos({b.get("producto_id") for b in candidatos})
    lista = await _lista_precio_default()

    async def _fila(b):
        c = await _costo_variante(b["vid"])
        neto = await _precio_neto(b["vid"], lista)
        m, mpct = _margen(neto, c["costo"])
        pid = b.get("producto_id")
        return _compact({
            "producto":        nombres.get(int(pid)) if pid else b.get("nombre"),
            "sku":             b["sku"],
            "stock":           round(b["stock"], 2),
            "costo_unitario":  round(c["costo"]) if c["costo"] else None,
            "precio_neto":     round(neto) if neto else None,
            "margen_unitario": m,
            "margen_pct":      mpct,
        })

    filas = await _en_lotes(_fila, candidatos, batch=8)
    filas.sort(key=lambda x: x.get("margen_unitario") or 0, reverse=True)
    return {"umbral": umbral, "total_bajo_umbral": len(bajos), "moneda": "CLP", "sugerencias": filas}


@mcp.tool()
@_monitor
async def ranking_rentabilidad(consulta: str = None, orden: str = "mayor", limite: int = 10) -> dict:
    """Ranking de productos por margen %. Con 'consulta' analiza ese grupo (ej: 'vasos', 'peluches');
    sin consulta usa los productos con más stock. orden: 'mayor' | 'menor'."""
    lista = await _lista_precio_default()

    if consulta:
        productos = await _buscar_productos(consulta, limite=30)
        base = []
        for p in productos:
            vs = await _variantes_de_producto(p.get("id"))
            if vs:
                base.append((vs[0].get("id"), p.get("name"), vs[0].get("code")))
    else:
        agrupado = await _agrupar_stocks()
        top = sorted(agrupado.items(), key=lambda x: x[1]["stock"], reverse=True)[:30]
        nombres = await _nombres_de_productos({i.get("producto_id") for _, i in top})
        base = [(vid,
                 nombres.get(int(i["producto_id"])) if i.get("producto_id") else i["nombre"],
                 i["sku"]) for vid, i in top]

    async def _fila(item):
        vid, nombre, sku = item
        c = await _costo_variante(vid)
        neto = await _precio_neto(vid, lista)
        if not neto or c["costo"] <= 0:   # sin precio o sin costo cargado: no se puede rankear margen
            return None
        m, mpct = _margen(neto, c["costo"])
        return {"producto": nombre, "sku": sku, "costo": round(c["costo"]),
                "precio_neto": round(neto), "margen": m, "margen_pct": mpct}

    filas = [f for f in await _en_lotes(_fila, base, batch=8) if f]
    filas.sort(key=lambda x: x["margen_pct"], reverse=(orden != "menor"))
    return {"moneda": "CLP", "orden": orden, "analizados": len(filas), "ranking": filas[:max(1, limite)]}


@mcp.tool()
@_monitor
async def valorizacion_inventario(top: int = 20, sucursal_id: int = None) -> dict:
    """Dónde está tu capital: productos con más dinero invertido en stock (cantidad x costo).
    Para '¿cuánto vale mi inventario?', '¿dónde tengo la plata parada?'.
    Aproximado: analiza los de mayor cantidad de los primeros registros de inventario."""
    agrupado = await _agrupar_stocks(sucursal_id)
    if not agrupado:
        return {"error": "No se encontraron registros de stock."}
    candidatos = sorted(agrupado.items(), key=lambda x: x[1]["stock"], reverse=True)[:max(top * 3, 60)]
    nombres = await _nombres_de_productos({i.get("producto_id") for _, i in candidatos})

    costos = await _en_lotes(lambda par: _costo_variante(par[0]), candidatos, batch=8)
    filas, capital_total = [], 0.0
    for (vid, info), c in zip(candidatos, costos):
        cap = info["stock"] * c["costo"]
        capital_total += cap
        pid = info.get("producto_id")
        filas.append(_compact({
            "producto":       nombres.get(int(pid)) if pid else info["nombre"],
            "sku":            info["sku"],
            "stock":          round(info["stock"], 2),
            "costo_unitario": round(c["costo"]) if c["costo"] else None,
            "capital":        round(cap),
        }))
    filas.sort(key=lambda x: x["capital"], reverse=True)
    return {
        "moneda":            "CLP",
        "capital_analizado": round(capital_total),
        "nota":              "Aproximado: top por cantidad de los primeros ~1000 registros de inventario.",
        "top":               filas[:max(1, top)],
    }
