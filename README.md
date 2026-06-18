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
| `top_stock` | Ranking de productos con más stock (con nombre) |
| `analizar_stock_critico` | Productos bajo un umbral de reposición (con nombre) |
| `analisis_producto` | Stock + costo + precio + margen + capital invertido de un producto |
| `reposicion_sugerida` | Qué reponer primero (stock bajo ordenado por margen) |
| `ranking_rentabilidad` | Productos por margen % (más/menos rentables) |
| `valorizacion_inventario` | Capital invertido en stock (cantidad × costo) |
| `configuracion` | Sucursales, tipos de doc, listas de precio, etc. |
| `listar_documentos` | Ventas/documentos con filtros de fecha |
| `resumen_ventas` | Totales neto/IVA/bruto con desglose por tipo |
| `detalle_documento` | Líneas de un documento específico |
| `rastrear_historial_cliente` | Últimas 5 compras de un cliente |
| `resumen_pagos` | Desglose por medio de pago |
| `ranking_vendedores` | Ventas por vendedor en un período |
| `buscar_variante` | Busca variantes por código, barcode, SKU |
| `precio_variante` | Precio de venta (neto y bruto) de una variante |
| `costo_variante` | Costo, valorización en inventario y margen de una variante |
| `listar_devoluciones` | Devoluciones por período/sucursal |
| `documentos_proveedor` | Facturas de proveedores |
| `listar_despachos` | Despachos/envíos |
| `obtener_detalle_recurso` | Detalle completo de cualquier recurso |

---

## Lenguaje natural

Las herramientas están pensadas para preguntas breves y cotidianas:

- **Fechas:** acepta `hoy`, `ayer`, `semana`, `mes`, `mes_pasado`, `año`, `ultimos_7`, `ultimos_30`, además de `YYYY-MM-DD` y `YYYY-MM`. Sin fecha, los resúmenes usan el **mes en curso** (zona horaria de Chile).
- **Productos:** búsqueda por nombre parcial y varias palabras en cualquier orden (ej: *"vasos frozen"*).
- **Clientes:** por nombre, apellido, email o RUT (coincidencia parcial).
- **Stock:** por nombre de producto (`consultar_stock` con `producto_id`), con nombres de sucursal.
- **Análisis de rentabilidad:** Bsale entrega costo (`averageCost`) y valorización (`totalCost`); con eso se calcula margen y capital invertido. Para preguntas como *"analiza el vaso frozen"*, *"¿cuánto margino en X?"*, *"¿qué reponer primero?"*, *"¿dónde tengo la plata parada?"*. Nota: productos sin costo cargado en Bsale se muestran sin margen (no como 100%).

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
