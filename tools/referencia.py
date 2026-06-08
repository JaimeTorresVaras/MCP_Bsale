from typing import Callable
from config import mcp
from http_client import _request
from cache import _cache_get, _cache_set
from transforms import _compact
from monitor import _monitor


@mcp.tool()
@_monitor
async def configuracion(tipo: str = "todo") -> dict:
    """Datos de referencia estáticos cacheados 4h.
    tipo: 'sucursales'|'tipos_documento'|'listas_precio'|'medios_pago'|'impuestos'|'todo'"""

    async def _get_ref(cache_key: str, endpoint: str, slim_fn: Callable) -> list:
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached
        data = await _request("GET", endpoint)
        items = [slim_fn(i) for i in data.get("items", [])] if "error" not in data else []
        if items:
            _cache_set(cache_key, items)
        return items

    tipos_validos = ("sucursales", "tipos_documento", "listas_precio", "medios_pago", "impuestos", "todo")
    if tipo not in tipos_validos:
        return {"error": f"tipo inválido: '{tipo}'. Usa: {' | '.join(tipos_validos)}"}

    result: dict = {}
    if tipo in ("sucursales", "todo"):
        result["sucursales"] = await _get_ref(
            "offices", "offices.json",
            lambda o: _compact({"id": o.get("id"), "nombre": o.get("name"),
                                 "direccion": o.get("address"), "activo": o.get("state") == 0}),
        )
    if tipo in ("tipos_documento", "todo"):
        result["tipos_documento"] = await _get_ref(
            "document_types", "document_types.json",
            lambda t: _compact({"id": t.get("id"), "nombre": t.get("name"),
                                  "electronico": bool(t.get("isElectronic")),
                                  "nota_venta": bool(t.get("isSalesNote"))}),
        )
    if tipo in ("listas_precio", "todo"):
        result["listas_precio"] = await _get_ref(
            "price_lists", "price_lists.json",
            lambda p: _compact({"id": p.get("id"), "nombre": p.get("name"),
                                  "activo": p.get("state") == 0}),
        )
    if tipo in ("medios_pago", "todo"):
        result["medios_pago"] = await _get_ref(
            "payment_types", "payment_types.json",
            lambda p: _compact({"id": p.get("id"), "nombre": p.get("name"),
                                  "es_efectivo": bool(p.get("isCash")),
                                  "activo": p.get("state") == 0}),
        )
    if tipo in ("impuestos", "todo"):
        result["impuestos"] = await _get_ref(
            "taxes", "taxes.json",
            lambda t: _compact({"id": t.get("id"), "nombre": t.get("name"),
                                  "porcentaje": t.get("percentage"),
                                  "activo": t.get("state") == 0}),
        )
    return result
