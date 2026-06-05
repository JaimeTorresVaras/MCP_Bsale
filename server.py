#!/usr/bin/env python3
"""Bsale MCP Server v4 — Arquitectura optimizada para mínimo gasto de tokens.
Modo remoto: soporta transporte SSE (HTTP) para despliegue en la nube.
"""

import os
import sys
import time
import logging
import difflib
import asyncio
import httpx
import contextvars
import functools
import json as _json
from pathlib import Path
from datetime import datetime
from typing import Optional, Any, Callable
from mcp.server.fastmcp import FastMCP

# ═══════════════════════════════════════════════════════════════
# [1] CONFIG
# ═══════════════════════════════════════════════════════════════

# Modo de transporte: "stdio" (local) o "sse" (remoto/cloud)
TRANSPORT = os.getenv("MCP_TRANSPORT", "stdio").strip().lower()

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [bsale] %(levelname)s %(message)s",
)
log = logging.getLogger("bsale")

# En modo SSE se pueden pasar opciones de host/puerto
SSE_HOST = os.getenv("HOST", "0.0.0.0")
SSE_PORT = int(os.getenv("PORT", "8000"))

mcp = FastMCP(
    "bsale",
    # En modo remoto indicamos el host/puerto
    host=SSE_HOST if TRANSPORT == "sse" else "127.0.0.1",
    port=SSE_PORT,
)

BSALE_TOKEN = os.getenv("BSALE_API_TOKEN", "").strip()
BASE_URL    = "https://api.bsale.cl/v1"
TIMEOUT     = 30.0
MAX_LIMIT   = 50
MAX_PAGES   = 20

# En cloud no escribimos al disco (no hay filesystem persistente)
_log_path_str = os.getenv("LOG_FILE", "")
LOG_FILE = Path(_log_path_str) if _log_path_str else (
    Path(__file__).parent / "bsale_mcp.log" if TRANSPORT == "stdio" else None
)

# ═══════════════════════════════════════════════════════════════
# [1b] MAPA VENDEDOR → CANAL / SUCURSAL
#      Clave: nombre del vendedor en Bsale normalizado (minúsculas, sin espacios dobles)
#      canal: "Tienda" | "Internet" | "B2B" | "Widit"
# ═══════════════════════════════════════════════════════════════

VENDEDOR_CANAL: dict[str, dict] = {
    # ── Tienda física ──────────────────────────────────────────
    "bianca plaza":           {"sucursal": "Apoquindo",           "canal": "Tienda"},
    "constanza castillo":     {"sucursal": "Apoquindo",           "canal": "Tienda"},
    "catalina suarez":        {"sucursal": "Apoquindo",           "canal": "Tienda"},
    "maria jose henriquez":   {"sucursal": "Apoquindo",           "canal": "Tienda"},
    "magdalena perez":        {"sucursal": "Comicon",             "canal": "Tienda"},
    "benjamin perez":         {"sucursal": "Comicon",             "canal": "Tienda"},
    "easton outlet":          {"sucursal": "Easton",              "canal": "Tienda"},
    "ventas outlet":          {"sucursal": "Easton",              "canal": "Tienda"},
    "open kennedy":           {"sucursal": "Open Kennedy",        "canal": "Tienda"},
    "camila cardenas":        {"sucursal": "Open Kennedy",        "canal": "Tienda"},
    "portal la dehesa":       {"sucursal": "La Dehesa",           "canal": "Tienda"},
    "sucursal la dehesa":     {"sucursal": "La Dehesa",           "canal": "Tienda"},
    "nicolas cardenas":       {"sucursal": "La Dehesa",           "canal": "Tienda"},
    "mall sport":             {"sucursal": "Mall Sport",          "canal": "Tienda"},
    "mall sport 2":           {"sucursal": "Mall Sport",          "canal": "Tienda"},
    "parque arauco":          {"sucursal": "Parque Arauco",       "canal": "Tienda"},
    "mall plaza vespucio":    {"sucursal": "Mall Plaza Vespucio", "canal": "Tienda"},
    "luana valotta":          {"sucursal": "Tienda",              "canal": "Tienda"},
    "ximena tapia":           {"sucursal": "Tienda",              "canal": "Tienda"},
    "roberto morales":        {"sucursal": "Tienda",              "canal": "Tienda"},
    "cinthya olivares":       {"sucursal": "Tienda",              "canal": "Tienda"},
    "constanza letelier":     {"sucursal": "Tienda",              "canal": "Tienda"},
    "lucas mosqueira":        {"sucursal": "Tienda",              "canal": "Tienda"},
    "america":                {"sucursal": "Tienda",              "canal": "Tienda"},
    # ── Internet / ecommerce / apps ───────────────────────────
    "loading play connect":   {"sucursal": "Internet",            "canal": "Internet"},
    "venta internet":         {"sucursal": "Internet",            "canal": "Internet"},
    "mercado libre carnaval": {"sucursal": "Mercado Libre",       "canal": "Internet"},
    "uber eats":              {"sucursal": "Apps",                "canal": "Internet"},
    "rappi carnaval":         {"sucursal": "Apps",                "canal": "Internet"},
    "falabella carnaval":     {"sucursal": "Internet",            "canal": "Internet"},
    "paris carnaval":         {"sucursal": "Internet",            "canal": "Internet"},
    "vicente iturriaga":      {"sucursal": "Fondas",              "canal": "Internet"},
    # ── B2B ───────────────────────────────────────────────────
    "dayana acosta":          {"sucursal": "B2B",                 "canal": "B2B"},
    "simon catalan":          {"sucursal": "B2B",                 "canal": "B2B"},
    "stephanie salamanca":    {"sucursal": "B2B",                 "canal": "B2B"},
    "leandro turchan":        {"sucursal": "B2B",                 "canal": "B2B"},
    "rodrigo morales":        {"sucursal": "B2B",                 "canal": "B2B"},
    "miguel vallejos":        {"sucursal": "B2B",                 "canal": "B2B"},
    "hernan sandoval":        {"sucursal": "B2B",                 "canal": "B2B"},
    "gabriela soto":          {"sucursal": "B2B",                 "canal": "B2B"},
    # ── Widit ─────────────────────────────────────────────────
    "maria jesus varela":         {"sucursal": "Widit",           "canal": "Widit"},
    "maria elizabeth duarte":     {"sucursal": "Widit",           "canal": "Widit"},
    "venta internet colab/widit": {"sucursal": "Widit",           "canal": "Widit"},
}


def _lookup_canal(nombre: str) -> dict | None:
    """Devuelve {canal, sucursal} para un nombre de vendedor. Normaliza mayúsculas y espacios."""
    key = " ".join(nombre.lower().split())
    return VENDEDOR_CANAL.get(key)


# ═══════════════════════════════════════════════════════════════
# [8] OBSERVABILIDAD
# ═══════════════════════════════════════════════════════════════

# ContextVar que enlaza cada llamada HTTP con el tool que la originó
_ctx_api_calls: contextvars.ContextVar[list | None] = contextvars.ContextVar(
    "api_calls", default=None
)


def _monitor(fn):
    """Decorator que registra invocación, tokens estimados, timing y API calls en LOG_FILE."""
    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        api_calls: list = []
        token = _ctx_api_calls.set(api_calls)
        t0 = time.monotonic()
        result, error = None, None
        try:
            result = await fn(*args, **kwargs)
            return result
        except Exception as e:
            error = str(e)
            raise
        finally:
            _ctx_api_calls.reset(token)
            elapsed = round((time.monotonic() - t0) * 1000)
            result_str = _json.dumps(result, ensure_ascii=False, default=str) if result else ""
            entry = {
                "ts":               datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                "tool":             fn.__name__,
                "args":             {k: v for k, v in kwargs.items() if v is not None},
                "tokens_out_est":   len(result_str) // 4,
                "elapsed_ms":       elapsed,
                "api_calls":        api_calls,
                "error":            error,
            }
            try:
                if LOG_FILE:
                    with open(LOG_FILE, "a", encoding="utf-8") as f:
                        f.write(_json.dumps(entry, ensure_ascii=False) + "\n")
                else:
                    # En cloud logueamos a stderr en vez de archivo
                    log.info("CALL %s", _json.dumps(entry, ensure_ascii=False, default=str))
            except Exception:
                pass  # el log nunca debe romper el servidor
    return wrapper


# ═══════════════════════════════════════════════════════════════
# [2] HTTP
# ═══════════════════════════════════════════════════════════════

def _headers() -> dict:
    if not BSALE_TOKEN:
        raise RuntimeError("BSALE_API_TOKEN no configurado en el entorno.")
    return {"access_token": BSALE_TOKEN, "Content-Type": "application/json"}


async def _request(
    method: str, endpoint: str,
    params: Optional[dict] = None, data: Optional[dict] = None,
) -> dict:
    url = f"{BASE_URL}/{endpoint}"
    clean_params = {k: v for k, v in (params or {}).items() if v is not None}
    log.info("→ %s %s %s", method, endpoint, clean_params)
    try:
        t_req = time.monotonic()
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            res = await client.request(
                method=method, url=url, headers=_headers(),
                params=clean_params, json=data,
            )
        elapsed_req = round((time.monotonic() - t_req) * 1000)
        log.info("← %s %s (%dms)", res.status_code, endpoint, elapsed_req)
        calls = _ctx_api_calls.get(None)
        if calls is not None:
            calls.append({"endpoint": endpoint, "method": method,
                          "status": res.status_code, "bytes": len(res.content), "ms": elapsed_req})
        if res.status_code == 401: return {"error": "Token inválido o expirado."}
        if res.status_code == 403: return {"error": "Sin permisos para este recurso."}
        if res.status_code == 404: return {"error": f"No encontrado: {endpoint}"}
        if res.status_code == 429: return {"error": "Rate limit alcanzado. Espera unos segundos."}
        res.raise_for_status()
        return res.json()
    except httpx.TimeoutException:
        return {"error": f"Timeout ({TIMEOUT}s) al conectar con Bsale."}
    except httpx.ConnectError:
        return {"error": "No se pudo conectar con api.bsale.cl."}
    except httpx.HTTPStatusError as e:
        return {"error": f"HTTP {e.response.status_code}: {e.response.text[:200]}"}
    except Exception as e:
        log.exception("Error inesperado en %s", endpoint)
        return {"error": f"Error inesperado: {e}"}


# ═══════════════════════════════════════════════════════════════
# [3] PAGINACIÓN
# ═══════════════════════════════════════════════════════════════

async def _paginar(endpoint: str, params: dict, max_registros: int = 1000) -> list:
    """Acumula todos los items en una lista. Usar solo cuando se necesitan todos los registros."""
    items_total = []
    p = dict(params)
    p["limit"]  = MAX_LIMIT
    p["offset"] = 0
    pages = 0
    while pages < MAX_PAGES and len(items_total) < max_registros:
        data = await _request("GET", endpoint, params=p)
        if "error" in data:
            break
        items = data.get("items", [])
        if not items:
            break
        items_total.extend(items)
        if p["offset"] + MAX_LIMIT >= data.get("count", 0):
            break
        p["offset"] += MAX_LIMIT
        pages += 1
    return items_total



# ═══════════════════════════════════════════════════════════════
# [4] CACHÉ
# ═══════════════════════════════════════════════════════════════

_CACHE: dict[str, tuple[float, Any]] = {}

_CACHE_TTL: dict[str, int] = {
    "offices":        14400,  # 4 horas — sucursales casi no cambian
    "document_types": 14400,  # 4 horas — tipos de doc son configuración
    "price_lists":    14400,  # 4 horas — listas de precio son configuración
    "products_index": 3600,   # 1 hora  — catálogo más volátil
}


def _cache_get(key: str) -> Any:
    entry = _CACHE.get(key)
    if entry and time.monotonic() < entry[0]:
        log.info("cache hit: %s", key)
        return entry[1]
    return None


def _cache_set(key: str, value: Any) -> None:
    ttl = _CACHE_TTL.get(key, 3600)
    _CACHE[key] = (time.monotonic() + ttl, value)


# ═══════════════════════════════════════════════════════════════
# [5] TRANSFORMACIÓN
# ═══════════════════════════════════════════════════════════════

def _compact(obj: Any) -> Any:
    """Elimina valores vacíos y claves 'href' recursivamente."""
    if isinstance(obj, dict):
        return {k: _compact(v) for k, v in obj.items()
                if v not in (None, "", [], {}) and k != "href"}
    if isinstance(obj, list):
        return [_compact(i) for i in obj if i not in (None, "", [], {})]
    return obj


def _ts(fecha_str: str) -> int:
    return int(datetime.strptime(fecha_str.strip(), "%Y-%m-%d").timestamp())


def _fecha(ts: Any) -> Optional[str]:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d") if ts else None


def _slim_cliente(c: dict) -> dict:
    nombre = f"{c.get('firstName', '')} {c.get('lastName', '')}".strip()
    return _compact({
        "id":     c.get("id"),
        "nombre": nombre,
        "email":  c.get("email"),
        "rut":    c.get("code"),
        "fono":   c.get("phone"),
        "ciudad": c.get("city"),
        "tipo":   "Empresa" if c.get("personType") == 2 else "Persona",
    })


def _slim_producto(p: dict) -> dict:
    return _compact({
        "id":     p.get("id"),
        "nombre": p.get("name"),
        "desc":   p.get("description"),
        "activo": p.get("state") == 0,
    })


def _origen_documento(email: str, vendedor: str) -> str:
    """Detecta el origen del documento basado en email del cliente y vendedor."""
    if email and "@marketplace.com" in email.lower():
        return "MercadoLibre"
    info = _lookup_canal(vendedor) if vendedor else None
    if info:
        return info.get("canal", "Desconocido")
    return "Desconocido"


def _slim_documento(d: dict) -> dict:
    dt = d.get("documentType") or {}
    cl = d.get("client") or {}
    of = d.get("office") or {}
    us = d.get("salesmanUser") or {}
    nombre_cli = f"{cl.get('firstName', '')} {cl.get('lastName', '')}".strip()
    nombre_vendedor = f"{us.get('firstName', '')} {us.get('lastName', '')}".strip()
    email = cl.get("email") or ""
    origen = _origen_documento(email, nombre_vendedor)
    return _compact({
        "id":          d.get("id"),
        "numero":      d.get("number"),
        "fecha":       _fecha(d.get("emissionDate")),
        "total":       d.get("totalAmount"),
        "neto":        d.get("netAmount"),
        "iva":         d.get("taxAmount"),
        "tipo":        dt.get("name"),
        "tipo_id":     dt.get("id"),
        "cliente":     nombre_cli,
        "cliente_id":  cl.get("id"),
        "email":       email or None,
        "origen":      origen,
        "sucursal":    of.get("name"),
        "sucursal_id": of.get("id"),
        "vendedor":    nombre_vendedor,
    })


def _slim_stock(s: dict) -> dict:
    v = s.get("variant") or {}
    o = s.get("office") or {}
    return _compact({
        "stock":       s.get("quantity"),
        "variante_id": v.get("id"),
        "variante":    v.get("description"),
        "sku":         v.get("code"),
        "sucursal":    o.get("name"),
    })


def _slim_devolucion(d: dict) -> dict:
    cl = d.get("client") or {}
    nombre_cli = f"{cl.get('firstName', '')} {cl.get('lastName', '')}".strip()
    o = d.get("office") or {}
    return _compact({
        "id":        d.get("id"),
        "fecha":     _fecha(d.get("returnDate") or d.get("admissionDate")),
        "monto":     d.get("totalAmount") or d.get("amount"),
        "motivo":    d.get("motive") or d.get("note"),
        "estado":    d.get("state"),
        "cliente":   nombre_cli,
        "sucursal":  o.get("name"),
    })


def _slim_despacho(s: dict) -> dict:
    cl = s.get("client") or {}
    nombre_cli = f"{cl.get('firstName', '')} {cl.get('lastName', '')}".strip()
    o = s.get("office") or {}
    return _compact({
        "id":         s.get("id"),
        "fecha":      _fecha(s.get("shippingDate") or s.get("generationDate")),
        "estado":     s.get("state"),
        "cliente":    nombre_cli,
        "direccion":  s.get("address"),
        "sucursal":   o.get("name"),
        "guia":       s.get("code") or s.get("number"),
    })


# ═══════════════════════════════════════════════════════════════
# [6] DOMINIO
# ═══════════════════════════════════════════════════════════════

async def _agrupar_stocks(sucursal_id: Optional[int] = None) -> dict[int, dict]:
    """Retorna {variante_id: {stock, nombre, sku}} agregado por variante. Sin llamadas extra."""
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
    """Mapa {nombre_lower: slim_producto} del catálogo completo. Cacheado 1 hora."""
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


# ═══════════════════════════════════════════════════════════════
# [7] TOOLS MCP — 12 herramientas
# ═══════════════════════════════════════════════════════════════

# ── CLIENTES ────────────────────────────────────────────────────

@mcp.tool()
@_monitor
async def listar_clientes(
    nombre: str = None, email: str = None, rut: str = None, limite: int = 25,
) -> dict:
    """Busca clientes por nombre, email o RUT."""
    params = {"limit": min(max(1, limite), MAX_LIMIT), "offset": 0}
    if nombre: params["firstName"] = nombre.strip()
    if email:  params["email"]     = email.strip()
    if rut:    params["code"]      = rut.strip().upper()
    data = await _request("GET", "clients.json", params=params)
    if "error" in data:
        return data
    return {"total": data.get("count", 0), "clientes": [_slim_cliente(c) for c in data.get("items", [])]}


@mcp.tool()
@_monitor
async def crear_cliente(
    nombre: str, rut: str = None, email: str = None,
    fono: str = None, es_empresa: bool = False,
) -> dict:
    """Crea un cliente en Bsale."""
    body: dict = {"firstName": nombre.strip(), "personType": 2 if es_empresa else 1}
    if email: body["email"] = email.strip()
    if rut:   body["code"]  = rut.strip().upper()
    if fono:  body["phone"] = fono.strip()
    res = await _request("POST", "clients.json", data=body)
    return _slim_cliente(res) if "error" not in res else res


# ── PRODUCTOS ───────────────────────────────────────────────────

@mcp.tool()
@_monitor
async def buscar_producto(consulta: str = None, limite: int = 10) -> dict:
    """Busca productos por nombre (exacto o aproximado). Sin consulta lista los primeros activos."""
    if consulta:
        # Etapa 1: búsqueda nativa en la API (1 request)
        data = await _request("GET", "products.json", params={
            "limit": min(limite, MAX_LIMIT), "state": 0, "search": consulta.strip(),
        })
        if "error" not in data and data.get("items"):
            return {"total": data.get("count", 0), "productos": [_slim_producto(p) for p in data["items"]]}
        # Etapa 2: fuzzy sobre catálogo cacheado (0 requests si hay caché vigente)
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


# ── STOCK ────────────────────────────────────────────────────────

@mcp.tool()
@_monitor
async def consultar_stock(variante_id: int = None, sucursal_id: int = None) -> dict:
    """Stock disponible. Sin filtros devuelve la primera página del inventario."""
    params: dict = {"limit": MAX_LIMIT, "offset": 0}
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


# ── REFERENCIA (con caché) ───────────────────────────────────────

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


# ── DOCUMENTOS ───────────────────────────────────────────────────

@mcp.tool()
@_monitor
async def listar_documentos(
    fecha_inicio: str = None, fecha_fin: str = None,
    tipo_documento_id: int = None, cliente_id: int = None,
    limite: int = 25, pagina: int = 0,
) -> dict:
    """Lista documentos de venta del más reciente al más antiguo.
    tipo_documento_id: obtener IDs con configuracion('tipos_documento')."""
    lim = min(max(1, limite), MAX_LIMIT)
    params: dict = {
        "limit": lim, "offset": max(0, pagina) * lim,
        "orderby": "emissiondate", "order": "DESC",
    }
    if tipo_documento_id: params["documenttypeid"] = tipo_documento_id
    if cliente_id:        params["clientid"]       = cliente_id
    try:
        if fecha_inicio or fecha_fin:
            ts_i = _ts(fecha_inicio) if fecha_inicio else 0
            ts_f = (_ts(fecha_fin) + 86399) if fecha_fin else int(time.time())
            params["emissiondaterange"] = f"[{ts_i},{ts_f}]"
    except ValueError:
        return {"error": "Formato de fecha inválido. Usa YYYY-MM-DD."}
    data = await _request("GET", "documents.json", params=params)
    if "error" in data:
        return data
    return {"total": data.get("count", 0), "documentos": [_slim_documento(d) for d in data.get("items", [])]}


@mcp.tool()
@_monitor
async def resumen_ventas(
    fecha_inicio: str, fecha_fin: str, tipo_documento_id: int = None,
) -> dict:
    """Totales neto/IVA/bruto de un período con desglose por tipo de documento.
    tipo_documento_id: filtrar por tipo (ver configuracion)."""
    try:
        ts_inicio = _ts(fecha_inicio)
        ts_fin    = _ts(fecha_fin) + 86399
    except ValueError:
        return {"error": "Formato de fecha inválido. Usa YYYY-MM-DD."}

    # summary.json requiere emissiondaterange (no emissiondatestart/end — esos causan 504)
    params: dict = {
        "emissiondaterange": f"[{ts_inicio},{ts_fin}]",
        "perdocument":       1,
    }
    if tipo_documento_id:
        params["documenttypeid"] = tipo_documento_id

    data = await _request("GET", "documents/summary.json", params=params)

    if "error" in data:
        return data

    # La respuesta puede ser una lista directa o un dict con clave "items"
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
        "periodo":             {"desde": fecha_inicio, "hasta": fecha_fin},
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


# ── DETALLE Y SAC ────────────────────────────────────────────────

@mcp.tool()
@_monitor
async def obtener_detalle_recurso(tipo: str, recurso_id: int) -> dict:
    """Detalle completo de un recurso. tipo: 'clients'|'products'|'documents'|'variants'"""
    if tipo not in ("clients", "products", "documents", "variants"):
        return {"error": "tipo inválido. Usa: clients, products, documents, variants"}
    if recurso_id <= 0:
        return {"error": "recurso_id debe ser positivo."}
    return _compact(await _request("GET", f"{tipo}/{recurso_id}.json"))


@mcp.tool()
@_monitor
async def detalle_documento(documento_id: int) -> dict:
    """Líneas de un documento: qué productos se vendieron y en qué cantidad."""
    if documento_id <= 0:
        return {"error": "documento_id debe ser positivo."}
    data = await _request("GET", f"documents/{documento_id}/details.json")
    if "error" in data:
        return data
    lineas = [
        _compact({
            "variante_id": (i.get("variant") or {}).get("id"),
            "producto":    i.get("comment", ""),
            "cantidad":    i.get("quantity"),
            "precio_unit": i.get("netUnitValue"),
            "total":       i.get("totalUnitValue"),
            "descuento":   i.get("discount"),
        })
        for i in data.get("items", [])
    ]
    return {"documento_id": documento_id, "total_lineas": len(lineas), "lineas": lineas}


@mcp.tool()
@_monitor
async def rastrear_historial_cliente(identificador: str) -> dict:
    """Encuentra un cliente (nombre, email o RUT) y devuelve sus últimas 5 compras."""
    limpio = identificador.strip()
    params: dict = {"limit": 1}
    if "@" in limpio:
        params["email"] = limpio.lower()
    elif sum(c.isdigit() for c in limpio) > 5:
        params["code"] = limpio.upper()
    else:
        params["firstName"] = limpio

    data = await _request("GET", "clients.json", params=params)
    items = data.get("items", []) if "error" not in data else []

    if not items and "firstName" in params:
        data2 = await _request("GET", "clients.json", params={"lastName": limpio, "limit": 1})
        items = data2.get("items", []) if "error" not in data2 else []

    if not items:
        return {"error": f"No se encontró cliente para: '{identificador}'"}

    cliente = items[0]
    docs_data = await _request("GET", "documents.json", params={
        "clientid": cliente["id"], "limit": 5,
        "orderby": "emissiondate", "order": "DESC",
    })
    compras = [_slim_documento(d) for d in docs_data.get("items", [])] if "error" not in docs_data else []

    return {"cliente": _slim_cliente(cliente), "ultimas_compras": compras}


# ── ANÁLISIS AVANZADO (endpoints nativos) ───────────────────────

@mcp.tool()
@_monitor
async def resumen_pagos(
    fecha_inicio: str, fecha_fin: str, sucursal_id: int = None,
) -> dict:
    """Desglose por medio de pago (efectivo, tarjeta, etc.) filtrado por fecha de emisión.
    Usa sucursal_id para acotar resultados. Sin sucursal analiza hasta 100 documentos."""
    try:
        ts_inicio = _ts(fecha_inicio)
        ts_fin    = _ts(fecha_fin) + 86399
    except ValueError:
        return {"error": "Formato de fecha inválido. Usa YYYY-MM-DD."}

    params_docs: dict = {
        "emissiondaterange": f"[{ts_inicio},{ts_fin}]",
    }
    if sucursal_id:
        params_docs["officeid"] = sucursal_id

    max_docs = 200 if sucursal_id else 100
    docs = await _paginar("documents.json", params_docs, max_registros=max_docs)

    if not docs:
        return _compact({"periodo": {"desde": fecha_inicio, "hasta": fecha_fin},
                         "total_bruto": 0, "moneda": "CLP", "por_medio_pago": {}})

    # Buscar pagos de cada documento en paralelo (lotes de 10)
    async def _pagos_doc(doc_id: int) -> list:
        data = await _request("GET", f"documents/{doc_id}/payments.json")
        return data.get("items") or [] if "error" not in data else []

    doc_ids = [d["id"] for d in docs if d.get("id")]
    todas_pagos: list = []
    for i in range(0, len(doc_ids), 10):
        lote = await asyncio.gather(*[_pagos_doc(did) for did in doc_ids[i:i+10]])
        for items in lote:
            todas_pagos.extend(items)

    # Agrupar por tipo de pago
    por_medio: dict = {}
    total_bruto = 0.0
    for p in todas_pagos:
        pt     = p.get("paymentType") or {}
        nombre = pt.get("name") or "Sin clasificar"
        monto  = float(p.get("amount") or 0)
        por_medio[nombre] = por_medio.get(nombre, 0.0) + monto
        total_bruto += monto

    return _compact({
        "periodo":              {"desde": fecha_inicio, "hasta": fecha_fin},
        "documentos_analizados": len(docs),
        "total_bruto":          round(total_bruto),
        "moneda":               "CLP",
        "por_medio_pago": {
            k: round(v)
            for k, v in sorted(por_medio.items(), key=lambda x: x[1], reverse=True)
        },
    })


async def _fetch_sellers(ts_inicio: int, ts_fin: int) -> list[dict] | dict:
    """Llama a users/sales_summary.json y devuelve lista de vendedores enriquecidos con canal."""
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
        neto   = round(float(s.get("total")    or s.get("subtotal") or 0))
        info   = _lookup_canal(nombre) or {}
        result.append(_compact({
            "nombre":    nombre,
            "canal":     info.get("canal", "Desconocido"),
            "sucursal":  info.get("sucursal"),
            "ventas":    ventas,
            "neto":      neto,
        }))
    return sorted(result, key=lambda x: x.get("ventas", 0), reverse=True)


@mcp.tool()
@_monitor
async def ranking_vendedores(fecha_inicio: str, fecha_fin: str) -> dict:
    """Ventas por vendedor en un período con canal y sucursal identificados.
    1 llamada a Bsale. Útil para desempeño del equipo de ventas."""
    try:
        ts_inicio = _ts(fecha_inicio)
        ts_fin    = _ts(fecha_fin) + 86399
    except ValueError:
        return {"error": "Formato de fecha inválido. Usa YYYY-MM-DD."}

    vendedores = await _fetch_sellers(ts_inicio, ts_fin)
    if isinstance(vendedores, dict) and "error" in vendedores:
        return vendedores

    return {
        "periodo":   {"desde": fecha_inicio, "hasta": fecha_fin},
        "total":     sum(v.get("ventas", 0) for v in vendedores),
        "moneda":    "CLP",
        "vendedores": vendedores,
    }


@mcp.tool()
@_monitor
async def resumen_por_canal(fecha_inicio: str, fecha_fin: str) -> dict:
    """Ventas agrupadas por canal (Tienda / Internet / B2B / Widit) usando el mapa de vendedores.
    Incluye participación porcentual de cada canal. 1 llamada a Bsale."""
    try:
        ts_inicio = _ts(fecha_inicio)
        ts_fin    = _ts(fecha_fin) + 86399
    except ValueError:
        return {"error": "Formato de fecha inválido. Usa YYYY-MM-DD."}

    vendedores = await _fetch_sellers(ts_inicio, ts_fin)
    if isinstance(vendedores, dict) and "error" in vendedores:
        return vendedores

    canales: dict[str, float] = {}
    for v in vendedores:
        canal = v.get("canal", "Desconocido")
        canales[canal] = canales.get(canal, 0.0) + v.get("ventas", 0)

    total = sum(canales.values()) or 1
    desglose = sorted(
        [
            {
                "canal":        canal,
                "ventas":       round(monto),
                "participacion": round(monto / total * 100, 1),
            }
            for canal, monto in canales.items()
        ],
        key=lambda x: x["ventas"],
        reverse=True,
    )

    return {
        "periodo":   {"desde": fecha_inicio, "hasta": fecha_fin},
        "total":     round(total),
        "moneda":    "CLP",
        "por_canal": desglose,
    }


# ── PRODUCTOS / VARIANTES AVANZADO ───────────────────────────────

@mcp.tool()
@_monitor
async def ventas_meli(fecha_inicio: str, fecha_fin: str) -> dict:
    """Ventas de Mercado Libre detectadas por email @marketplace.com del cliente.
    Pagina todos los documentos del período, busca el cliente de cada uno y filtra por email.
    Fechas en YYYY-MM-DD."""
    try:
        ts_i = _ts(fecha_inicio)
        ts_f = _ts(fecha_fin) + 86399
    except ValueError:
        return {"error": "Formato de fecha inválido. Usa YYYY-MM-DD."}

    docs = await _paginar(
        "documents.json",
        {"emissiondaterange": f"[{ts_i},{ts_f}]"},
        max_registros=2000,
    )
    if not docs:
        return {"periodo": {"desde": fecha_inicio, "hasta": fecha_fin},
                "total_ventas": 0, "total_pedidos": 0, "moneda": "CLP", "documentos": []}

    # IDs de cliente únicos presentes en el período
    client_ids = list({
        str(d["client"]["id"])
        for d in docs
        if (d.get("client") or {}).get("id")
    })

    # Buscar clientes en lotes de 10 en paralelo
    client_cache: dict[str, dict] = {}

    async def _get_client(cid: str) -> tuple[str, dict]:
        data = await _request("GET", f"clients/{cid}.json")
        return cid, data

    for i in range(0, len(client_ids), 10):
        results = await asyncio.gather(*[_get_client(cid) for cid in client_ids[i:i + 10]])
        for cid, data in results:
            if "error" not in data:
                client_cache[cid] = data

    # Filtrar documentos cuyo cliente tiene email @marketplace.com
    meli_docs = []
    total_ventas = 0.0

    for d in docs:
        cid  = str((d.get("client") or {}).get("id", ""))
        cli  = client_cache.get(cid, {})
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
        "periodo":         {"desde": fecha_inicio, "hasta": fecha_fin},
        "total_ventas":    round(total_ventas),
        "total_pedidos":   len(meli_docs),
        "ticket_promedio": ticket_promedio,
        "moneda":          "CLP",
        "documentos":      meli_docs,
    })


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
    i = items[0]
    neto   = float(i.get("variantValue") or i.get("value") or 0)
    bruto  = round(neto * 1.19)
    return _compact({
        "variante_id":    variante_id,
        "lista_precio_id": lista_precio_id,
        "precio_neto":    round(neto),
        "precio_bruto":   bruto,
        "moneda":         "CLP",
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


# ── DEVOLUCIONES ─────────────────────────────────────────────────

@mcp.tool()
@_monitor
async def listar_devoluciones(
    fecha_inicio: str = None, fecha_fin: str = None,
    sucursal_id: int = None, limite: int = 25,
) -> dict:
    """Lista devoluciones de un período. Fechas en YYYY-MM-DD."""
    params: dict = {"limit": min(max(1, limite), MAX_LIMIT), "offset": 0}
    if sucursal_id: params["officeid"] = sucursal_id
    try:
        if fecha_inicio: params["returndatestart"] = _ts(fecha_inicio)
        if fecha_fin:    params["returndateend"]   = _ts(fecha_fin) + 86399
    except ValueError:
        return {"error": "Formato de fecha inválido. Usa YYYY-MM-DD."}
    data = await _request("GET", "returns.json", params=params)
    if "error" in data:
        return data
    items = data.get("items") or (data if isinstance(data, list) else [])
    return {
        "total": data.get("count", len(items)) if isinstance(data, dict) else len(items),
        "devoluciones": [_slim_devolucion(d) for d in items],
    }


# ── PROVEEDORES ───────────────────────────────────────────────────

@mcp.tool()
@_monitor
async def documentos_proveedor(
    fecha_inicio: str = None, rut_proveedor: str = None, limite: int = 25,
) -> dict:
    """Facturas de proveedores. fecha_inicio en YYYY-MM filtra por mes (ej: 2026-05)."""
    params: dict = {"limit": min(max(1, limite), MAX_LIMIT), "offset": 0}
    if rut_proveedor: params["clientcode"] = rut_proveedor.strip().upper()
    try:
        if fecha_inicio:
            d = fecha_inicio.strip()
            params["year"]  = int(d[:4])
            params["month"] = int(d[5:7])
    except (ValueError, IndexError):
        return {"error": "Formato de fecha inválido. Usa YYYY-MM-DD."}
    data = await _request("GET", "third_party_documents.json", params=params)
    if "error" in data:
        return data
    items = data.get("items") or (data if isinstance(data, list) else [])
    return {
        "total": data.get("count", len(items)) if isinstance(data, dict) else len(items),
        "documentos": [
            _compact({
                "id":        d.get("id"),
                "numero":    d.get("number"),
                "fecha":     _fecha(d.get("emissionDate")),
                "proveedor": d.get("clientName") or d.get("name"),
                "rut":       d.get("clientCode") or d.get("code"),
                "total":     d.get("totalAmount"),
                "estado":    d.get("state"),
            })
            for d in items
        ],
    }


# ── LOGÍSTICA ─────────────────────────────────────────────────────

@mcp.tool()
@_monitor
async def listar_despachos(
    fecha_inicio: str = None, fecha_fin: str = None,
    sucursal_id: int = None, limite: int = 25,
) -> dict:
    """Despachos/envíos de un período. state: 0=pendiente, 1=despachado."""
    params: dict = {"limit": min(max(1, limite), MAX_LIMIT), "offset": 0}
    if sucursal_id: params["officeid"] = sucursal_id
    try:
        if fecha_inicio: params["shippingdatestart"] = _ts(fecha_inicio)
        if fecha_fin:    params["shippingdateend"]   = _ts(fecha_fin) + 86399
    except ValueError:
        return {"error": "Formato de fecha inválido. Usa YYYY-MM-DD."}
    data = await _request("GET", "shippings.json", params=params)
    if "error" in data:
        return data
    items = data.get("items") or (data if isinstance(data, list) else [])
    return {
        "total": data.get("count", len(items)) if isinstance(data, dict) else len(items),
        "despachos": [_slim_despacho(d) for d in items],
    }


# ── Health check (para Railway / Render / load balancers) ────────
from starlette.requests import Request
from starlette.responses import JSONResponse


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """Endpoint público de salud. No requiere autorización."""
    return JSONResponse({"status": "ok", "service": "bsale-mcp"})


# ── Entry point ──────────────────────────────────────────────────
if __name__ == "__main__":
    log.info("Bsale MCP Server v4 iniciando... (transporte: %s)", TRANSPORT)
    if not BSALE_TOKEN:
        log.error("BSALE_API_TOKEN no configurado.")
        sys.exit(1)

    if TRANSPORT == "sse":
        log.info("Modo remoto SSE en %s:%s", SSE_HOST, SSE_PORT)
        mcp.run(transport="sse")
    else:
        mcp.run()
