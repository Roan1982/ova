# Documentación Técnica del sistema de emergencias

Este documento contiene:
- Bitácora de desarrollo
- Esquema del pipeline (arquitectura y flujo de datos)
- Informe técnico detallado con resultados, análisis crítico y limitaciones
- Contrato (entradas/salidas) y casos borde
- Cómo ejecutar y verificar (comandos útiles)

---

## Bitácora (versión en palabras sencillas)

Aquí tenés un registro claro y sin tecnicismos de lo que se hizo hasta ahora:

- Empezamos armando la estructura básica del proyecto con Django para manejar emergencias y recursos (agentes, hospitales, parkings).
- Definimos cómo va a guardarse la información en la base de datos (qué datos guardamos de emergencias y agentes) y creamos las migraciones correspondientes.
- Implementamos la lógica que decide a qué agente enviar cuando llega una emergencia y cómo calcular la mejor ruta para que llegue rápido.
- Añadimos scripts para generar datos de prueba automáticamente, así es fácil recrear escenarios para probar el sistema.
- Escribimos pruebas automáticas que verifican que los cálculos de rutas y la asignación de recursos funcionan como se espera.
- Creamos plantillas simples para ver un tablero y los detalles de las emergencias en el navegador (interfaz básica para mostrar resultados).
- Añadimos comandos de mantenimiento que permiten poblar datos o actualizar información de transporte desde scripts.
- Decisión clave: mantener todo modular (por partes), de modo que la parte que calcula rutas se pueda cambiar por otra sin romper el resto.

Si querés, puedo transformar esta versión en un documento independiente o en un resumen para presentar a stakeholders.

### Bitácora ampliada (referencias al código)

A continuación se amplía la bitácora con referencias directas al código para entender qué hace cada pieza y cómo encajan.

- Estructura y entrada: `manage.py` y `emergency_app/settings.py` inicializan la aplicación Django y cargan dependencias listadas en `requirements.txt`.

- Modelos principales (`core/models.py`):
   - `Force`, `Vehicle`, `Agent`: representan las fuerzas (Bomberos, SAME, Policía), los vehículos y los agentes. Campos relevantes: ubicaciones actuales (`current_lat`, `current_lon` en `Vehicle`; `lat`, `lon` en `Agent`) y `status` para controlar disponibilidad.
   - `Emergency`: almacena emergencias con `description`, coordenadas (`location_lat`, `location_lon`), `code` (rojo/amarillo/verde) y `priority`. Importante: su método `save()` intenta clasificar la emergencia llamando a `classify_with_ai` (si hay IA disponible) o al clasificador local `classify_emergency`; además, si la emergencia es crítica, activa `process_ia()`.
   - `EmergencyDispatch`: guarda cada despacho (fuerza, vehículo, agente, estado) creado por `ensure_multi_dispatch()` en `Emergency`.
   - `CalculatedRoute`: persiste rutas calculadas (distancia, tiempo estimado, geometría) para auditar y mostrar ETA.

   Referencia rápida: cuando se crea o actualiza una `Emergency`, se ejecuta `Emergency.save()` → `classify_code()` → si corresponde `process_ia()` → `ensure_multi_dispatch()` que crea `EmergencyDispatch` y usa `_find_best_available_vehicle/agent()` para asignar recursos.

- Lógica de ruteo (`core/routing.py`):
   - `RouteOptimizer` es el núcleo: `get_best_route(start, end)` prueba múltiples proveedores en este orden (Mapbox → OpenRoute → OSRM → GraphHopper → FallbackGrid). También aplica ajustes: `adjust_route_for_closures()` (evita cortes de calles consultando `StreetClosure`), `adjust_duration_for_traffic()` (ajusta duración según `TrafficCount`).
   - Utilidades clave: `calculate_distance()` (Haversine), `_generate_grid_path()` (fallback urbano), `find_optimal_assignments()` (itera recursos y pide `get_best_route()` para cada uno, calcula `priority_score`).

   Ejemplo de uso en código: `Emergency._find_best_available_vehicle()` importa `get_route_optimizer()` y llama `optimizer.get_best_route(vehicle_coords, emergency_coords)` para decidir el `best_vehicle` por ETA.

- Cliente de datos externos (`core/transport_client.py`):
   - `BuenosAiresTransportClient` encapsula llamadas a la API de transporte. Métodos: `get_street_closures()`, `get_parking_data()`, `get_traffic_counts()`, `get_transport_alerts()` y `update_*` que persisten esos datos en modelos (`StreetClosure`, `ParkingSpot`, `TrafficCount`, `TransportAlert`).
   - Uso: los management commands (p. ej. `core/management/commands/update_transport_data.py`) o procesos periódicos usan `get_transport_client().update_all_data()` para mantener la DB sincronizada.

- Scripts y población de datos:
   - `populate_test_data.py` crea fuerzas, vehículos y algunas emergencias de ejemplo (útil para desarrollo local).
   - `core/management/commands/seed_emergencies.py` contiene escenarios más complejos y la opción `--with-vehicles` para asegurar recursos base. Ambos scripts permiten levantar escenarios reproducibles para pruebas manuales o demos.

- Flujos y comportamiento observable (cómo encajan las piezas):
   1. Creación de emergencia (por UI o script) → `Emergency.save()` intenta clasificarla.
   2. Si la clasificación apunta a una fuerza o es de alta prioridad, `process_ia()` llama `ensure_multi_dispatch()`.
   3. `ensure_multi_dispatch()` calcula qué fuerzas se necesitan (`_infer_required_forces()`), crea `EmergencyDispatch` por fuerza y usa `_find_best_available_vehicle()` y `_find_best_available_agent()` para asignar recursos. Esas funciones llaman al optimizador de rutas.
   4. El optimizador (`RouteOptimizer.get_best_route`) consulta proveedores externos y modelos internos (cortes, conteos de tránsito) para devolver una ruta ajustada; el resultado se guarda como `CalculatedRoute`.
   5. Cuando la emergencia se resuelve, `Emergency.resolve()` libera agentes/vehículos y marca `CalculatedRoute` con estado `completada`.

- Pruebas (`core/tests.py`, `test_police_routing.py`):
   - Validaciones incluidas: la clasificación IA cae en fallback local si no hay clave; el sistema prioriza vehículos cercanos; al procesar una emergencia se crean dispatches y `CalculatedRoute`; resolver una emergencia libera recursos.
   - Ejemplos de aserciones: `test_process_emergency_assigns_nearest_vehicle` espera que el vehículo más cercano pase a `status='en_ruta'` y que `Emergency.status` cambie a `'asignada'`.

Con esto tenés una versión ampliada de la bitácora que enlaza lo que se hizo con las rutas concretas en el código (archivos y métodos). Si querés, puedo:
- Extraer y formatear las líneas de docstring o comentarios que aparecen en cada archivo para incluirlas literalmente en la documentación.
- Generar un resumen diapositiva (2–3 slides) para presentar al equipo no técnico.

## Módulo de IA: funcionamiento externo (cloud) y simulado (local)

Esta sección explica cómo está implementada la parte de clasificación automática (IA), qué hace el cliente cloud, cuál es el fallback local simulado y cómo probarlos.

Resumen rápido
- Código relevante: `core/llm.py` (cliente cloud y orquestador) y `core/ai.py` (IA simulada / basada en reglas).
- Flujo: la llamada principal usada por el resto del sistema es `classify_with_ai(description)` (definida en `core/llm.py`). Primero intenta usar el proveedor cloud configurado; si falla, cae al fallback local `get_ai_classification_with_response()` en `core/ai.py`.

Arquitectura y responsabilidades
- `core/llm.py` — CloudAIClient y orquestador:
   - `CloudAIClient` detecta el proveedor por la configuración (`AI_PROVIDER` en `settings.py`), soporta `openai` y `ollama`.
   - Para OpenAI: construye un payload con `SYSTEM_PROMPT` (un prompt que obliga a devolver JSON según un esquema definido) y hace POST a la API (`/chat/completions` o el endpoint configurado). Implementa reintentos con backoff exponencial y timeouts.
   - Para Ollama: construye payload y realiza la llamada al endpoint local de Ollama (`OLLAMA_BASE_URL`).
   - La función `_parse_json_content()` sanitiza respuestas (quita bloques de código y busca el JSON) y `classify_with_ai()` normaliza el resultado vía `_normalize_result()` agregando campos estándar: `tipo`, `codigo`, `score`, `razones`, `respuesta_ia`, `recursos`, `recommended_resources` y `fuente`.

- `core/ai.py` — IA simulada / basada en reglas:
   - Implementa `analyze_description()` que aplica diccionarios de palabras clave (severas, moderadas, leves), patrones regex para detectar tipo (médico, bomberos, policial) y suma puntajes.
   - `classify_emergency()` transforma ese puntaje a un `codigo` (rojo/amarillo/verde).
   - `generate_ia_response()` produce un texto de recomendación operativo en castellano, agregando contexto (vulnerables, multiplicidad, lugar sensible).
   - `get_ai_classification_with_response()` devuelve el objeto completo (misma estructura esperada por el sistema) con `recursos` inferidos por `_infer_resource_recommendations()`.

Contrato (entrada/salida)
- Entrada: una cadena de texto `description` (string) que describe la emergencia.
- Salida (dict) — campos normalizados que el resto del sistema consume:
   - `tipo`: 'policial' | 'medico' | 'bomberos'
   - `codigo`: 'rojo' | 'amarillo' | 'verde'
   - `score`: integer (1..100)
   - `razones`: lista de strings con motivos de la clasificación
   - `respuesta_ia`: string con recomendación operativa en castellano
   - `recursos`: lista de objetos { tipo, cantidad, detalle? }
   - `recommended_resources`: duplicado para compatibilidad
   - `fuente`: 'openai'|'ollama'|'local' (indica origen)

Comportamiento y manejo de errores
- Prioridad de uso: si `AI_PROVIDER` (en `settings.py`) apunta a un proveedor soportado, `CloudAIClient.classify()` intentará llamar al proveedor en la nube.
- Reintentos y timeouts: OpenAI/Ollama usan un número de reintentos (`AI_MAX_RETRIES`, con backoff exponencial) y timeout (`AI_TIMEOUT`). Errores de red o respuestas inválidas quedan logueadas y se reintentará hasta agotar intentos.
- Parsing robusto: la respuesta del LLM se limpia por `_sanitize_content()` y `_parse_json_content()` para extraer JSON aun cuando el modelo devuelva texto extra. Si no se puede parsear, se considera fallo.
- Fallback local: si el cliente cloud devuelve None o lanza excepción, `classify_with_ai()` captura el error y llama a `get_ai_classification_with_response()` (`core/ai.py`), que siempre devuelve una estructura válida. En este caso el campo `fuente` se marca como `local`.

Settings relevantes (para `settings.py`)
- `AI_PROVIDER` — 'openai' (por defecto) o 'ollama'.
- `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_API_BASE` — para usar OpenAI.
- `OLLAMA_BASE_URL`, `OLLAMA_MODEL` — para usar Ollama local.
- `AI_TIMEOUT`, `AI_MAX_RETRIES` — timeouts y reintentos.

Cómo probar localmente (PowerShell)
- Forma rápida en Django shell (usa el fallback si no hay API key):

```powershell
cd c:\Users\angel.steklein\Documents\desarrollo\ova\emergency_system
.\.venv\Scripts\Activate.ps1  # si usás virtualenv
python manage.py shell
from core.llm import classify_with_ai, get_ai_status
print(get_ai_status())
print(classify_with_ai("Incendio con humo denso en edificio, varias personas atrapadas"))
```

- Forzar el fallback local: asegurate de que `OPENAI_API_KEY` no esté seteada o pon `AI_PROVIDER='local'` temporalmente en `emergency_app/settings.py`.

Ejemplo de salida (ejemplo simplificado):

```json
{
   "tipo": "bomberos",
   "codigo": "rojo",
   "score": 78,
   "razones": ["Severidad alta: 'incendio masivo' (+60)", "Lugar sensible: 'hospital' (+10)"],
   "respuesta_ia": "Emergencia de bomberos crítica. Despachando múltiples unidades. (Índice de gravedad: 78/100)",
   "recursos": [{"tipo":"camión de bomberos","cantidad":2}],
   "fuente": "local"
}
```

Buenas prácticas y recomendaciones
- Validar las respuestas cloud antes de confiar en cambios automáticos: el código ya guarda la recomendación en `resolution_notes` pero las decisiones finales (por ejemplo asignar vehículos) combinan heurísticas internas.
- Registrar y monitorear `get_ai_status()` en endpoints de health-check para detectar caídas del proveedor cloud y activar alertas.
- Añadir tests unitarios que simulen respuestas JSON malformadas desde el proveedor cloud para verificar que el fallback local se active correctamente.

Tests sugeridos (rápidos)
- Test de integración en `core/tests.py` ya cubre parte del flujo: crear una Emergency y verificar que `resolution_notes` contiene "Clasificación IA" cuando se procesó.
- Agregar tests que mockeen `CloudAIClient.classify` para devolver `None` o JSON inválido y verificar que `get_ai_classification_with_response` se use y `fuente` sea `local`.

Si querés, puedo:
- Añadir ejemplos unitarios (pytest) que mockeen la llamada HTTP a OpenAI/Ollama y verifiquen fallback. 
- Añadir un endpoint pequeño `/ai-status/` (si no existe) que devuelva el `get_ai_status()` en JSON para monitoreo.

## APIs externas y funcionalidades añadidas

APIs / servicios desde los que el sistema obtiene datos o delega cálculo de rutas:

- Mapbox Directions API: opción preferente para cálculo de rutas cuando se configura `MAPBOX_API_KEY`; devuelve rutas con geometría GeoJSON, pasos y estimaciones de tiempo y distancia. (Uso en `core/routing.py` — `get_route_mapbox`).
- OpenRouteService (OpenRoute): usado como alternativa para ruteo si se configura `OPENROUTE_API_KEY`. Devuelve GeoJSON y permite instrucciones y formatos con unidades métricas. (Uso en `core/routing.py` — `get_route_openroute`).
- OSRM (servidores públicos): usado como fallback resiliente (múltiples hosts públicos) cuando no hay API key o los proveedores comerciales fallan. Implementado con backoff y chequeos de geometría. (Uso en `core/routing.py` — `get_route_osrm`).
- GraphHopper: opción adicional si se configura `GRAPHOPPER_API_KEY`, usada como proveedor alternativo en `RouteOptimizer`.
- API Transporte Ciudad de Buenos Aires (api-transporte.buenosaires.gob.ar): fuente de datos de cortes de calles (`StreetClosure`), lugares de estacionamiento (`ParkingSpot`), conteos de tránsito (`TrafficCount`) y alertas de transporte. Consumido por `core/transport_client.py` y actualizado por los management commands (`update_transport_data`).
- OpenAI / Ollama: proveedores para la clasificación IA en `core/llm.py` (OpenAI vía `OPENAI_API_KEY` y posibles bases alternativas, Ollama local vía `OLLAMA_BASE_URL`).

Funcionalidades añadidas y cómo se implementan

- Trazado de rutas con animación:
   - El sistema calcula la geometría de la ruta (GeoJSON LineString) usando `RouteOptimizer.get_best_route()`.
   - La geometría se expone a la vista y al frontend donde se puede animar el trazado (p. ej. usando Leaflet + leaflet-polyline-snakeanim o Mapbox GL JS con interpolación de puntos). En el backend la función `CalculatedRoute.route_geometry` guarda la geometría que alimenta la animación.

- Tiempo estimado de llegada (ETA):
   - `RouteOptimizer` devuelve `duration` (segundos) y `distance` (metros). Se normaliza y guarda en `CalculatedRoute.estimated_time_minutes` y `distance_km`.
   - El endpoint/logic que muestra la emergencia puede presentar `eta = duration / 60` en minutos en el dashboard.

- Onda verde (prioridad de semáforo):
   - Campo `Emergency.onda_verde` se activa automáticamente en `Emergency.save()` cuando la clasificación es `rojo` (prioridad máxima). La lógica pone `onda_verde=True` y `priority=10` para casos críticos.
   - Para despliegues reales, esto se puede integrar con controladores semafóricos o sistemas de gestión de tráfico mediante API específica (no incluida aquí), pero el flag está listo para enviarse a un middleware de señalización.

- Tiempo de respuesta y tracking:
   - Cuando se asigna un vehículo/agente, el sistema guarda `target_lat/target_lon` y cambia `status` a `en_ruta`.
   - `CalculatedRoute` sirve como registro histórico y fuente para calcular progreso: el frontend puede interpolar la posición actual usando `calculated_at`, `estimated_time_minutes`, y la geometría (`route_geometry`). En tests y en `core/tests.py` hay helpers (`_build_vehicle_tracking`) que construyen payloads de tracking.

- Indicadores y métricas por emergencia:
   - `priority`, `reported_at`, `assigned_force`, `assigned_vehicle`, `resolved_at` y `resolution_notes` se usan para calcular tiempos de respuesta (reportado -> asignado, asignado -> en escena, en escena -> resuelto).
   - El sistema registra y actualiza `CalculatedRoute.status` (activa/completada) para medir cumplimiento y tiempos reales.

- Ajustes por tráfico y cortes de calle:
   - Antes de aceptar una ruta, `RouteOptimizer` ejecuta `adjust_route_for_closures()` (verifica `StreetClosure` desde la DB) y `adjust_duration_for_traffic()` (consulta `TrafficCount`) para estimar congestión y, si es necesario, recalcular rutas alternativas.

Notas de implementación
- La animación del trazado y el tracking son principalmente responsabilidad del frontend; el backend provee la geometría, ETA y timestamps necesarios. En `core/tests.py` se incluyen utilidades que simulan el progreso y verifican payloads que el frontend puede consumir.
- Si querés, puedo proveer un ejemplo mínimo de frontend (Leaflet + JS) que consuma `CalculatedRoute.route_geometry` y muestre la animación/ETA en el dashboard.

## 1. Bitácora de desarrollo

Resumen de pasos realizados, herramientas y decisiones técnicas durante el desarrollo del proyecto.

1. Inicialización del proyecto
   - Estructura: aplicación Django llamada `core` dentro del proyecto `emergency_system`.
   - Archivos clave: `manage.py`, `emergency_app/settings.py`, `core/models.py`, `core/routing.py`, `requirements.txt`.
   - Herramientas: Python 3.x, Django (versión en `requirements.txt`), pip, Git.

2. Modelado y migraciones
   - Modelos definidos en `core/models.py` (agentes, hospitales, parkings, emergencias, rutas calculadas, dispatch).
   - Migraciones generadas y versionadas en `core/migrations/` (hasta `0012_emergencydispatch_agent.py`).
   - Decisiones: mantener modelos normalizados, usar FK para relaciones entre emergencias y recursos.

3. Lógica de enrutamiento y transporte
   - Archivos relevantes: `core/routing.py`, `routing.py` en el root, `core/transport_client.py`.
   - Uso: cálculo de rutas desde agentes a emergencias, integración con servicios externos (simulados o reales) para tráfico/tiempos.
   - Decisiones: abstraer cliente de transporte en `transport_client.py` para facilitar mocks en tests.

4. Simulación y generación de datos
   - Scripts: `populate_test_data.py`, `scripts/populate_real_data.py`, `create_police_resources.py`.
   - Decisión: scripts CLI para poblar DB y simular emergencias, facilitar testing reproducible.

5. Pruebas y validación
   - Tests incluidos: `core/tests.py`, `test_police_buenos_aires.py`, `test_police_routing.py`.
   - Decisión: pruebas unitarias para rutas, reasignación de recursos y cálculos críticos.

6. Interfaz y plantillas
   - Templates en `core/templates/core/` para vistas de dashboard, lista de emergencias, detalle.
   - Decisión: separar lógica de presentación de la lógica de negocio; emplear plantillas simples para demo.

7. Automatizaciones y comandos de gestión
   - Management commands: `core/management/commands/seed_emergencies.py` y `update_transport_data.py`.
   - Decisión: tareas programables para poblar y actualizar datos externos.

8. Notas sobre infraestructura y despliegue
   - Arquitectura pensada para ejecutarse en un servidor con PostgreSQL o SQLite para desarrollo.
   - Recomendación: usar Redis/Cache para datos de tráfico en tiempo real en despliegues de producción.

---

## 2. Esquema del pipeline (arquitectura y flujo de datos)

Descripción general:
- Origenes de datos: sensores de tráfico, base de datos interna (agentes, vehículos, hospitales), entrada de emergencias (UI o API), scripts de importación.
- Componentes principales: UI/Views, lógica de negocio (core), motor de enrutamiento (routing), cliente de transporte (transport_client), persistencia (DB), scripts/cron jobs, tests.

Flujo de datos (alto nivel, ASCII):

  [UI/API] --> [Core Views/Controllers] --> [Core Business Logic]
                                         |--> [Routing Engine] --> [Transport Client/API]
                                         |--> [Dispatch Logic] --> [DB Updates]

  [Scripts: populate, seed] --> [DB]
  [Management Commands / Cron] --> [Update transport data] --> [DB Cache]

Componentes y responsabilidades:
- UI/API: recibir emergencias, mostrar dashboard y detalles.
- Core Business Logic: asignar recursos (fuerzas), priorizar emergencias, calcular rutas de respuesta.
- Routing Engine: calcula tiempos y distancias; usa `transport_client.py` para datos reales o simulados.
- DB: almacena modelos, migraciones y resultados (rutas calculadas, dispatch logs).
- Scripts/Jobs: mantenimientos y poblado de datos.

Diagrama de componentes (texto):

  +----------------+
  |    Usuarios    |
  +----------------+
           |
           v
  +----------------+         +------------------+
  |   Web/API      | <-----> |   Templates / UI |
  +----------------+         +------------------+
           |
           v
  +---------------------------+
  |        Django Core        |
  | - Views / Controllers     |
  | - Models                 |
  | - Dispatch Logic         |
  +---------------------------+
           |          |
    Routing Engine    Management Commands
       |                  |
       v                  v
  +------------+      +----------------+
  | Transport  |      |   Scripts /    |
  |  Client    |      |   Cron Jobs    |
  +------------+      +----------------+
           |
           v
        Externals
   (Traffic APIs, Maps)

---

## 3. Informe técnico detallado

Propósito
- Describir comportamiento del sistema, resultados obtenidos durante pruebas y análisis crítico.

Entorno de pruebas
- Sistema operativo durante desarrollo: Windows/macOS/Linux (multi-plataforma); pruebas realizadas localmente con Python.
- Dependencias: listadas en `requirements.txt`. Recomendado: crear un virtualenv y pip install -r requirements.txt.

Resultados principales
- Correcta creación y migración de esquemas de DB (migrations presentes).
- Scripts de población (`populate_test_data.py`) permiten generar escenarios reproducibles.
- Cálculo de rutas implementado y cubierto por tests en `test_police_routing.py`.
- Dispatch y reasignación de recursos probado en `test_police_buenos_aires.py`.

Métricas observadas (ejemplos y cómo obtenerlas)
- Tiempo medio de cálculo de ruta: medir el tiempo de ejecución de funciones en `core/routing.py` usando `timeit` o `pytest --durations`.
- Cobertura de tests: ejecutar suite de tests y medir cobertura (recomendar instalación de pytest-cov).

Análisis crítico
- Fortalezas:
  - Diseño modular: cliente de transporte abstraído, management commands para mantenimiento.
  - Tests y scripts incluidos: facilitan verificación y reproducibilidad.
- Debilidades / Limitaciones:
  - Ausencia de integración real con APIs de mapas en el repo — el `transport_client` puede estar simulado.
  - No hay configuración declarada para despliegue (Docker, CI/CD) en el repo adjunto.
  - Manejo de concurrencia y escala (p. ej. múltiples emergencias simultáneas) no está probado a gran escala.
  - No se observa uso de colas (RabbitMQ, Celery) para trabajo en background; tareas pesadas pueden bloquear requests.

Riesgos técnicos
- Datos de terceros: depender de APIs de tráfico puede introducir latencia y costos.
- Exactitud de tiempos de respuesta: si los datos de tráfico son simulados, la heurística puede no ajustarse a producción.

Limitaciones conocidas
- Simulación limitada: scripts y pruebas se basan en datos estáticos o generados artificialmente.
- Escalabilidad: el diseño actual es suficiente para PoC y pruebas, pero necesita re-arquitectura para producción a gran escala (caching, colas, microservicios).

Recomendaciones
- Integrar un servicio de enrutamiento real (e.g., OSRM, GraphHopper, Google Directions API) y añadir tests de integración.
- Introducir caché (Redis) para respuestas de rutas frecuentes.
- Añadir un worker (Celery) para cálculos de rutas y updates en background.
- Añadir Dockerfile y pipeline CI para test y despliegue.

---

## 4. Contrato: entradas, salidas y modos de error

Contrato (resumen):

- Función: asignar recurso a emergencia
  - Entradas: emergencia_id (int), timestamp (ISO str) opcional
  - Salidas: objeto dispatch (id, agent_id, eta_estimada, ruta)
  - Errores: emergencia no encontrada (404/Exception), sin agentes disponibles (error controlado)

- Función: calcular ruta
  - Entradas: origen (lat, lon), destino (lat, lon), modo Transporte (driving/walking)
  - Salidas: distancia_m, duracion_s, steps (lista)
  - Errores: datos inválidos, API externa no disponible (timeout/429)

- Función: poblar DB desde script
  - Entradas: flags (cantidad agentes, semilla aleatoria)
  - Salidas: resumen del insert (n_created)
  - Errores: violaciones de integridad de DB, duplicados manejados por try/except

Edge cases a cubrir
- Emergencias con coordenadas inválidas o faltantes.
- Agentes en estado no disponible (fuera de servicio, en otra asignación).
- Respuestas parciales del servicio de rutas (sin steps completos).
- Errores transitorios de API: reintentos exponenciales y circuit breaker.

---

## 5. Cómo ejecutar y verificar

Preparación rápida (Windows PowerShell):

1. Crear virtualenv e instalar dependencias

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -r requirements.txt
```

2. Migrar DB y poblar datos de prueba

```powershell
python manage.py migrate; python populate_test_data.py
```

3. Ejecutar tests

```powershell
python -m pytest -q
```

Comprobaciones sugeridas
- Ejecutar `python manage.py runserver` y abrir el dashboard en `http://127.0.0.1:8000/`.
- Revisar logs generados por `seed_emergencies` y `update_transport_data`.

---

## 6. Pasos siguientes y mejoras propuestas

- Generar diagramas gráficos (PlantUML o draw.io) a partir del esquema ASCII.
- Añadir Dockerfile y `docker-compose` para stack (web, db, redis).
- Añadir pruebas de rendimiento y de carga para validar concurrencia.
- Preparar integración con un proveedor de mapas reales y tests de integración.

---

## Anexo: archivos clave referenciados
- `manage.py` — entrada de Django
- `requirements.txt` — dependencias
- `core/models.py`, `core/routing.py`, `core/transport_client.py` — lógica central
- `populate_test_data.py`, `scripts/populate_real_data.py` — scripts de población
- `core/management/commands/seed_emergencies.py` — comandos de mantenimiento


---

Fin del documento.
