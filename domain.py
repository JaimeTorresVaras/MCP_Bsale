from typing import Optional
from http_client import _request, _paginar
from cache import _cache_get, _cache_set
from transforms import _slim_producto, _compact
from config import _lookup_canal


async def _agrupar_stocks(sucursal_id: Optional[int] = None) -> dict[int, dict]:
    params: dict = {}
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
            desc = (v.get("description") or "").strip()
            code = (v.get("code") or "").strip()
            resultado[vid] = {
                "stock":  0.0,
                "nombre": f"{code} {desc}".strip() or f"Variante {vid}",
                "sku":    code,
            }
        resultado[vid]["stock"] += float(item.get("quantity") or 0)
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
