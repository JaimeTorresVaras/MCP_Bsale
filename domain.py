import asyncio
import difflib
from typing import Optional
from http_client import _request, _paginar
from cache import _cache_get, _cache_set
from transforms import _slim_producto, _compact, _norm
from config import _lookup_canal, MAX_LIMIT


async def _agrupar_stocks(sucursal_id: Optional[int] = None) -> dict[int, dict]:
    clave = f"agrupado_stock_{sucursal_id or 'all'}"
    cached = _cache_get(clave)
    if cached is not None:
        return cached
    params: dict = {"expand": "[variant]"}
    if sucursal_id:
        params["officeid"] = sucursal_id
    items = await _paginar("stocks.json", params, max_registros=2000)
    resultado: dict[int, dict] = {}
    for item in items:
        v = item.get("variant") or {}
        vid = v.get("id")
        if not vid:
            continue
        if vid not in resultado:
            code = (v.get("code") or "").strip()
            resultado[vid] = {
                "stock":       0.0,
                "sku":         code,
                "producto_id": (v.get("product") or {}).get("id"),
                "nombre":      code or f"Variante {vid}",
            }
        resultado[vid]["stock"] += float(item.get("quantity") or 0)
    if resultado:
        _cache_set(clave, resultado, ttl=600)  # 10 min: análisis no repagina cada vez
    return resultado


async def _nombres_de_productos(ids) -> dict[int, str]:
    """Resuelve {producto_id: nombre} en lotes paralelos, con caché por id."""
    resultado: dict[int, str] = {}
    pendientes: list[int] = []
    for pid in {int(i) for i in ids if i}:
        cached = _cache_get(f"prod_name_{pid}")
        if cached is not None:
            resultado[pid] = cached
        else:
            pendientes.append(pid)

    async def _uno(pid: int) -> tuple[int, Optional[str]]:
        d = await _request("GET", f"products/{pid}.json")
        return pid, (d.get("name") if "error" not in d else None)

    for i in range(0, len(pendientes), 10):
        lote = await asyncio.gather(*[_uno(p) for p in pendientes[i:i + 10]])
        for pid, nombre in lote:
            if nombre:
                _cache_set(f"prod_name_{pid}", nombre)
                resultado[pid] = nombre
    return resultado


async def _get_products_index() -> dict[str, dict]:
    cached = _cache_get("products_index")
    if cached is not None:
        return cached
    todos = await _paginar("products.json", {"state": 0}, max_registros=2000)
    index = {
        (p.get("name") or "").lower().strip(): _slim_producto(p)
        for p in todos if p.get("name")
    }
    _cache_set("products_index", index)
    return index


async def _fetch_sellers(ts_inicio: int, ts_fin: int) -> list[dict] | dict:
    data = await _request("GET", "users/sales_summary.json", params={
        "startdate": ts_inicio,
        "enddate":   ts_fin,
    })
    if "error" in data:
        return data

    result = []
    for s in (data.get("sellers") or []):
        nombre = s.get("fullName") or f"Usuario {s.get('id')}"
        ventas = round(float(s.get("subtotal") or 0))
        neto   = round(float(s.get("total") or s.get("subtotal") or 0))
        info   = _lookup_canal(nombre) or {}
        result.append(_compact({
            "nombre":   nombre,
            "canal":    info.get("canal", "Desconocido"),
            "sucursal": info.get("sucursal"),
            "ventas":   ventas,
            "neto":     neto,
        }))
    return sorted(result, key=lambda x: x.get("ventas", 0), reverse=True)


# ── Búsqueda y análisis de productos ────────────────────────────────────────
def _stem(palabra: str) -> str:
    """Plural simple a singular para tolerar 'vasos' -> 'vaso'."""
    return palabra[:-1] if palabra.endswith("s") and len(palabra) > 3 else palabra


async def _buscar_productos(consulta: str, limite: int = 10) -> list:
    """Productos (items crudos) por nombre parcial, varias palabras o aproximado.
    Núcleo compartido por buscar_producto y las herramientas de análisis."""
    lim = min(max(1, limite), MAX_LIMIT)

    async def _por_nombre(term: str, n: int) -> list:
        d = await _request("GET", "products.json",
                           params={"limit": min(n, MAX_LIMIT), "state": 0, "name": term})
        return d.get("items", []) if "error" not in d else []

    q = (consulta or "").strip()
    if not q:
        return []
    tokens = [_stem(t) for t in q.lower().split() if len(t) >= 3]

    if len(tokens) <= 1:
        items = await _por_nombre(q, lim)
    else:
        principal = max(tokens, key=len)
        cand = await _paginar("products.json", {"state": 0, "name": principal}, max_registros=300)
        items = [p for p in cand if all(t in (p.get("name") or "").lower() for t in tokens)]
        if not items:
            items = await _por_nombre(q, lim)

    if items:
        return items[:lim]

    index = await _get_products_index()
    matches = difflib.get_close_matches(q.lower(), list(index), n=lim, cutoff=0.6)
    return [{"id": index[m]["id"], "name": index[m].get("nombre"), "state": 0} for m in matches]


async def _variantes_de_producto(producto_id: int) -> list:
    d = await _request("GET", f"products/{producto_id}/variants.json")
    return d.get("items", []) if "error" not in d else []


async def _costo_variante(vid: int) -> dict:
    """{costo: promedio unitario, valorizado: costo total FIFO} de una variante (cacheado)."""
    cached = _cache_get(f"costo_{vid}")
    if cached is not None:
        return cached
    d = await _request("GET", f"variants/{vid}/costs.json")
    res = ({"costo": float(d.get("averageCost") or 0), "valorizado": float(d.get("totalCost") or 0)}
           if "error" not in d else {"costo": 0.0, "valorizado": 0.0})
    _cache_set(f"costo_{vid}", res)
    return res


async def _lista_precio_default() -> Optional[int]:
    cached = _cache_get("lista_precio_default")
    if cached is not None:
        return cached
    d = await _request("GET", "price_lists.json", params={"limit": 50})
    activas = [p for p in d.get("items", []) if p.get("state") == 0] if "error" not in d else []
    lid = activas[0]["id"] if activas else None
    if lid:
        _cache_set("lista_precio_default", lid)
    return lid


async def _precio_neto(vid: int, lista_id: Optional[int] = None) -> float:
    """Precio neto de venta de una variante en la lista indicada (o la default)."""
    lista_id = lista_id or await _lista_precio_default()
    if not lista_id:
        return 0.0
    d = await _request("GET", f"price_lists/{lista_id}/details.json",
                       params={"variantid": vid, "limit": 1})
    items = (d.get("items") or (d if isinstance(d, list) else [])) if "error" not in d else []
    return float(items[0].get("variantValue") or items[0].get("value") or 0) if items else 0.0


async def _stock_variante(vid: int, sucursal_id: Optional[int] = None):
    """(stock_total, [{sucursal, stock}]) de una variante."""
    p: dict = {"variantid": vid, "expand": "[office]", "limit": MAX_LIMIT}
    if sucursal_id:
        p["officeid"] = sucursal_id
    rows = (await _request("GET", "stocks.json", params=p)).get("items", [])
    total = sum(float(r.get("quantity") or 0) for r in rows)
    por_suc = [{"sucursal": (r.get("office") or {}).get("name"), "stock": r.get("quantity")}
               for r in rows]
    return total, por_suc


async def _en_lotes(fn, items: list, batch: int = 10) -> list:
    """Ejecuta fn(item) en paralelo por lotes (evita saturar el API)."""
    salida = []
    for i in range(0, len(items), batch):
        salida.extend(await asyncio.gather(*[fn(x) for x in items[i:i + batch]]))
    return salida


def _es_venta(doc: dict) -> bool:
    """True solo para documentos de venta (boletas/facturas). Excluye guías de
    despacho, notas de crédito, devoluciones y anulaciones. Requiere document_type expandido."""
    n = _norm((doc.get("document_type") or {}).get("name") or "")
    return bool(n) and not any(x in n for x in ("guia", "credito", "devolucion", "anulacion"))


async def _resumen_documentos(ts_i: int, ts_f: int) -> dict:
    """Escanea los documentos del período (líneas, sucursal, tipo y cliente) en una sola
    pasada concurrente (reintento 429, caché 30 min) y arma varias agregaciones:
      - por_variante: {vid: {cantidad, ingreso, por_sucursal, por_tipo}}
      - por_cliente:  {client_id: {total, docs}}  (total bruto comprado)
      - totales:      {neto, num_docs}
    Cuenta solo ventas reales (boletas/facturas); excluye guías y notas de crédito."""
    clave = f"resumen_docs_{ts_i}_{ts_f}"
    cached = _cache_get(clave)
    if cached is not None:
        return cached

    base = {"emissiondaterange": f"[{ts_i},{ts_f}]", "limit": MAX_LIMIT,
            "expand": "[details,office,document_type]"}

    async def _pagina(off: int) -> list:
        for intento in range(3):  # reintenta ante rate-limit (429) para no perder páginas
            d = await _request("GET", "documents.json", params={**base, "offset": off})
            if "error" not in d:
                return d.get("items", [])
            await asyncio.sleep(1.5 * (intento + 1))
        return []

    vacio = {"por_variante": {}, "por_cliente": {}, "totales": {"neto": 0.0, "num_docs": 0}}
    primera = await _request("GET", "documents.json", params={**base, "offset": 0})
    if "error" in primera:
        return vacio
    docs = list(primera.get("items", []))
    offsets = list(range(MAX_LIMIT, primera.get("count", 0), MAX_LIMIT))
    for lote in await _en_lotes(_pagina, offsets, batch=12):
        docs.extend(lote)

    por_variante: dict[int, dict] = {}
    por_cliente: dict[int, dict] = {}
    neto_total = 0.0
    num_docs = 0
    for doc in docs:
        if not _es_venta(doc):
            continue
        num_docs += 1
        neto_total += float(doc.get("netAmount") or 0)
        cid = (doc.get("client") or {}).get("id")
        if cid:
            ec = por_cliente.setdefault(int(cid), {"total": 0.0, "docs": 0})
            ec["total"] += float(doc.get("totalAmount") or 0)
            ec["docs"]  += 1
        office = (doc.get("office") or {}).get("name") or "Sin sucursal"
        tipo   = (doc.get("document_type") or {}).get("name") or "Otro"
        for li in ((doc.get("details") or {}).get("items") or []):
            vid = (li.get("variant") or {}).get("id")
            if not vid:
                continue
            vid = int(vid)
            qty = float(li.get("quantity") or 0)
            ing = float(li.get("netAmount") or 0)
            e = por_variante.setdefault(vid, {"cantidad": 0.0, "ingreso": 0.0,
                                              "por_sucursal": {}, "por_tipo": {}})
            e["cantidad"] += qty
            e["ingreso"]  += ing
            e["por_sucursal"][office] = e["por_sucursal"].get(office, 0.0) + qty
            t = e["por_tipo"].setdefault(tipo, {"cantidad": 0.0, "ingreso": 0.0})
            t["cantidad"] += qty
            t["ingreso"]  += ing

    resumen = {"por_variante": por_variante, "por_cliente": por_cliente,
               "totales": {"neto": neto_total, "num_docs": num_docs}}
    _cache_set(clave, resumen, ttl=1800)
    return resumen


async def _ventas_por_variante(ts_i: int, ts_f: int) -> dict:
    """Compat: solo las ventas por variante (ver _resumen_documentos)."""
    return (await _resumen_documentos(ts_i, ts_f))["por_variante"]


async def _nombres_de_clientes(ids) -> dict[int, dict]:
    """{client_id: {nombre, rut}} en lotes paralelos, con caché por id."""
    resultado: dict[int, dict] = {}
    pendientes: list[int] = []
    for cid in {int(i) for i in ids if i}:
        cached = _cache_get(f"cli_{cid}")
        if cached is not None:
            resultado[cid] = cached
        else:
            pendientes.append(cid)

    async def _uno(cid: int):
        d = await _request("GET", f"clients/{cid}.json")
        if "error" in d:
            return cid, None
        nombre = f"{d.get('firstName','')} {d.get('lastName','')}".strip() or d.get("company") or f"Cliente {cid}"
        return cid, {"nombre": nombre, "rut": d.get("code")}

    for cid, info in await _en_lotes(_uno, pendientes, batch=10):
        if info:
            _cache_set(f"cli_{cid}", info)
            resultado[cid] = info
    return resultado


async def _info_variantes(vids) -> dict[int, dict]:
    """{vid: {producto, sku}} resolviendo variante -> producto -> nombre (con caché)."""
    resultado: dict[int, dict] = {}
    pendientes: list[int] = []
    for vid in {int(v) for v in vids if v}:
        cached = _cache_get(f"varinfo_{vid}")
        if cached is not None:
            resultado[vid] = cached
        else:
            pendientes.append(vid)

    async def _uno(vid: int):
        d = await _request("GET", f"variants/{vid}.json")
        if "error" in d:
            return vid, None
        return vid, {"producto_id": (d.get("product") or {}).get("id"), "sku": d.get("code")}

    parciales = {vid: info for vid, info in await _en_lotes(_uno, pendientes, batch=10) if info}
    nombres = await _nombres_de_productos({i["producto_id"] for i in parciales.values() if i.get("producto_id")})
    for vid, info in parciales.items():
        pid = info.get("producto_id")
        r = {"producto": nombres.get(int(pid)) if pid else None, "sku": info.get("sku")}
        _cache_set(f"varinfo_{vid}", r)
        resultado[vid] = r
    return resultado
