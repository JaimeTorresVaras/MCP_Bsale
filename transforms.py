from typing import Any, Optional
from datetime import datetime
from config import _lookup_canal


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
