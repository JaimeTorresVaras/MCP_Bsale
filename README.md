# 🛒 Bsale MCP Server — Versión Remota

Integración de **Bsale** con **Claude** vía Model Context Protocol (MCP).  
Esta versión soporta **dos modos**: local (stdio) y **remoto (SSE/HTTP para la nube)**.

---

## Herramientas disponibles

| Herramienta | Descripción |
|---|---|
| `listar_clientes` | Buscar clientes por nombre, email o RUT |
| `crear_cliente` | Crear un nuevo cliente |
| `buscar_producto` | Busca por nombre parcial; admite varias palabras en cualquier orden |
| `consultar_stock` | Stock disponible por producto, variante o sucursal |
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

## Solución de problemas

**Error: BSALE_API_TOKEN no configurado**  
→ Verifica que la variable de entorno esté configurada en el panel de Railway/Render.

**Error 401 Unauthorized**  
→ Tu token de Bsale es incorrecto o expiró. Genera uno nuevo desde Bsale.

**Claude no puede conectar**  
→ Verifica que la URL sea pública (HTTPS). Prueba abriendo `https://TU-URL/sse` en el navegador.

**El servidor "duerme" en Render (plan free)**  
→ La primera solicitud puede tardar 30-60 segundos en despertar. Usa Railway para evitar esto.
