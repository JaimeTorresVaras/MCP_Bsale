import asyncio
from config import mcp
from http_client import _request, _paginar
from transforms import _compact, _fecha, _parse_periodo
from domain import _fetch_sellers
from monitor import _monitor


@mcp.tool()
@_monitor
async def resumen_ventas(
    fecha_inicio: str = None, fecha_fin: str = None, tipo_documento_id: int = None,
) -> dict:
    """¿Cuánto se vendió? Totales neto/IVA/bruto del período con desglose por tipo de documento.
    Acepta lenguaje natural ('hoy', 'ayer', 'semana', 'mes', 'mes_pasado', 'año', 'ultimos_30')
    o fechas YYYY-MM-DD. Sin fechas usa el mes en curso.
    tipo_documento_id: filtrar por tipo (ver configuracion)."""
    ts_inicio, ts_fin, desde, hasta = _parse_periodo(fecha_inicio, fecha_fin)

    params: dict = {
        "emissiondaterange": f"[{ts_inicio},{ts_fin}]",
        "perdocument":       1,
    }
    if tipo_documento_id:
        params["documenttypeid"] = tipo_documento_id

    data = await _request("GET", "documents/summary.json", params=params)
    if "error" in data:
        return data

    if isinstance(data, list):
        items       = data
        bsale_count = sum(int(i.get("count", 0) or 0) for i in items)
    else:
        items       = data.get("items") or ([data] if data.get("totalAmount") is not None else [])
        bsale_count = data.get("count") or sum(int(i.get("count", 0) or 0) for i in items)

    total_neto  = sum(float(i.get("totalNetAmount", 0) or 0) for i in items)
    total_iva   = sum(float(i.get("totalTaxAmount", 0) or 0) for i in items)
    total_bruto = sum(float(i.get("totalAmount",    0) or 0) for i in items)
    total_docs  = sum(int(i.get("count",            0) or 0) for i in items)

    por_tipo = {}
    for i in items:
        tipo = (i.get("documentType") or {}).get("name") or i.get("documentTypeName") or "Sin tipo"
        por_tipo[tipo] = {
            "cantidad": int(i.get("count", 0) or 0),
            "total":    round(float(i.get("totalAmount", 0) or 0)),
        }

    return {
        "periodo":             {"desde": desde, "hasta": hasta},
        "bsale_count":         bsale_count,
        "documentos_emitidos": total_docs,
        "financiero": {
            "neto":        round(total_neto),
            "iva":         round(total_iva),
            "total_bruto": round(total_bruto),
            "moneda":      "CLP",
        },
        "por_tipo_documento": por_tipo,
    }


@mcp.tool()
@_monitor
async def resumen_pagos(
    fecha_inicio: str = None, fecha_fin: str = None, sucursal_id: int = None,
) -> dict:
    """¿Cómo pagaron? Desglose por medio de pago (efectivo, tarjeta, etc.) por fecha de emisión.
    Acepta lenguaje natural ('hoy', 'mes', 'mes_pasado', ...) o YYYY-MM-DD; sin fechas, mes en curso.
    Usa sucursal_id para acotar. Sin sucursal analiza hasta 100 documentos."""
    ts_inicio, ts_fin, desde, hasta = _parse_periodo(fecha_inicio, fecha_fin)

    params_docs: dict = {"emissiondaterange": f"[{ts_inicio},{ts_fin}]"}
    if sucursal_id:
        params_docs["officeid"] = sucursal_id

    max_docs = 200 if sucursal_id else 100
    docs = await _paginar("documents.json", params_docs, max_registros=max_docs)

    if not docs:
        return _compact({"periodo": {"desde": desde, "hasta": hasta},
                         "total_bruto": 0, "moneda": "CLP", "por_medio_pago": {}})

    async def _pagos_doc(doc_id: int) -> list:
        data = await _request("GET", f"documents/{doc_id}/payments.json")
        return data.get("items") or [] if "error" not in data else []

    doc_ids = [d["id"] for d in docs if d.get("id")]
    todas_pagos: list = []
    for i in range(0, len(doc_ids), 10):
        lote = await asyncio.gather(*[_pagos_doc(did) for did in doc_ids[i:i+10]])
        for items in lote:
            todas_pagos.extend(items)

    por_medio: dict = {}
    total_bruto = 0.0
    for p in todas_pagos:
        pt     = p.get("paymentType") or {}
        nombre = pt.get("name") or "Sin clasificar"
        monto  = float(p.get("amount") or 0)
        por_medio[nombre] = por_medio.get(nombre, 0.0) + monto
        total_bruto += monto

    return _compact({
        "periodo":               {"desde": desde, "hasta": hasta},
        "documentos_analizados": len(docs),
        "total_bruto":           round(total_bruto),
        "moneda":                "CLP",
        "por_medio_pago": {
            k: round(v)
            for k, v in sorted(por_medio.items(), key=lambda x: x[1], reverse=True)
        },
    })


@mcp.tool()
@_monitor
async def ranking_vendedores(fecha_inicio: str = None, fecha_fin: str = None) -> dict:
    """¿Quién vendió más? Ventas por vendedor con canal y sucursal. 1 llamada a Bsale.
    Acepta lenguaje natural ('hoy', 'mes', 'mes_pasado', 'año', ...) o YYYY-MM-DD;
    sin fechas usa el mes en curso."""
    ts_inicio, ts_fin, desde, hasta = _parse_periodo(fecha_inicio, fecha_fin)

    vendedores = await _fetch_sellers(ts_inicio, ts_fin)
    if isinstance(vendedores, dict) and "error" in vendedores:
        return vendedores

    return {
        "periodo":    {"desde": desde, "hasta": hasta},
        "total":      sum(v.get("ventas", 0) for v in vendedores),
        "moneda":     "CLP",
        "vendedores": vendedores,
    }


@mcp.tool()
@_monitor
async def resumen_por_canal(fecha_inicio: str = None, fecha_fin: str = None) -> dict:
    """¿Cuánto vendió cada canal? Ventas agrupadas por canal (Tienda / Internet / B2B / Widit)
    con participación porcentual. 1 llamada a Bsale.
    Acepta lenguaje natural o YYYY-MM-DD; sin fechas usa el mes en curso."""
    ts_inicio, ts_fin, desde, hasta = _parse_periodo(fecha_inicio, fecha_fin)

    vendedores = await _fetch_sellers(ts_inicio, ts_fin)
    if isinstance(vendedores, dict) and "error" in vendedores:
        return vendedores

    canales: dict[str, float] = {}
    for v in vendedores:
        canal = v.get("canal", "Desconocido")
        canales[canal] = canales.get(canal, 0.0) + v.get("ventas", 0)

    total   = sum(canales.values()) or 1
    desglose = sorted(
        [
            {
                "canal":         canal,
                "ventas":        round(monto),
                "participacion": round(monto / total * 100, 1),
            }
            for canal, monto in canales.items()
        ],
        key=lambda x: x["ventas"],
        reverse=True,
    )

    return {
        "periodo":   {"desde": desde, "hasta": hasta},
        "total":     round(total),
        "moneda":    "CLP",
        "por_canal": desglose,
    }


@mcp.tool()
@_monitor
async def ventas_meli(fecha_inicio: str = None, fecha_fin: str = None) -> dict:
    """Ventas de Mercado Libre (detectadas por email @marketplace.com del cliente).
    Pagina los documentos del período, busca el cliente de cada uno y filtra por email.
    Acepta lenguaje natural o YYYY-MM-DD; sin fechas usa el mes en curso."""
    ts_i, ts_f, desde, hasta = _parse_periodo(fecha_inicio, fecha_fin)

    docs = await _paginar(
        "documents.json",
        {"emissiondaterange": f"[{ts_i},{ts_f}]"},
        max_registros=2000,
    )
    if not docs:
        return {"periodo": {"desde": desde, "hasta": hasta},
                "total_ventas": 0, "total_pedidos": 0, "moneda": "CLP", "documentos": []}

    client_ids = list({
        str(d["client"]["id"])
        for d in docs
        if (d.get("client") or {}).get("id")
    })

    client_cache: dict[str, dict] = {}

    async def _get_client(cid: str) -> tuple[str, dict]:
        data = await _request("GET", f"clients/{cid}.json")
        return cid, data

    for i in range(0, len(client_ids), 10):
        results = await asyncio.gather(*[_get_client(cid) for cid in client_ids[i:i + 10]])
        for cid, data in results:
            if "error" not in data:
                client_cache[cid] = data

    meli_docs = []
    total_ventas = 0.0

    for d in docs:
        cid   = str((d.get("client") or {}).get("id", ""))
        cli   = client_cache.get(cid, {})
        email = (cli.get("email") or "").lower()
        if "@marketplace.com" not in email:
            continue
        monto = float(d.get("totalAmount") or 0)
        total_ventas += monto
        nombre = f"{cli.get('firstName', '')} {cli.get('lastName', '')}".strip()
        meli_docs.append(_compact({
            "id":      d.get("id"),
            "numero":  d.get("number"),
            "fecha":   _fecha(d.get("emissionDate")),
            "total":   round(monto),
            "cliente": nombre,
            "email":   cli.get("email"),
        }))

    ticket_promedio = round(total_ventas / len(meli_docs)) if meli_docs else 0

    return _compact({
        "periodo":         {"desde": desde, "hasta": hasta},
        "total_ventas":    round(total_ventas),
        "total_pedidos":   len(meli_docs),
        "ticket_promedio": ticket_promedio,
        "moneda":          "CLP",
        "documentos":      meli_docs,
    })
