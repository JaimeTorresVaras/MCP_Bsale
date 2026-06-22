from config import mcp
from transforms import _compact, _parse_periodo
from domain import (
    _buscar_productos, _variantes_de_producto, _costo_variante, _precio_neto,
    _lista_precio_default, _stock_variante, _agrupar_stocks, _nombres_de_productos,
    _ventas_por_variante, _resumen_documentos, _nombres_de_clientes, _info_variantes,
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
async def ventas_producto(consulta: str, fecha_inicio: str = None, fecha_fin: str = None) -> dict:
    """Unidades vendidas, ingreso, margen y sucursales de un producto en un período.
    Para '¿cuánto vendí de X este año?', '¿cuánto marginé en X?', '¿dónde se vendió X?'.
    Período en lenguaje natural (hoy/mes/mes_pasado/año/ultimos_30...) o YYYY-MM-DD;
    sin fecha usa el año en curso. La primera consulta de un período largo puede tardar
    ~30s (escanea los documentos); luego queda en caché. Margen aproximado (costo promedio actual)."""
    ts_i, ts_f, desde, hasta = _parse_periodo(fecha_inicio, fecha_fin, por_defecto="anio")
    productos = await _buscar_productos(consulta, limite=5)
    if not productos:
        return {"nota": f"No se encontraron productos para '{consulta}'."}
    ventas = await _ventas_por_variante(ts_i, ts_f)

    async def _analizar(p):
        variantes = await _variantes_de_producto(p["id"])
        unidades = ingreso = costo_total = 0.0
        por_suc: dict = {}
        por_tipo: dict = {}
        for v in variantes:
            vd = ventas.get(int(v["id"]))
            if not vd:
                continue
            unidades += vd["cantidad"]
            ingreso  += vd["ingreso"]
            c = await _costo_variante(v["id"])
            costo_total += c["costo"] * vd["cantidad"]
            for s, q in vd["por_sucursal"].items():
                por_suc[s] = por_suc.get(s, 0.0) + q
            for t, tv in vd.get("por_tipo", {}).items():
                acc = por_tipo.setdefault(t, {"cantidad": 0.0, "ingreso": 0.0})
                acc["cantidad"] += tv["cantidad"]
                acc["ingreso"]  += tv["ingreso"]
        margen = ingreso - costo_total
        return _compact({
            "producto_id":       p["id"],
            "producto":          p.get("name"),
            "unidades_vendidas": round(unidades, 2),
            "ingreso_neto":      round(ingreso),
            "margen_neto":       round(margen) if costo_total else None,
            "margen_pct":        round(margen / ingreso * 100, 1) if ingreso and costo_total else None,
            "por_sucursal":      [{"sucursal": s, "unidades": round(q, 2)}
                                  for s, q in sorted(por_suc.items(), key=lambda x: -x[1])] or None,
            "por_tipo_documento": [{"tipo": t, "unidades": round(tv["cantidad"], 2),
                                    "ingreso": round(tv["ingreso"]),
                                    "precio_unit": round(tv["ingreso"] / tv["cantidad"]) if tv["cantidad"] else None}
                                   for t, tv in sorted(por_tipo.items(), key=lambda x: -x[1]["cantidad"])] or None,
        })

    resultado = await _en_lotes(_analizar, productos, batch=5)
    return {"periodo": {"desde": desde, "hasta": hasta}, "moneda": "CLP", "productos": resultado}


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


@mcp.tool()
@_monitor
async def top_productos_vendidos(fecha_inicio: str = None, fecha_fin: str = None,
                                 por: str = "unidades", limite: int = 15) -> dict:
    """Ranking de los productos MÁS VENDIDOS en un período. por: 'unidades' | 'ingreso'.
    Para '¿qué se vendió más este mes?', 'top/lo más vendido', 'productos estrella'.
    Período en lenguaje natural (hoy/mes/mes_pasado/año/...) o YYYY-MM-DD; sin fecha usa el mes en curso.
    La 1ª consulta de un período largo puede tardar (~30-60s); luego usa caché."""
    ts_i, ts_f, desde, hasta = _parse_periodo(fecha_inicio, fecha_fin, por_defecto="mes")
    por_variante = (await _resumen_documentos(ts_i, ts_f))["por_variante"]
    if not por_variante:
        return {"periodo": {"desde": desde, "hasta": hasta}, "ranking": []}
    clave = "ingreso" if por == "ingreso" else "cantidad"
    top = sorted(por_variante.items(), key=lambda x: x[1][clave], reverse=True)[:max(1, limite)]
    info = await _info_variantes([vid for vid, _ in top])
    return {
        "periodo":  {"desde": desde, "hasta": hasta},
        "orden_por": por, "moneda": "CLP",
        "ranking": [
            _compact({
                "ranking":           i + 1,
                "producto":          (info.get(vid) or {}).get("producto") or f"Variante {vid}",
                "sku":               (info.get(vid) or {}).get("sku"),
                "unidades_vendidas": round(v["cantidad"], 2),
                "ingreso_neto":      round(v["ingreso"]),
            })
            for i, (vid, v) in enumerate(top)
        ],
    }


@mcp.tool()
@_monitor
async def mejores_clientes(fecha_inicio: str = None, fecha_fin: str = None, limite: int = 15) -> dict:
    """Ranking de clientes por monto comprado en un período (lo que pagaron, con IVA).
    Para '¿quiénes son mis mejores clientes?', 'clientes que más compran'.
    Período en lenguaje natural o YYYY-MM-DD; sin fecha usa el año en curso."""
    ts_i, ts_f, desde, hasta = _parse_periodo(fecha_inicio, fecha_fin, por_defecto="anio")
    por_cliente = (await _resumen_documentos(ts_i, ts_f))["por_cliente"]
    if not por_cliente:
        return {"periodo": {"desde": desde, "hasta": hasta}, "clientes": []}
    top = sorted(por_cliente.items(), key=lambda x: x[1]["total"], reverse=True)[:max(1, limite)]
    nombres = await _nombres_de_clientes([cid for cid, _ in top])
    return {
        "periodo": {"desde": desde, "hasta": hasta}, "moneda": "CLP",
        "clientes": [
            _compact({
                "cliente":        (nombres.get(cid) or {}).get("nombre") or f"Cliente {cid}",
                "rut":            (nombres.get(cid) or {}).get("rut"),
                "total_comprado": round(info["total"]),
                "compras":        info["docs"],
            })
            for cid, info in top
        ],
    }


@mcp.tool()
@_monitor
async def productos_sin_movimiento(fecha_inicio: str = None, fecha_fin: str = None, limite: int = 30) -> dict:
    """Productos con stock que NO se vendieron en el período (dead stock / capital inmovilizado).
    Para '¿qué tengo en stock que no se vende?', 'productos sin rotación', 'capital parado'.
    Período en lenguaje natural o YYYY-MM-DD; sin fecha usa el año en curso."""
    ts_i, ts_f, desde, hasta = _parse_periodo(fecha_inicio, fecha_fin, por_defecto="anio")
    agrupado = await _agrupar_stocks()
    if not agrupado:
        return {"error": "No se encontraron registros de stock."}
    vendidos = (await _resumen_documentos(ts_i, ts_f))["por_variante"]
    sin_venta = [{"vid": vid, **info} for vid, info in agrupado.items()
                 if info["stock"] > 0 and vendidos.get(vid, {}).get("cantidad", 0) == 0]
    sin_venta.sort(key=lambda x: x["stock"], reverse=True)
    candidatos = sin_venta[:max(limite * 4, 80)]   # acota llamadas de costo
    costos = await _en_lotes(lambda x: _costo_variante(x["vid"]), candidatos, batch=10)
    for item, c in zip(candidatos, costos):
        item["capital"] = item["stock"] * c["costo"]
    candidatos.sort(key=lambda x: x["capital"], reverse=True)
    top = candidatos[:max(1, limite)]
    nombres = await _nombres_de_productos({x.get("producto_id") for x in top})
    return {
        "periodo": {"desde": desde, "hasta": hasta}, "moneda": "CLP",
        "total_sin_movimiento": len(sin_venta),
        "productos": [
            _compact({
                "producto":             nombres.get(int(x["producto_id"])) if x.get("producto_id") else x.get("nombre"),
                "sku":                  x["sku"],
                "stock":                round(x["stock"], 2),
                "capital_inmovilizado": round(x["capital"]),
            })
            for x in top
        ],
    }


@mcp.tool()
@_monitor
async def margen_periodo(fecha_inicio: str = None, fecha_fin: str = None) -> dict:
    """Margen bruto estimado del período: ingreso − costo de lo vendido (COGS).
    Para '¿cuánto margen/ganancia dejé este mes?', 'rentabilidad del período'.
    El COGS se calcula sobre los productos que más facturan e informa el % de ventas cubierto (aprox honesta).
    Período en lenguaje natural o YYYY-MM-DD; sin fecha usa el mes en curso."""
    ts_i, ts_f, desde, hasta = _parse_periodo(fecha_inicio, fecha_fin, por_defecto="mes")
    por_variante = (await _resumen_documentos(ts_i, ts_f))["por_variante"]
    if not por_variante:
        return {"periodo": {"desde": desde, "hasta": hasta}, "ingreso_neto": 0, "nota": "Sin ventas en el período."}
    ingreso_total = sum(v["ingreso"] for v in por_variante.values())
    top = sorted(por_variante.items(), key=lambda x: x[1]["ingreso"], reverse=True)[:200]
    costos = await _en_lotes(lambda kv: _costo_variante(kv[0]), top, batch=10)
    cogs = ingreso_cubierto = 0.0
    for (vid, v), c in zip(top, costos):
        cogs += c["costo"] * v["cantidad"]
        ingreso_cubierto += v["ingreso"]
    margen = ingreso_cubierto - cogs
    return _compact({
        "periodo": {"desde": desde, "hasta": hasta}, "moneda": "CLP",
        "ingreso_neto_total":       round(ingreso_total),
        "ingreso_analizado":        round(ingreso_cubierto),
        "cobertura_analisis_pct":   round(ingreso_cubierto / ingreso_total * 100, 1) if ingreso_total else 0,
        "costo_productos_vendidos": round(cogs),
        "margen_bruto":             round(margen),
        "margen_pct":               round(margen / ingreso_cubierto * 100, 1) if ingreso_cubierto else None,
        "nota": "Margen sobre los productos top por ingreso (ver cobertura_analisis_pct); costo promedio aprox.",
    })
