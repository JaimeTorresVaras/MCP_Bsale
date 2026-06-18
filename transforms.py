import unicodedata
from typing import Any, Optional
from datetime import datetime, date, timedelta, time as _time
from config import _lookup_canal

try:  # zona horaria de Chile; fallback a UTC-4 si no hay tzdata
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo("America/Santiago")
except Exception:  # pragma: no cover
    from datetime import timezone
    _TZ = timezone(timedelta(hours=-4))


def _compact(obj: Any) -> Any:
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


# ── Fechas en lenguaje natural ──────────────────────────────────────────────
def _hoy() -> date:
    return datetime.now(_TZ).date()


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower().strip()
    return s.replace(" ", "_").replace("-", "_")


def _ultimo_dia_mes(d: date) -> date:
    nxt = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
    return nxt - timedelta(days=1)


def _palabra_a_rango(term: str) -> Optional[tuple[date, date]]:
    """Convierte una palabra clave normalizada en (desde, hasta). None si no aplica."""
    hoy = _hoy()
    fijos = {
        "hoy": (hoy, hoy),
        "ayer": (hoy - timedelta(days=1), hoy - timedelta(days=1)),
        "anteayer": (hoy - timedelta(days=2), hoy - timedelta(days=2)),
        "semana": (hoy - timedelta(days=hoy.weekday()), hoy),
        "esta_semana": (hoy - timedelta(days=hoy.weekday()), hoy),
        "mes": (hoy.replace(day=1), hoy),
        "este_mes": (hoy.replace(day=1), hoy),
        "anio": (hoy.replace(month=1, day=1), hoy),
        "ano": (hoy.replace(month=1, day=1), hoy),
        "este_anio": (hoy.replace(month=1, day=1), hoy),
        "este_ano": (hoy.replace(month=1, day=1), hoy),
    }
    if term in fijos:
        return fijos[term]
    if term in ("semana_pasada", "ultima_semana"):
        fin = hoy - timedelta(days=hoy.weekday() + 1)
        return fin - timedelta(days=6), fin
    if term in ("mes_pasado", "ultimo_mes"):
        fin = hoy.replace(day=1) - timedelta(days=1)
        return fin.replace(day=1), fin
    if term in ("anio_pasado", "ano_pasado"):
        return date(hoy.year - 1, 1, 1), date(hoy.year - 1, 12, 31)
    for n in (7, 15, 30, 60, 90, 180, 365):
        if term in (f"ultimos_{n}", f"ultimos_{n}_dias", f"{n}_dias", f"{n}dias"):
            return hoy - timedelta(days=n - 1), hoy
    return None


def _a_fecha(valor: str, fin_de_mes: bool = False) -> Optional[date]:
    """Parsea 'YYYY-MM-DD' o 'YYYY-MM' (mes -> primer o último día)."""
    v = valor.strip()
    try:
        if len(v) == 7:
            d = datetime.strptime(v, "%Y-%m").date()
            return _ultimo_dia_mes(d) if fin_de_mes else d
        return datetime.strptime(v[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _rango_ts(desde: date, hasta: date) -> tuple[int, int]:
    ts_i = int(datetime.combine(desde, _time.min, _TZ).timestamp())
    ts_f = int(datetime.combine(hasta, _time.max, _TZ).timestamp())
    return ts_i, ts_f


def _parse_periodo(inicio: str = None, fin: str = None, por_defecto: str = "mes"):
    """Interpreta un período en lenguaje natural o fechas exactas.
    Devuelve (ts_inicio, ts_fin, desde_iso, hasta_iso); (None, None, None, None) si
    no hay nada y por_defecto es None.
    Acepta: 'hoy', 'ayer', 'semana', 'mes', 'mes_pasado', 'año', 'ultimos_7', etc.,
    o 'YYYY-MM-DD' / 'YYYY-MM'. Sin datos usa por_defecto ('mes' = mes en curso)."""
    if inicio:
        rango = _palabra_a_rango(_norm(inicio))
        if rango:
            desde, hasta = rango
            return (*_rango_ts(desde, hasta), desde.isoformat(), hasta.isoformat())

    desde = _a_fecha(inicio) if inicio else None
    hasta = _a_fecha(fin, fin_de_mes=True) if fin else None

    if desde is None and hasta is None:
        if por_defecto == "mes":
            hoy = _hoy()
            desde, hasta = hoy.replace(day=1), hoy
        else:
            return None, None, None, None
    else:
        if desde is None:
            desde = hasta.replace(day=1)
        if hasta is None:
            # 'YYYY-MM' solo en inicio => ese mes completo; si no, hasta hoy
            hasta = _ultimo_dia_mes(desde) if inicio and len(inicio.strip()) == 7 else _hoy()

    return (*_rango_ts(desde, hasta), desde.isoformat(), hasta.isoformat())


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
    nombre_cli      = f"{cl.get('firstName', '')} {cl.get('lastName', '')}".strip()
    nombre_vendedor = f"{us.get('firstName', '')} {us.get('lastName', '')}".strip()
    email  = cl.get("email") or ""
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
        "id":       d.get("id"),
        "fecha":    _fecha(d.get("returnDate") or d.get("admissionDate")),
        "monto":    d.get("totalAmount") or d.get("amount"),
        "motivo":   d.get("motive") or d.get("note"),
        "estado":   d.get("state"),
        "cliente":  nombre_cli,
        "sucursal": o.get("name"),
    })


def _slim_despacho(s: dict) -> dict:
    cl = s.get("client") or {}
    nombre_cli = f"{cl.get('firstName', '')} {cl.get('lastName', '')}".strip()
    o = s.get("office") or {}
    return _compact({
        "id":        s.get("id"),
        "fecha":     _fecha(s.get("shippingDate") or s.get("generationDate")),
        "estado":    s.get("state"),
        "cliente":   nombre_cli,
        "direccion": s.get("address"),
        "sucursal":  o.get("name"),
        "guia":      s.get("code") or s.get("number"),
    })
