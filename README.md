# 🛒 Bsale MCP Server — Versión Remota

Integración de **Bsale** con **Claude** vía Model Context Protocol (MCP).  
Esta versión soporta **dos modos**: local (stdio) y **remoto (SSE/HTTP para la nube)**.

---

## Herramientas disponibles

| Herramienta | Descripción |
|---|---|
| `listar_clientes` | Buscar clientes por nombre, email o RUT |
| `crear_cliente` | Crear un nuevo cliente |
| `buscar_producto` | Busca por nombre exacto o aproximado (fuzzy) |
| `consultar_stock` | Stock disponible por variante o sucursal |
| `top_stock` | Ranking de variantes con más stock |
| `analizar_stock_critico` | SKUs bajo un umbral de reposición |
| `configuracion` | Sucursales, tipos de doc, listas de precio, etc. |
| `listar_documentos` | Ventas/documentos con filtros de fecha |
| `resumen_ventas` | Totales neto/IVA/bruto con desglose por tipo |
| `detalle_documento` | Líneas de un documento específico |
| `rastrear_historial_cliente` | Últimas 5 compras de un cliente |
| `resumen_pagos` | Desglose por medio de pago |
| `ranking_vendedores` | Ventas por vendedor en un período |
| `buscar_variante` | Busca variantes por código, barcode, SKU |
| `precio_variante` | Precio en una lista de precio |
| `costo_variante` | Costo promedio y cálculo de margen |
| `listar_devoluciones` | Devoluciones por período/sucursal |
| `documentos_proveedor` | Facturas de proveedores |
| `listar_despachos` | Despachos/envíos |
| `obtener_detalle_recurso` | Detalle completo de cualquier recurso |

---

## Opción A — Despliegue en Railway (recomendado, 5 min)

### 1. Crear cuenta en Railway
Ve a [railway.app](https://railway.app) y crea una cuenta gratuita.

### 2. Crear nuevo proyecto desde GitHub
1. Sube esta carpeta a un repositorio GitHub (puede ser privado)
2. En Railway: **New Project → Deploy from GitHub repo**
3. Selecciona el repositorio

### 3. Configurar variables de entorno
En el panel de Railway, ve a **Variables** y agrega:

```
BSALE_API_TOKEN = tu_token_de_bsale
MCP_TRANSPORT   = sse
PORT            = 8000
```

### 4. Obtener la URL pública
Railway te da una URL tipo:  
`https://bsale-mcp-production.up.railway.app`

La URL del endpoint SSE será:  
`https://bsale-mcp-production.up.railway.app/sse`

---

## Opción B — Despliegue en Render.com (plan gratuito)

### 1. Crear cuenta en Render
Ve a [render.com](https://render.com) y crea una cuenta.

### 2. Nuevo Web Service
1. **New → Web Service → Connect a repository**
2. Selecciona tu repo con este código
3. Render detectará el `render.yaml` automáticamente

### 3. Configurar variable secreta
En el panel de Render, ve a **Environment** y agrega:
```
BSALE_API_TOKEN = tu_token_de_bsale
```

La URL del endpoint SSE será:  
`https://bsale-mcp.onrender.com/sse`

> ⚠️ El plan gratuito de Render "duerme" después de 15 min de inactividad.  
> Para uso constante usa Railway o un plan pago.

---

## Opción C — Servidor propio / VPS

```bash
# Clonar y entrar al directorio
git clone tu-repo && cd bsale-mcp

# Instalar dependencias
pip install -r requirements.txt

# Correr en modo remoto
BSALE_API_TOKEN=tu_token MCP_TRANSPORT=sse PORT=8000 python server.py
```

Necesitas un proxy reverso (nginx/caddy) con HTTPS para usarlo como conector remoto.

---

## Agregar como Conector en Claude

Una vez desplegado, sigue estos pasos:

### Plan Pro/Max (individual)
1. Ve a [claude.ai/customize/connectors](https://claude.ai/customize/connectors)
2. Haz clic en **"+" → "Add custom connector"**
3. Pega la URL: `https://TU-DOMINIO.railway.app/sse`
4. Haz clic en **"Add"**

### Plan Team/Enterprise
Un Owner debe ir a **Organization settings → Connectors → Add → Custom → Web** y agregar la URL.  
Luego cada miembro conecta desde **Customize → Connectors**.

### Activar por conversación
Haz clic en el botón **"+"** del chat → **"Connectors"** → activa el toggle de Bsale.

---

## Modo local (sin cambios respecto a la versión anterior)

Si quieres seguir usando el servidor localmente con Claude Desktop, funciona igual que antes:

```json
{
  "mcpServers": {
    "bsale": {
      "command": "python",
      "args": ["/RUTA/server.py"],
      "env": {
        "BSALE_API_TOKEN": "TU_TOKEN_AQUI"
      }
    }
  }
}
```

Sin la variable `MCP_TRANSPORT=sse`, el servidor usa stdio por defecto.

---

## Obtener tu Token de API de Bsale

1. Inicia sesión en tu cuenta de Bsale
2. Ve a **Configuración → Aplicaciones → API**
3. Crea o copia tu **Access Token**

---

## Solución de problemas

**Error: BSALE_API_TOKEN no configurado**  
→ Verifica que la variable de entorno esté configurada en el panel de Railway/Render.

**Error 401 Unauthorized**  
→ Tu token de Bsale es incorrecto o expiró. Genera uno nuevo desde Bsale.

**Claude no puede conectar**  
→ Verifica que la URL sea pública (HTTPS). Prueba abriendo `https://TU-URL/sse` en el navegador.

**El servidor "duerme" en Render (plan free)**  
→ La primera solicitud puede tardar 30-60 segundos en despertar. Usa Railway para evitar esto.
