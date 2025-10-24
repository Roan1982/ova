# Sistema de Emergencias CABA - Knowledge Source para Watson Orchestrate

## Información General del Sistema

### Propósito
Sistema integral de gestión de emergencias para la Ciudad Autónoma de Buenos Aires (CABA) que integra:
- Clasificación automática de emergencias mediante IA
- Optimización de rutas multi-proveedor
- Gestión de recursos (vehículos, agentes, instalaciones)
- Sistema de onda verde para emergencias críticas
- Integración con APIs de transporte y noticias

### Tecnologías
- **Backend**: Django 5.2.5, Python 3.12
- **Base de datos**: SQLite (desarrollo), compatible con PostgreSQL
- **Frontend**: Leaflet.js, JavaScript vanilla
- **IA**: OpenAI, Ollama, Watson Orchestrate (configurable)
- **Ruteo**: OSRM, OpenRouteService, Mapbox, GraphHopper

---

## Estructura del Proyecto

```
emergency_system/
├── manage.py                      # Django CLI
├── requirements.txt               # Dependencias Python
├── db.sqlite3                     # Base de datos
├── emergency_app/                 # Configuración principal
│   ├── settings.py               # Configuración global
│   ├── urls.py                   # URLs raíz
│   ├── wsgi.py / asgi.py        # Servidores
├── core/                          # Aplicación principal
│   ├── models.py                 # Modelos de datos
│   ├── views.py                  # Vistas y APIs
│   ├── urls.py                   # URLs de la app
│   ├── forms.py                  # Formularios Django
│   ├── ai.py                     # Clasificación local
│   ├── llm.py                    # Integración IA cloud
│   ├── routing.py                # Motor de ruteo
│   ├── news.py                   # Integración noticias
│   ├── transport_client.py       # API de transporte BA
│   ├── templates/core/           # Templates HTML
│   ├── management/commands/      # Comandos custom
│   │   ├── seed_emergencies.py  # Datos de prueba
│   │   └── update_transport_data.py
│   └── migrations/               # Migraciones DB
├── scripts/
│   └── populate_real_data.py     # Población inicial
├── traffic_light_system.py       # Sistema onda verde
├── demo_emergency_parking.py     # Demo narrada
└── routing.py                     # Optimizador de rutas
```

---

## Modelos de Datos Principales

### Emergency (Emergencia)
```python
{
    "id": int,
    "code": "rojo|amarillo|verde",  # Criticidad
    "priority": int,                 # 10=crítica, 5=urgente, 1=leve
    "description": str,
    "address": str,
    "location_lat": float,
    "location_lon": float,
    "status": "pendiente|asignada|resuelta",
    "assigned_force": FK(Force),
    "assigned_vehicle": FK(Vehicle),
    "onda_verde": bool,             # Onda verde activa
    "reported_at": datetime,
    "resolved_at": datetime,
    "resolution_notes": str,
    "ai_response": str              # Clasificación IA
}
```

### Force (Fuerza)
Tipos: `Bomberos`, `SAME`, `Policía`, `Tránsito`
```python
{
    "id": int,
    "name": str,
    "contact_info": str,
    "created_at": datetime
}
```

### Vehicle (Vehículo)
```python
{
    "id": int,
    "force": FK(Force),
    "type": str,                    # Ambulancia, Patrulla, etc.
    "current_lat": float,
    "current_lon": float,
    "target_lat": float,
    "target_lon": float,
    "home_facility": FK(Facility),
    "status": "disponible|en_ruta|ocupado"
}
```

### Agent (Agente)
```python
{
    "id": int,
    "name": str,
    "force": FK(Force),
    "role": str,
    "status": "disponible|en_ruta|en_escena|ocupado|fuera_servicio",
    "assigned_vehicle": FK(Vehicle),
    "lat": float, "lon": float,
    "target_lat": float, "target_lon": float,
    "home_facility": FK(Facility)
}
```

### CalculatedRoute (Ruta Calculada)
```python
{
    "id": int,
    "emergency": FK(Emergency),
    "resource_id": str,             # "vehicle_123"
    "resource_type": str,           # "Ambulancia - SAME"
    "distance_km": float,
    "estimated_time_minutes": float,
    "priority_score": float,
    "route_geometry": json,         # GeoJSON LineString
    "status": "activa|completada|cancelada",
    "calculated_at": datetime,
    "completed_at": datetime
}
```

### EmergencyDispatch (Despacho)
```python
{
    "id": int,
    "emergency": FK(Emergency),
    "force": FK(Force),
    "vehicle": FK(Vehicle),
    "agent": FK(Agent),
    "status": "despachado|en_ruta|en_escena|finalizado",
    "created_at": datetime
}
```

### Facility (Instalación)
Tipos: `comisaria`, `cuartel`, `base_transito`
```python
{
    "id": int,
    "name": str,
    "kind": str,
    "force": FK(Force),
    "address": str,
    "lat": float, "lon": float
}
```

### Hospital
```python
{
    "id": int,
    "name": str,
    "address": str,
    "total_beds": int,
    "occupied_beds": int,
    "available_beds": int (property),
    "lat": float, "lon": float
}
```

### Modelos de Transporte (Integración API BA)

**StreetClosure**: Cortes de calles
```python
{
    "external_id": str,
    "name": str,
    "closure_type": "total|parcial|alternado|restringido",
    "lat": float, "lon": float,
    "geometry": json,               # GeoJSON
    "start_date": datetime,
    "end_date": datetime,
    "is_active": bool
}
```

**ParkingSpot**: Estacionamientos
```python
{
    "external_id": str,
    "name": str,
    "spot_type": "street|garage|lot|emergency",
    "total_spaces": int,
    "available_spaces": int,
    "is_paid": bool,
    "is_active": bool
}
```

**TrafficCount**: Conteos de tránsito
```python
{
    "external_id": str,
    "location_name": str,
    "count_type": "vehicle|speed|occupancy",
    "count_value": int,
    "unit": str,                    # vehicles, km/h, percentage
    "timestamp": datetime
}
```

**TransportAlert**: Alertas de transporte
```python
{
    "external_id": str,
    "title": str,
    "alert_type": "closure|accident|construction|event|weather|other",
    "severity": "low|medium|high|critical",
    "start_date": datetime,
    "end_date": datetime,
    "is_active": bool
}
```

---

## APIs y Endpoints

### Frontend / Pantallas

| URL | Descripción |
|-----|-------------|
| `/` | Dashboard principal con mapa interactivo |
| `/create/` | Formulario de reporte de emergencia |
| `/list/` | Lista de emergencias (pendientes/asignadas/resueltas) |
| `/detalle/<id>/` | Vista detallada de emergencia |
| `/agentes/` | Lista de agentes por fuerza |
| `/hospitales/` | Lista de hospitales y disponibilidad |
| `/instalaciones/` | Lista de instalaciones (comisarías, cuarteles) |
| `/dashboard/` | Dashboard estadístico |
| `/ai-status/` | Estado del sistema de IA |

### APIs JSON

#### Emergencias y Ruteo
```
GET  /api/routes/<emergency_id>/
     Calcula/recalcula rutas para emergencia
     Response: {
       success: bool,
       routes: [{
         resource_id: str,
         resource_type: str,
         distance: str,
         duration: str,
         geometry: GeoJSON,
         score: float,
         coordinates: [[lat, lon]],
         is_dispatch: bool
       }],
       emergency: {...},
       green_wave_active: bool
     }

GET  /api/stored-routes/<emergency_id>/
     Devuelve rutas persistidas sin recalcular
     Response: {success: bool, routes: [...]}

GET  /api/mobility/<emergency_id>/
     Progreso de recursos, ETA ajustada, intersecciones
     Response: {
       success: bool,
       frozen: bool,
       resources: [{
         resource_id: str,
         progress: float (0-1),
         eta_minutes: float,
         traffic: {level: str, factor: float},
         intersections: [...]
       }]
     }

GET  /api/tracking/
     Seguimiento en tiempo real de todos los recursos
     Response: {
       success: bool,
       tracking_data: [{
         id: str,
         type: "vehicle"|"agent",
         position: {lat: float, lon: float},
         emergency_id: int,
         eta_seconds: int
       }]
     }
```

#### Onda Verde
```
POST /api/green-wave/<emergency_id>/
     Activa onda verde para emergencia código rojo
     Response: {
       success: bool,
       message: str,
       total_intersections: int,
       results: [...]
     }

GET  /api/traffic-status/
     Estado de semáforos y ondas verdes activas
     Response: {
       success: bool,
       active_waves: int,
       waves_data: [...]
     }
```

#### Noticias y Datos Externos
```
GET  /api/news/
     Últimas noticias clasificadas por severidad
     Response: {success: bool, items: [...]}

GET  /api/weather/
     Clima actual y pronóstico
     Response: {success: bool, weather: {...}}

GET  /api/incidents/
     Incidentes y alertas de tránsito
     Response: {success: bool, items: [...]}
```

#### Gestión de Recursos
```
POST /api/redistribute-resources/
     Redistribuye recursos evitando zonas problemáticas
     Response: {success: bool, message: str}

GET  /api/route-details/<emergency_id>/
     Detalles completos de ruta (recurso, distancia, semáforos)
     Response: {success: bool, route_details: {...}}
```

#### Demo (Desarrollo)
```
GET  /demo/presentation/
     Demo guiada con narración

GET  /api/demo/calculated_route/
     Ruta mock densificada para demo

GET  /demo/sync/state/
POST /demo/sync/state/update/
     Sincronización estado demo CLI ↔ frontend
```

---

## Sistema de Clasificación IA

### Schema JSON Esperado
```json
{
  "tipo": "policial|medico|bomberos",
  "codigo": "rojo|amarillo|verde",
  "score": 0-100,
  "razones": ["razón 1", "razón 2"],
  "respuesta_ia": "Recomendación operativa",
  "recursos": [
    {
      "tipo": "Ambulancia|Patrulla|Camión de Bomberos",
      "cantidad": 1-10,
      "detalle": "Descripción opcional"
    }
  ]
}
```

### Prompt del Sistema (SYSTEM_PROMPT)
```
Eres un clasificador de emergencias para la Ciudad Autónoma de Buenos Aires.
Sigue exactamente estas instrucciones y responde en JSON válido contra el esquema:
{schema}

Incluye un campo opcional 'recursos' con lista de objetos: tipo, cantidad, detalle.
El campo 'respuesta_ia' debe contener una recomendación operativa corta en castellano.
No agregues texto fuera del JSON, no uses comillas curvas ni bloques ``` y evita texto introductorio.
```

### Flujo de Clasificación

1. **Crear emergencia** → `Emergency.save()` activa `classify_code()`
2. **`classify_code()`** intenta:
   - `classify_with_ai(description)` → Llama cloud LLM
   - Si falla → `classify_emergency(description)` → Fallback local
3. **Cloud LLM** (`core/llm.py`):
   - `CloudAIClient.classify(description)`
   - Proveedores soportados: `openai`, `ollama`, `watson` (por implementar)
   - Retry logic: 3 intentos con backoff exponencial
4. **Fallback local** (`core/ai.py`):
   - Reglas basadas en keywords
   - Siempre retorna clasificación válida

### Proveedores de IA Configurados

**OpenAI** (por defecto):
```python
AI_PROVIDER = 'openai'
OPENAI_API_KEY = env('OPENAI_API_KEY')
OPENAI_MODEL = 'gpt-4o-mini'
OPENAI_API_BASE = 'https://api.openai.com/v1'
```

**Ollama** (local):
```python
AI_PROVIDER = 'ollama'
OLLAMA_BASE_URL = env('OLLAMA_BASE_URL')
OLLAMA_MODEL = 'gemma:4b'
```

**Watson Orchestrate** (pendiente integración):
```python
AI_PROVIDER = 'watson'
WATSON_API_KEY = env('WATSON_API_KEY')
WATSON_MODEL = 'default'
WATSON_API_BASE = 'https://api.watson-orchestrate.ibm.com/v1'
```

---

## Sistema de Ruteo Multi-Proveedor

### RouteOptimizer (core/routing.py)

**Proveedores soportados:**
1. **OSRM** (público, sin API key)
2. **OpenRouteService** (requiere API key)
3. **Mapbox** (requiere API key)
4. **GraphHopper** (requiere API key)
5. **Fallback Grid** (cálculo local)

**Método principal:**
```python
def get_best_route(start_coords, end_coords) -> dict:
    """
    Returns: {
        'provider': str,
        'distance': float (metros),
        'duration': float (segundos),
        'geometry': GeoJSON LineString,
        'steps': list
    }
    """
```

**Características:**
- Prueba múltiples hosts OSRM si uno falla
- Ajusta rutas para evitar cortes de calles activos
- Calcula tráfico simulado basado en hora del día
- Caché LRU para evitar recálculos
- Modo offline: `ROUTING_OFFLINE=1`

**Límites geográficos (CABA):**
```python
CABA_BOUNDS = {
    'min_lat': -34.7536,
    'max_lat': -34.5265,
    'min_lon': -58.5314,
    'max_lon': -58.3309
}
```

### Función de Cálculo de Rutas para Emergencia

```python
def calculate_emergency_routes(emergency) -> list:
    """
    Calcula rutas óptimas para emergencia.
    
    Returns: [
        {
            'resource': {
                'id': str,
                'name': str,
                'type': 'vehicle'|'agent'
            },
            'route_info': {
                'distance': float,
                'duration': float,
                'geometry': GeoJSON
            },
            'distance_km': float,
            'estimated_arrival': float (minutos),
            'priority_score': float
        }
    ]
    """
```

**Priorización:**
- Vehículos con ETA < 10 min: +50 puntos
- Código rojo: multiplica por 0.7
- Onda verde: multiplica por 0.6

---

## Sistema de Onda Verde

### Ubicación
`traffic_light_system.py` (raíz del proyecto)

### Intersecciones Principales (MAJOR_INTERSECTIONS)
```python
[
    {"name": "9 de Julio y Corrientes", "lat": -34.6037, "lon": -58.3816},
    {"name": "Callao y Santa Fe", "lat": -34.5956, "lon": -58.3925},
    {"name": "Libertador y Figueroa Alcorta", "lat": -34.5780, "lon": -58.4067},
    # ... total 20 intersecciones
]
```

### TrafficManager (Singleton)

**Métodos principales:**
```python
def activate_green_wave(resource_id, route_geometry, duration_seconds):
    """
    Activa onda verde para recurso en ruta.
    
    Args:
        resource_id: str
        route_geometry: GeoJSON LineString
        duration_seconds: float
    
    Returns: {
        'success': bool,
        'intersections': [
            {
                'name': str,
                'lat': float, 'lon': float,
                'green_start': datetime,
                'green_end': datetime,
                'priority': int
            }
        ]
    }
    """

def deactivate_green_wave(resource_id):
    """Desactiva onda verde de un recurso."""

def get_active_waves():
    """Retorna ondas verdes activas con estado."""
```

### Función Helper
```python
def activate_emergency_green_wave(emergency) -> dict:
    """
    Activa onda verde para todos los recursos de emergencia código rojo.
    
    Args:
        emergency: Emergency instance
    
    Returns: {
        'success': bool,
        'message': str,
        'total_intersections': int,
        'results': [...]
    }
    """
```

---

## Configuración (settings.py)

### Seguridad (⚠️ REQUIERE ACTUALIZACIÓN)
```python
SECRET_KEY = env('SECRET_KEY', 'django-insecure-default')  # ⚠️ Hardcoded actualmente
DEBUG = env('DEBUG', 'False') == 'True'                    # ⚠️ True actualmente
ALLOWED_HOSTS = env('ALLOWED_HOSTS', '').split(',')         # ⚠️ [] actualmente
```

### Base de Datos
```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}
```

### IA Cloud
```python
AI_PROVIDER = env('AI_PROVIDER', 'openai')
AI_TIMEOUT = int(env('AI_TIMEOUT', '20'))
AI_MAX_RETRIES = int(env('AI_MAX_RETRIES', '3'))

OPENAI_API_KEY = env('OPENAI_API_KEY')
OPENAI_MODEL = env('OPENAI_MODEL', 'gpt-4o-mini')
OPENAI_API_BASE = env('OPENAI_API_BASE', 'https://api.openai.com/v1')

OLLAMA_BASE_URL = env('OLLAMA_BASE_URL')
OLLAMA_MODEL = env('OLLAMA_MODEL', 'gemma:4b')
```

### Ruteo Externo
```python
OPENROUTE_API_KEY = env('OPENROUTE_API_KEY')
MAPBOX_API_KEY = env('MAPBOX_API_KEY')
ROUTING_MAX_RESULTS = int(env('ROUTING_MAX_RESULTS', '6'))
ROUTING_VEHICLE_CANDIDATES = int(env('ROUTING_VEHICLE_CANDIDATES', '6'))
ROUTING_AGENT_CANDIDATES = int(env('ROUTING_AGENT_CANDIDATES', '4'))
ROUTING_CACHE_SIZE = int(env('ROUTING_CACHE_SIZE', '128'))
ROUTING_OFFLINE = env('ROUTING_OFFLINE', '0') == '1'
```

### Localización
```python
LANGUAGE_CODE = 'es'
TIME_ZONE = 'America/Argentina/Buenos_Aires'
USE_I18N = True
USE_TZ = True
```

---

## Comandos Django Personalizados

### seed_emergencies
```bash
python manage.py seed_emergencies [--flush] [--with-vehicles]
```
Genera emergencias de prueba con clasificación IA.

**Opciones:**
- `--flush`: Elimina emergencias previas
- `--with-vehicles`: Crea vehículos si no existen

### update_transport_data
```bash
python manage.py update_transport_data
```
Actualiza datos desde API de Transporte BA:
- Cortes de calles
- Estacionamientos
- Conteos de tránsito
- Alertas de transporte

---

## Scripts de Utilidad

### populate_real_data.py
```bash
python scripts/populate_real_data.py
```
Población inicial de la base de datos:
- Fuerzas (Bomberos, SAME, Policía, Tránsito)
- Instalaciones (comisarías, cuarteles)
- Hospitales
- Vehículos y agentes con coordenadas reales de CABA

### demo_emergency_parking.py
```bash
python demo_emergency_parking.py [--fast]
```
Demo narrada con TTS del flujo completo:
- Clasificación IA
- Búsqueda de estacionamiento
- Cálculo de rutas
- Sincronización con frontend

**Opciones:**
- `--fast`: Modo rápido sin pausas largas

### traffic_light_system.py
```bash
python traffic_light_system.py
```
Procesa emergencias código rojo y activa onda verde automáticamente.

### redistribute_resources.py
```bash
python redistribute_resources.py
```
Redistribuye recursos para evitar coordenadas problemáticas (zona del río).

---

## Variables de Entorno Recomendadas

Crear archivo `.env` en raíz de `emergency_system/`:

```bash
# Django Core
SECRET_KEY=your-secret-key-here-change-this
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1,yourdomain.com

# IA Providers
AI_PROVIDER=watson  # openai|ollama|watson
AI_TIMEOUT=20
AI_MAX_RETRIES=3

# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
OPENAI_API_BASE=https://api.openai.com/v1

# Ollama (local)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=gemma:4b

# Watson Orchestrate
WATSON_API_KEY=your-watson-api-key
WATSON_MODEL=default
WATSON_API_BASE=https://api.watson-orchestrate.ibm.com/v1

# Routing APIs
OPENROUTE_API_KEY=your-key
MAPBOX_API_KEY=your-key
ROUTING_MAX_RESULTS=6
ROUTING_OFFLINE=0

# News & Transport
NEWS_CACHE_SECONDS=300
NEWS_FEEDS=https://feed1.xml,https://feed2.xml
```

---

## Flujo de Trabajo Típico

### 1. Reporte de Emergencia
```
Usuario → /create/ → Formulario
                  ↓
          POST con descripción + coordenadas
                  ↓
          Emergency.save()
                  ↓
          classify_code() → classify_with_ai()
                  ↓
          Asignación automática de Force
                  ↓
          ensure_multi_dispatch()
                  ↓
          Creación de EmergencyDispatch
                  ↓
          Asignación de vehículos/agentes
                  ↓
          Cálculo inicial de rutas
                  ↓
          Persistencia en CalculatedRoute
                  ↓
          Redirect → /detalle/<id>/
```

### 2. Procesamiento Manual
```
Admin → /process/<id>/
              ↓
      process_emergency()
              ↓
      Reclasificación IA (opcional)
              ↓
      calculate_emergency_routes()
              ↓
      _persist_routes_for_emergency()
              ↓
      Múltiples CalculatedRoute guardadas
              ↓
      Render template con rutas
```

### 3. Activación Onda Verde
```
Usuario → Clic botón "Onda Verde"
                ↓
        POST /api/green-wave/<id>/
                ↓
        activate_emergency_green_wave()
                ↓
        Para cada dispatch:
          activate_green_wave()
                ↓
        Cálculo intersecciones en ruta
                ↓
        Ventanas temporales green_start/end
                ↓
        emergency.onda_verde = True
                ↓
        Response JSON con intersecciones
```

### 4. Seguimiento en Tiempo Real
```
Frontend poll cada 10s → GET /api/tracking/
                              ↓
                      real_time_tracking()
                              ↓
                      Query CalculatedRoute activas
                              ↓
                      Query EmergencyDispatch activas
                              ↓
                      Interpolar progreso por ETA
                              ↓
                      Calcular traffic_factor
                              ↓
                      Response con posiciones
```

### 5. Resolución
```
Admin → /resolver/<id>/
              ↓
        POST con notas
              ↓
        emergency.resolve()
              ↓
        Liberar vehículos/agentes
              ↓
        CalculatedRoute → status='completada'
              ↓
        EmergencyDispatch → status='finalizado'
              ↓
        emergency.status = 'resuelta'
```

---

## Problemas Conocidos y Limitaciones

### Seguridad
- ⚠️ `SECRET_KEY` hardcoded en código
- ⚠️ `DEBUG=True` en producción
- ⚠️ `ALLOWED_HOSTS=[]` permite cualquier host
- ⚠️ Sin autenticación en endpoints críticos (onda verde, redistribución)
- ⚠️ Falta validación de inputs en formularios
- ⚠️ SSRF potencial en geocoding

### Performance
- ⚠️ Sin índices en campos `status`, `code`, `priority`
- ⚠️ Queries N+1 en templates
- ⚠️ Sin caché en queries frecuentes
- ⚠️ Geocoding síncrono sin timeout

### Código
- ⚠️ Funciones `process_emergency()` y `calculate_routes_api()` muy largas (200+ líneas)
- ⚠️ Lógica de clasificación duplicada en 3 lugares
- ⚠️ Manejo de errores inconsistente (`print()` en producción)
- ⚠️ Sin tests unitarios

---

## Próximos Desarrollos

### Integración Watson Orchestrate
**Pendiente de implementación en `core/llm.py`:**

```python
class CloudAIClient:
    def _call_watson(self, description: str) -> Optional[Dict[str, Any]]:
        """
        Integración con Watson Orchestrate LLM.
        
        Requiere:
        - WATSON_API_KEY
        - WATSON_API_BASE
        - WATSON_MODEL
        
        Request: {
            "model": str,
            "input": str,
            "schema": dict
        }
        
        Response: {
            "result": {
                "tipo": str,
                "codigo": str,
                "score": int,
                "razones": list,
                "recursos": list
            }
        }
        """
```

**Fallback chain propuesto:**
1. Watson Orchestrate (primario)
2. OpenAI (si Watson falla)
3. Ollama (si OpenAI falla)
4. Local rules (último recurso)

### Mejoras Propuestas
- [ ] Migrar secrets a variables de entorno
- [ ] Implementar autenticación JWT
- [ ] Agregar índices a modelos
- [ ] Implementar caché Redis
- [ ] Escribir suite de tests
- [ ] Refactorizar funciones largas
- [ ] WebSockets para tracking real-time
- [ ] Integración con Waze/Google Maps Traffic
- [ ] Dashboard de métricas con Grafana
- [ ] Logs estructurados con ELK stack

---

## Glosario de Términos

**CABA**: Ciudad Autónoma de Buenos Aires  
**ETA**: Estimated Time of Arrival (tiempo estimado de llegada)  
**SAME**: Sistema de Atención Médica de Emergencias  
**Onda Verde**: Sistema de sincronización de semáforos para priorizar paso de emergencias  
**GeoJSON**: Formato JSON para representar geometrías geográficas  
**OSRM**: Open Source Routing Machine  
**Dispatch**: Despacho/asignación de recursos a emergencia  
**Fallback**: Sistema de respaldo cuando el sistema primario falla  
**N+1 Query**: Patrón ineficiente donde se hace 1 query + N queries adicionales en loop  

---

## Contacto y Soporte

**Repositorio**: https://github.com/Roan1982/ova  
**Rama principal**: main  
**Python**: 3.12  
**Django**: 5.2.5  

**Para soporte del agente Watson:**
- Revisar logs en consola Django: `python manage.py runserver`
- Estado de IA: `/ai-status/`
- Variables de entorno: Verificar `.env` existe y está configurado
- Modo offline: `ROUTING_OFFLINE=1` para desarrollo sin APIs externas

---

## Ejemplo de Uso Completo

### Caso: Incendio en edificio

**1. Reporte:**
```bash
POST /create/
{
    "description": "Incendio en edificio de 10 pisos en Av. Corrientes 1500",
    "address": "Av. Corrientes 1500, CABA",
    "location_lat": -34.6037,
    "location_lon": -58.3816
}
```

**2. Clasificación IA:**
```json
{
    "tipo": "bomberos",
    "codigo": "rojo",
    "score": 95,
    "razones": [
        "Incendio en edificio alto",
        "Alto riesgo para personas",
        "Requiere evacuación inmediata"
    ],
    "recursos": [
        {"tipo": "Camión de Bomberos", "cantidad": 3, "detalle": "Con escalera mecánica"},
        {"tipo": "Ambulancia", "cantidad": 2, "detalle": "Para posibles heridos"},
        {"tipo": "Patrulla", "cantidad": 1, "detalle": "Control de tránsito"}
    ]
}
```

**3. Despachos creados:**
- EmergencyDispatch → Force: Bomberos, Vehicle: Camión, Agent: Capitán
- EmergencyDispatch → Force: SAME, Vehicle: Ambulancia, Agent: Médico
- EmergencyDispatch → Force: Policía, Vehicle: Patrulla, Agent: Oficial

**4. Rutas calculadas:**
- Camión Bomberos (Cuartel Central): 2.3 km, 5 min, Score: 15
- Ambulancia 1 (Hospital Argerich): 1.8 km, 4 min, Score: 18
- Ambulancia 2 (Base SAME): 3.1 km, 7 min, Score: 25

**5. Onda verde activada:**
- 12 intersecciones en rutas
- Ventanas temporales de 30 segundos cada una
- Prioridad máxima por código rojo

**6. Tracking:**
- Poll cada 10s actualiza posiciones interpoladas
- ETA ajustada por tráfico en tiempo real
- Notificación cuando recursos están a <2 min

**7. Resolución:**
- Incendio controlado en 45 minutos
- 3 personas evacuadas con lesiones leves
- Recursos liberados y vuelven a bases
- Rutas marcadas como completadas

---

**Fin del Knowledge Source - Sistema de Emergencias CABA**  
**Versión**: 1.0  
**Fecha**: Octubre 2025  
**Autor**: Sistema de Documentación Automática
