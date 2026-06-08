import os
import sys
import logging
from pathlib import Path
from mcp.server.fastmcp import FastMCP

TRANSPORT = os.getenv("MCP_TRANSPORT", "stdio").strip().lower()

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [bsale] %(levelname)s %(message)s",
)
log = logging.getLogger("bsale")

SSE_HOST = os.getenv("HOST", "0.0.0.0")
SSE_PORT = int(os.getenv("PORT", "8000"))

mcp = FastMCP(
    "bsale",
    host=SSE_HOST if TRANSPORT == "sse" else "127.0.0.1",
    port=SSE_PORT,
)

BSALE_TOKEN = os.getenv("BSALE_API_TOKEN", "").strip()
BASE_URL    = "https://api.bsale.cl/v1"
TIMEOUT     = 30.0
MAX_LIMIT   = 50
MAX_PAGES   = 20

_log_path_str = os.getenv("LOG_FILE", "")
LOG_FILE = Path(_log_path_str) if _log_path_str else (
    Path(__file__).parent / "bsale_mcp.log" if TRANSPORT == "stdio" else None
)

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
    key = " ".join(nombre.lower().split())
    return VENDEDOR_CANAL.get(key)
