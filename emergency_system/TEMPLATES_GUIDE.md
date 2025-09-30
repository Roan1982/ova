# Guía de Templates y Pantallas

Esta guía describe cada template del sistema, la información presentada, la función de cada botón / acción y recomendaciones de capturas de pantalla para documentación.

## Índice
1. `base.html`
2. `dashboard.html`
3. `home.html` (Centro de Control / Mapa Operativo)
4. `emergency_list.html`
5. `emergency_detail.html`
6. `create_emergency.html`
7. `ai_status.html`
8. `agentes_list.html`
9. `unidades_por_fuerza.html`
10. `facilities_list.html`
11. `hospitales_list.html`

---
## 1. `base.html`
Layout base con:
- Barra de navegación fija (links a Dashboard, Emergencias, Reportar, Agentes, Unidades, Instalaciones, Hospitales, IA, Admin, Mapa).
- Estilos dark theme unificados.
- Bloques extendibles: `extra_head`, `extra_styles`, `content`, `extra_scripts`.
- Footer con timestamp.

Botones/Nav:
- 🚨 Dashboard: vista consolidada.
- Reportar: formulario de nueva emergencia.
- 🤖 IA: estado del motor de clasificación.
- Admin: acceso a Django admin.
- Mapa: centro de control interactivo.

Capturas sugeridas:
- Vista completa barra superior + dropdown / ancho completo.
- Ejemplo de estilo de card base.

---
## 2. `dashboard.html`
Panel estratégico resumido.

Secciones:
1. Métricas generales (Emergencias activas, Vehículos, Agentes, Camas disponibles).
2. Emergencias activas por prioridad (rojo / amarillo / verde).
3. Estado de intervenciones (Pendientes, Asignadas, En curso, Despachos activos).
4. Estado por fuerza (tabla con vehículos y agentes + barras de disponibilidad).
5. Recursos hospitalarios (capacidad y porcentaje libre).
6. Accesos rápidos.
7. Timestamp de última actualización (auto-refresh 30s) + botón 🔄.

Botones:
- 🔄 Actualizar: reload de la página.
- Cards Acceso Rápido: navegación por click.

Interacciones dinámicas:
- Parpadeo (`critical-blink`) en valores críticos (emergencias rojas o muchas activas).

Capturas sugeridas:
- Métricas superiores.
- Cards de prioridad.
- Tabla de fuerzas (una fila expandida visible).
- Sección hospitalaria.
- Accesos rápidos.

---
## 3. `home.html` (Centro de Control)
Pantalla operativa integral con mapa interactivo y panel lateral.

Contenido principal:
- Mapa Leaflet (emergencias, agentes (movimiento simulado), instalaciones, hospitales, rutas, comunas).
- Controles de capas (botones toggle): Emergencias, Agentes, Instalaciones, Hospitales, Rutas, Comunas.
- Botones de acción: 🎯 Centrar, 🧹 Limpiar rutas, 🔄 Redistribuir, 🔍 Test rutas.
- Ticker superior de actividad (3 items rotando).

Panel lateral (aside):
1. Clima + mini pronóstico (↻ refrescar).
2. Noticias (↻ refrescar, ▶ rotar item, severidad color).
3. Incidentes & Tránsito (↻ refrescar).
4. Estado Operativo (contadores emergencias / agentes / instalaciones / comunas).
5. Leyenda (códigos y tipos de recurso).
6. Actividad reciente (log incremental).
7. Control de Tracking en vivo (cuando hay datos) con slider histórico, play/pause, navegación ⏮️ ⏭️.

Popups de emergencia en el mapa:
- Datos: ID, descripción, dirección, estado, tiempo, fuerza asignada, bandera de onda verde.
- Botones dentro del popup:
  - 🗺️ Calcular Rutas: llama `/api/routes/<id>/`.
  - 📦 Mostrar Rutas: muestra persistidas (`/api/stored-routes/`).
  - ⚡ Asignar Óptimo: (placeholder si existe backend).
  - 🚦 Onda Verde (si código rojo): activa semaforización prioritaria.
  - 👁️ Detalle: navega a detalle.

Ruteo:
- `Calcular Rutas` selecciona un subconjunto priorizado (función `selectRoutesForDisplay`).
- `Mostrar Rutas` limpia y pinta sólo las persistidas.
- Fallback: crea ruta simple línea base→emergencia si API falla.
- Animación de dash en polilíneas.

Tracking tiempo real:
- Marcadores con gradiente y halo (más intenso para código rojo).
- Trail punteado histórico.
- Popup con progreso, ETA, tráfico.
- Panel de control: histórico (hasta 30 frames), slider y estado EN VIVO/PAUSADO.

Botones clave (barra mapa):
- 🧹 Limpia rutas y tracking.
- 🔄 Redistribuye (POST `/api/redistribute/` → feedback en ticker).
- 🔍 Test: prueba API de rutas con emergencia fija y muestra ruta demo.

Eventos auto:
- Movimiento simulado de agentes cada 15s.
- Rotación noticias cada 12s.
- Update de ticker cada 20s.

Capturas sugeridas:
- Vista mapa + panel lateral completo.
- Popup emergencia abierto con botones.
- Rutas dibujadas (varios colores).
- Activación “Onda Verde” (ruta en verde + semáforos marcados).
- Panel tracking con slider y marcadores de ruta.
- Panel clima + noticias + incidentes.
- Leyenda.

---
## 4. `emergency_list.html`
Listado segmentado en tres bloques:
1. Pendientes (sin procesar IA) – borde ámbar, badge SIN PROCESAR.
2. Activas procesadas (con o sin onda verde, con badge IA si tuvo clasificación).
3. Finalizadas (opacidad reducida, estado RESUELTA).

Elementos por tarjeta:
- Código (tag color), descripción, dirección, estado, fuerza / vehículo asignado (si aplica), fecha reporte, prioridad.
- Botones acción:
  - 🤖 Procesar con IA (pendientes).
  - 👁️ Ver Detalle.
  - ✅ Resolver (en activas).

Resumen estadístico inferior con totales.

Capturas sugeridas:
- Sección “Pendientes” con al menos una.
- Sección “Activas” con emergencia roja + badge ONDA VERDE.
- Sección “Finalizadas”.
- Resumen inferior.

---
## 5. `emergency_detail.html`
Pantalla focal de una emergencia con ruteo + movilidad multi-recurso.

Secciones:
- Header con ID, código (tag), estado, fuerza / vehículo asignado, dirección.
- Badge 🧊 RUTAS CONGELADAS si resuelta.
- Panel principal “Mapa Operativo”: botones superiores y leyenda.
  - Botones:
    - 🔄 Recalcular Rutas (deshabilitado si resuelta).
    - 🚦 Activar Onda Verde (si código rojo y no activa).
    - 🎯 Centrar.
- Barra global de progreso + estadísticas (distancia recorrida/restante, ETA, velocidad, recursos en ruta) + sparkline histórico.
- Timeline de ventana verde agregada (intersecciones próximas) con estado (Activa / En Xs / Pendiente).
- Cards de rutas (óptima, rápida, backups) con score y proveedor.
- Bloque “📡 Movilidad por Recurso”: cada card incluye progreso, ETA, distancia restante, velocidad, factor tráfico + mini timeline por intersecciones próximas.
- Informe IA (bloque coloreado) + notas de resolución.
- Lista de despachos (force, vehículo, estado, timestamp).
- Rutas calculadas (cards con métrica distancia/tiempo/score, status, completado).
- Form para marcar como resuelta (si no lo está).

Dinámica clave:
- Progreso global = promedio de progresos individuales.
- Fallback animado si no hay tracking real: marcador se interpola.
- Interpolación suave tracking (30fps) + sparkline histórico.
- Cambio de color de rutas según tráfico dinámico.

Capturas sugeridas:
- Mapa con rutas + barra progreso + timeline onda verde.
- Cards de movilidad (varias columnas).
- Popup de marcador primario (dot azul). 
- Informe IA.
- Cards de rutas calculadas.

---
## 6. `create_emergency.html`
Formulario de reporte con mapa clickeable y autocomplete Nominatim.

Elementos:
- Mapa inicial centrado en CABA.
- Click en mapa: coloca marcador, rellena lat/lon ocultos y hace reverse geocode para campo dirección.
- Input “Dirección (buscar)” con sugerencias en dropdown.
- Form estándar de Django (`form.as_p`) incluyendo descripción, tipo, código, prioridad (según modelo).
- Botón Enviar.

Capturas sugeridas:
- Vista inicial mapa + formulario vacío.
- Dropdown autocomplete abierto.
- Marcador colocado y dirección autocompletada.

---
## 7. `ai_status.html`
Estado operativo del sistema de clasificación.

Secciones:
1. Estado general (proveedor cloud, IA local, sistema activo, último error).
2. Configuración (proveedor, modelo, endpoint, si hay API key).
3. Test de clasificación (entrada fija + resultado estructurado + fuente).
4. Capacidades y flujo (listas explicativas).
5. Botones: Volver al Dashboard, 🔄 Actualizar Estado (reload).

Capturas sugeridas:
- Estado general con indicadores verde/rojo.
- Resultado test (JSON pretty) y respuesta IA.
- Configuración (API key presente / ausente).

---
## 8. `agentes_list.html`
Listado tabular filtrable de agentes.

Elementos:
- Estadísticas superiores (disponibles, en ruta, ocupados, en escena, total).
- Filtros select por fuerza y estado (filtran filas con JS). 
- Tabla con: Nombre, Fuerza, Rol, Estado (color), Vehículo asignado, Coordenadas.

Capturas sugeridas:
- Stats + filtros visibles.
- Tabla con diferentes estados coloreados.
- Ejemplo de filtro aplicado (algunas filas ocultas).

---
## 9. `unidades_por_fuerza.html`
Unidades vehiculares agrupadas por fuerza.

Contenido por fuerza:
- Header con nombre + total + % disponible.
- Stats (disponibles / en ruta / ocupados).
- Tabla: Tipo, Estado (color), Coordenadas (o Sin ubicación).

Capturas sugeridas:
- Una fuerza expandida con stats + tabla.
- Varias fuerzas en la misma pantalla (scroll parcial).

---
## 10. `facilities_list.html`
Listado de instalaciones (comisarías, cuarteles, bases tránsito, hospitales) con filtros.

Elementos:
- Estadísticas globales (total + conteo por tipo).
- Barra de filtros (cada tipo con contador, botón activo resaltado).
- Tabla: Instalación, Tipo (badge), Fuerza, Dirección, Coordenadas.
- Stats extra: Con coordenadas / Sin coordenadas / Cobertura geográfica.

Capturas sugeridas:
- Filtros (uno activo).
- Tabla con mezcla de tipos (mostrar badges diferentes).
- Stats adicionales de cobertura.

---
## 11. `hospitales_list.html`
Capacidad hospitalaria y ocupación.

Elementos:
- Stats globales (hospitales, camas totales, ocupadas, disponibles, ocupación promedio).
- Tabla: Hospital, Dirección, Capacidad, Estado Actual (ocupadas/disponibles), % ocupación (barra), Ubicación.
- Clasificación ocupación (Normal / Medio / Alto / Crítico).
- Resumen por categoría de ocupación.

Capturas sugeridas:
- Stats superiores.
- Tabla con al menos un hospital en cada umbral de ocupación.
- Resumen inferior por tramos.

---
## Recomendaciones Generales para Screenshots
- Modo oscuro activo (colores ya optimizados).
- Resolución mínima sugerida: 1600×900 para ancho completo.
- Ocultar datos sensibles (si hubieran) antes de compartir.
- Añadir numeración sobre screenshots si se referenciarán en un documento (p.ej. Fig 3.1, Fig 3.2).
- Para animaciones (rutas, tracking), capturar: estado inicial, durante desplazamiento, estado final.

## Checklist de Capturas (Resumen)
| Template | Capturas Clave |
|----------|----------------|
| base | Barra navegación + card base |
| dashboard | Métricas, prioridad, tabla fuerzas, hospital, accesos |
| home | Mapa completo, popup emergencia, rutas, onda verde, tracking panel, panel lateral (clima/noticias) |
| emergency_list | Secciones: pendientes, activas (con onda verde), finalizadas, resumen |
| emergency_detail | Mapa + barra progreso, movilidad por recurso, timeline onda verde, informe IA, rutas calculadas |
| create_emergency | Mapa vacío, autocomplete abierto, marcador puesto |
| ai_status | Estado proveedores, test exitoso, config sin/sí API key |
| agentes_list | Stats + filtros, tabla con colores, filtro aplicado |
| unidades_por_fuerza | Fuerza con stats + tabla |
| facilities_list | Filtros activos + tabla + stats cobertura |
| hospitales_list | Stats + tabla multiumbral + resumen por ocupación |

---
**Fin de la guía.**
