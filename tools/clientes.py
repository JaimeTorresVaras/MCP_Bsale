from config import mcp, MAX_LIMIT
from http_client import _request
from transforms import _slim_cliente, _slim_documento
from monitor import _monitor


async def _buscar_clientes(params: dict) -> list:
    data = await _request("GET", "clients.json", params={**params, "limit": MAX_LIMIT})
    return data.get("items", []) if "error" not in data else []


async def _clientes_por_nombre(nombre: str, lim: int) -> list:
    """Busca por nombre/apellido (substring, insensible a mayúsculas). Soporta nombre completo."""
    toks = [t for t in nombre.lower().split() if len(t) >= 2]
    if not toks:
        return []
    if len(toks) == 1:
        # una palabra puede ser nombre o apellido: busca en ambos y combina
        encontrados = await _buscar_clientes({"firstname": toks[0]}) \
                    + await _buscar_clientes({"lastname": toks[0]})
        vistos, items = set(), []
        for c in encontrados:
            if c.get("id") not in vistos:
                vistos.add(c.get("id"))
                items.append(c)
        return items[:lim]
    # Nombre completo: nombre + apellido (AND); si falla, filtra client-side.
    items = await _buscar_clientes({"firstname": toks[0], "lastname": toks[-1]})
    if not items:
        cand = await _buscar_clientes({"firstname": toks[0]})
        items = [c for c in cand
                 if all(t in f"{c.get('firstName','')} {c.get('lastName','')}".lower() for t in toks)]
    if not items:
        items = await _buscar_clientes({"lastname": toks[-1]})
    return items[:lim]


@mcp.tool()
@_monitor
async def listar_clientes(
    consulta: str = None, nombre: str = None,
    email: str = None, rut: str = None, limite: int = 10,
) -> dict:
    """Busca clientes por nombre, email o RUT. 'consulta' detecta el tipo automáticamente
    (ej: 'juan perez', 'juan@mail.com', '76.063.958-3'). Para responder '¿quién es / cuánto
    compró X?' encuentra primero el cliente aquí."""
    lim = min(max(1, limite), MAX_LIMIT)

    if consulta and not (nombre or email or rut):
        c = consulta.strip()
        if "@" in c:
            email = c
        elif sum(ch.isdigit() for ch in c) >= 6:
            rut = c
        else:
            nombre = c

    if nombre:
        items = await _clientes_por_nombre(nombre, lim)
        return {"total": len(items), "clientes": [_slim_cliente(c) for c in items]}

    params: dict = {"limit": lim, "offset": 0}
    if email: params["email"] = email.strip()
    if rut:   params["code"]  = rut.strip().upper()
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


@mcp.tool()
@_monitor
async def rastrear_historial_cliente(identificador: str) -> dict:
    """Encuentra un cliente (nombre, email o RUT) y devuelve sus últimas 5 compras.
    Ideal para '¿qué/cuánto ha comprado X?'."""
    limpio = identificador.strip()

    if "@" in limpio:
        items = await _buscar_clientes({"email": limpio.lower()})
    elif sum(c.isdigit() for c in limpio) >= 6:
        items = await _buscar_clientes({"code": limpio.upper()})
    else:
        items = await _clientes_por_nombre(limpio, lim=1)

    if not items:
        return {"error": f"No se encontró cliente para: '{identificador}'"}

    cliente = items[0]
    docs_data = await _request("GET", "documents.json", params={
        "clientid": cliente["id"], "limit": 5,
        "orderby": "emissiondate", "order": "DESC",
    })
    compras = [_slim_documento(d) for d in docs_data.get("items", [])] if "error" not in docs_data else []

    return {"cliente": _slim_cliente(cliente), "ultimas_compras": compras}
