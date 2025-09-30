# Sistema de Emergencias CABA

Este proyecto coordina emergencias para la Ciudad Autónoma de Buenos Aires combinando clasificación asistida por IA y optimización de rutas para asignar los recursos más cercanos y rápidos.

## 🧠 IA en la nube

El motor de clasificación ahora usa un proveedor configurable en la nube (por defecto OpenAI) con respaldo automático a las reglas locales. Configura las siguientes variables de entorno antes de iniciar el servidor:

| Variable | Descripción | Valor por defecto |
|----------|-------------|-------------------|
| `AI_PROVIDER` | Proveedor de IA (`openai` u `ollama`) | `openai` |
| `OPENAI_API_KEY` | API key del proveedor OpenAI | — |
| `OPENAI_MODEL` | Modelo a utilizar | `gpt-4o-mini` |
| `OPENAI_API_BASE` | Endpoint del API | `https://api.openai.com/v1` |
| `AI_TIMEOUT` | Timeout de cada solicitud (s) | `20` |
| `AI_MAX_RETRIES` | Reintentos ante fallos | `3` |

> Si no se define `OPENAI_API_KEY`, el sistema retorna automáticamente a las reglas locales, garantizando disponibilidad.

## Configuración Noticias y Clima

Añade en tu archivo `.env` (o variables de entorno del sistema):

```
# Lista de feeds RSS separados por coma (override opcional)
NEWS_FEEDS=https://www.telam.com.ar/rss2/policiales.xml,https://www.infobae.com/feeds/policiales.xml

# Palabras clave para filtrar (opcional). Si se define, solo titulares que contengan alguna.
NEWS_KEYWORDS=incendio,choque,policía,accidente,rescate

# TTL de caché para noticias (segundos)
NEWS_CACHE_SECONDS=300

# OpenWeatherMap (https://openweathermap.org/api)
WEATHER_API_KEY=TU_API_KEY
WEATHER_LAT=-34.6037
WEATHER_LON=-58.3816
WEATHER_CACHE_SECONDS=600
```

Si no configuras `WEATHER_API_KEY`, se usa automáticamente un fallback sin API key (Open-Meteo) con datos básicos actuales (temperatura y viento). Si esa llamada falla, el panel mostrará "No disponible".

La lógica de recolección está en `core/news.py`.

### Endpoints JSON añadidos

| Endpoint | Descripción | Ejemplo de campo |
|----------|-------------|------------------|
| `/api/news/` | Últimos titulares procesados con severidad | `severity`, `severity_color`, `severity_score` |
| `/api/weather/` | Clima actual + mini pronóstico 6h | `forecast_hours: [{time, temp}]` |
| `/api/incidents/` | Incidentes / tránsito categorizados | `category`, `is_incident` |

### Clasificación de severidad de titulares
Se calcula un puntaje sumando pesos por palabras clave (incend, choque, herido, tirote, etc.). Rangos:

- 0–5: Baja (azul)
- 6–11: Media (ámbar)
- 12+: Alta (rojo)

### Pronóstico breve
Cuando no hay API key se usa Open‑Meteo para estado actual y próximas 6 horas. Con API key se combina OpenWeatherMap (condición e icono) + Open‑Meteo (mini forecast) para consistencia temporal.

### Refresh en interfaz
En el panel derecho:
- Botón ↻ en Clima y Noticias para solicitar JSON nuevamente.
- Botón ▶ rota la primera noticia al final (rotación también automática cada 12s).
Para mantener compatibilidad puedes seguir configurando `OLLAMA_BASE_URL` y `OLLAMA_MODEL`; si `AI_PROVIDER=ollama` el sistema intentará conectarse a ese servidor.

### Feeds de Incidentes / Tránsito

Se agregó soporte para feeds adicionales enfocados en tránsito, clima severo e incidentes urbanos. Variables:

```
# Lista de feeds adicionales (además de NEWS_FEEDS) para incidentes
INCIDENT_FEEDS=https://www.telam.com.ar/rss2/sociedad.xml,https://www.cronista.com/files/rss/section/sociedad.xml
```

Cada titular se clasifica en categorías básicas (accidente, incendio, transito, clima, rescate, general) mediante coincidencia de palabras clave. El endpoint `/api/incidents/` prioriza los ítems con categoría distinta de `general`. Campos adicionales:

| Campo | Descripción |
|-------|-------------|
| `category` | Categoría primaria detectada |
| `categories` | Lista de todas las categorías que coincidieron |
| `is_incident` | Booleano si la categoría principal no es `general` |

Panel en la UI: “Incidentes & Tránsito” con botón ↻ para actualización manual.

## 🚨 Asignación inteligente de recursos

1. La IA clasifica la emergencia y recomienda tipos de recursos (vehículos/agentes) junto con una justificación.
2. El optimizador calcula rutas para los recursos disponibles priorizando por ETA real y distancia.
3. Se asigna automáticamente el móvil más cercano/rápido y se generan despachos adicionales en orden de prioridad.
4. Se produce un informe completo con clasificación, recursos sugeridos y métricas de movilidad (distancia, ETA, onda verde).

Puedes consultar el estado del proveedor en **Core → IA → Estado del sistema** (`/ai/status`) donde se muestran los chequeos de disponibilidad y el resultado de una clasificación de prueba.

## ▶️ Puesta en marcha

1. Crea y activa un entorno virtual (usa `run_system.bat` en Windows o los comandos estándar en otros sistemas).
2. Instala dependencias:

```bash
pip install -r emergency_system/requirements.txt
```

3. Exporta las variables de entorno necesarias (ver tabla anterior).
4. Ejecuta el servidor Django:

```bash
python manage.py runserver
```

## ✅ Pruebas

Para ejecutar el nuevo conjunto de pruebas automatizadas:

```bash
python manage.py test core
```

Las pruebas verifican que el fallback local funcione sin API key y que el flujo de asignación seleccione el móvil más cercano.

## 🛣️ Ruteo, Progreso y Movilidad en Tiempo (Casi) Real

### Flujo General de Rutas

1. Al crear o procesar una emergencia con coordenadas válidas se calculan varias rutas y se persisten en `CalculatedRoute` (no se recalculan de fondo mientras la emergencia no cambie de estado).
2. En la vista detalle (`/detalle/<id>/`) se muestran:
	- Rutas ordenadas por prioridad/ETA (Óptima, Rápida, Backups).
	- Panel de mapa con polilíneas coloreadas y (si aplica) realce de Onda Verde.
3. Al marcar la emergencia como resuelta las rutas quedan “congeladas” (badge 🧊) y no se recalculan más.

### Endpoints Relevantes

| Endpoint | Propósito |
|----------|----------|
| `/api/routes/<id>/` | Cálculo (manual) / recalculo de rutas (si no está resuelta) |
| `/api/stored-routes/<id>/` | Devuelve solo las rutas persistidas (sin recálculo) |
| `/api/mobility/<id>/` | Progreso por recurso + ventanas de onda verde individuales |
| `/api/tracking/` | Seguimiento “genérico” (vehículos / agentes en ruta) |
| `/api/green-wave/<id>/` (POST) | Activa la onda verde (solo código rojo) |
| `/api/traffic-status/` | Estado agregado de ondas e intersecciones |

### Progreso Global vs. Progreso Individual

En el mapa se ve una barra “Progreso hacia la emergencia”. A partir de la versión más reciente el avance agregado se calcula como el **promedio** de los progresos individuales de todos los recursos asignados. Esto refleja mejor el avance global cuando hay varios móviles / agentes en trayecto (un recurso muy retrasado no bloquea que el indicador avance si el resto progresa). 

Históricamente se usó el **mínimo** (interpretación estricta “todos deben llegar” = 100%). Si prefieres volver a ese criterio, cambia una sola línea (ver abajo). También podrías usar percentil (p.ej. P80) o una media ponderada por criticidad del recurso.

Cada recurso tiene su propia tarjeta con:
- Progreso porcentual e interpolación suave entre polls.
- ETA restante estimada (ajustada por factor de tráfico sintético determinístico).
- Distancia total y restante.
- Velocidad efectiva estimada.
- Nivel de tráfico (libre / moderado / congestionado) y factor numérico.
- Lista de intersecciones próximas (si corresponde) con estado de ventana verde (ACTIVA, Próx, Pendiente).

Si no existe aún un tracking real (endpoint `/api/tracking/`), se usa un **fallback de movilidad** que anima un marcador sobre la geometría de la ruta primaria según el progreso calculado en el backend.

### Cálculo de Progreso (Backend)

Para cada `CalculatedRoute`:
1. Se toma el `estimated_time_minutes` original y se ajusta con un `traffic_factor` determinístico por recurso.
2. El progreso = tiempo transcurrido / tiempo total ajustado (acotado a [0,1]).
3. Se interpola la posición sobre la geometría almacenada (GeoJSON `LineString`).
4. Distancia restante = distancia_total * (1 - progreso).
5. ETA restante = distancia_restante / velocidad_ajustada.

### Ventanas de Onda Verde por Recurso

Incluso antes de activar formalmente la Onda Verde, el endpoint `/api/mobility/<id>/` calcula intersecciones relevantes “adelante” del punto actual proyectado para cada recurso y genera ventanas estimadas:
- Filtra intersecciones ya pasadas (threshold ~50m).
- Limita a las próximas 6 intersecciones (payload ligero).
- Usa velocidad promedio adaptativa (>=30 km/h si la estimada es muy baja) para estimar llegada.

El timeline global del panel muestra intersecciones agregadas de ondas activas cercanas a la emergencia. Las tarjetas muestran una vista resumida para su propio trayecto restante.

### Estados Congelados

Cuando la emergencia pasa a `resuelta`:
- Endpoint `/api/routes/<id>/` devuelve rutas con `frozen=true` y no recalcula.
- `/api/mobility/<id>/` fuerza progreso 1.0 (100%) y detiene el polling en el frontend.
- Marcadores quedan en posición final.

### Fallback y Robustez

El sistema intenta siempre degradar elegantemente:
- Si falla cálculo de rutas, genera una ruta de respaldo corta.
- Si `/api/tracking/` no entrega recursos, la UI utiliza los progresos sintéticos de `/api/mobility/`.
- Si la geometría está vacía, el marcador primario no se anima pero las tarjetas siguen mostrando porcentajes calculados.

### Personalización Rápida

Puedes ajustar en `views.py` o settings:
- `MOBILITY_POLL_MS` (frontend) para cambiar el intervalo de polling de movilidad.
- `ROUTING_MAX_RESULTS` para limitar rutas persistidas.
- Semáforos (intersecciones) en `traffic_light_system.py` (`MAJOR_INTERSECTIONS`).

## 🚦 Onda Verde (Green Wave)

Activable para código rojo mediante POST a `/api/green-wave/<id>/`.

Características:
- Se registra una “onda” por vehículo/despacho relevante.
- `traffic_manager` limpia ondas expiradas (>30 min) automáticamente.
- El panel de intersecciones colorea: verde (ventana activa), ámbar (próxima <15s), rojo (fuera de ventana).

## 🔍 Resumen de Variables Involucradas

| Elemento | Fuente | Uso |
|----------|-------|-----|
| `CalculatedRoute` | Base de datos | Persistencia de ruta y tiempos base |
| `traffic_factor` | Función determinística | Simulación de tráfico para ETA dinámica |
| `progress` | Cálculo (elapsed/ajustado) | Animación y porcentaje en tarjetas y barra |
| `route_geometry` | JSON (LineString) | Interpolación de posición y marcadores |
| Intersecciones | `traffic_light_system.py` | Ventanas de onda verde |

---

Si necesitas cambiar la definición de progreso agregado (por ejemplo usar mínimo, percentil o media ponderada), modifica en el template `renderMobility` la línea donde se calcula `globalProgress` (actualmente `avg = progresses.reduce(...)/progresses.length`). Sustituye por:

- Mínimo: `const globalProgress = Math.min(...progresses);`
- Percentil (ej. 0.8): ordena `progresses` y toma el índice `Math.floor(0.8*(n-1))`.
- Media ponderada: define pesos y usa `sum(p_i * w_i)/sum(w_i)`.

Mantén siempre el resultado acotado a `[0,1]`.

Para soporte adicional o mejorar la visualización (íconos específicos por tipo de recurso, clustering, etc.) se pueden abrir issues o extender el template.

