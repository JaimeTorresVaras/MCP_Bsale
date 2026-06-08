from config import mcp, MAX_LIMIT
from http_client import _request
from transforms import _slim_cliente, _slim_documento
from monitor import _monitor


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
