# 📊 Datos que se Envían a Watson Orchestrate

## ✅ Resumen de la Prueba

Ejecutamos una clasificación completa mostrando **exactamente** qué datos Watson recibe y cómo debe responder.

---

## 🔑 1. AUTENTICACIÓN

### Token IAM (JWT)
```
✅ Token obtenido exitosamente
Longitud: 1446 caracteres
Tipo: Bearer token
Endpoint IAM: https://iam.platform.saas.ibm.com/siusermgr/api/1.0/apikeys/token
Expira en: 7200 segundos (2 horas)
```

### Headers HTTP
```http
Authorization: Bearer eyJraWQiOiJJLXlVeldnSnlhUE5MY0RTdzBmS2x1TUd6cWlFdU... (1446 chars)
Content-Type: application/json
```

---

## 📤 2. DATOS ENVIADOS A WATSON

### Endpoint
```
POST https://api.dl.watson-orchestrate.ibm.com/instances/20251024-1053-4080-0097-0efa6c69fba0/v1/chat/completions
```

### Payload JSON Completo
```json
{
  "messages": [
    {
      "role": "system",
      "content": "Eres un clasificador de emergencias para la Ciudad Autónoma de Buenos Aires. Sigue exactamente estas instrucciones y responde en JSON válido contra el siguiente esquema: {\"type\": \"object\", \"properties\": {\"tipo\": {\"type\": \"string\", \"enum\": [\"policial\", \"medico\", \"bomberos\"]}, \"codigo\": {\"type\": \"string\", \"enum\": [\"rojo\", \"amarillo\", \"verde\"]}, \"score\": {\"type\": \"number\"}, \"razones\": {\"type\": \"array\", \"items\": {\"type\": \"string\"}}, \"respuesta_ia\": {\"type\": \"string\"}, \"recursos\": {\"type\": \"array\", \"items\": {\"type\": \"object\", \"properties\": {\"tipo\": {\"type\": \"string\"}, \"cantidad\": {\"type\": \"integer\"}, \"detalle\": {\"type\": \"string\"}}}}}, \"required\": [\"tipo\", \"codigo\"]}. Incluye un campo opcional 'recursos' con una lista de objetos que indiquen los móviles o agentes recomendados, con campos: tipo (string), cantidad (entero) y detalle (opcional). El campo 'respuesta_ia' debe contener una recomendación operativa corta en castellano. No agregues texto fuera del JSON, no uses comillas curvas ni bloques ``` y evita texto introductorio."
    },
    {
      "role": "user",
      "content": "Clasifica la siguiente emergencia de CABA según el schema JSON del sistema:\n\nDescripción: \n    Incendio en edificio de departamentos de 8 pisos en Av. Corrientes 2500.\n    Hay humo visible desde la calle y vecinos reportan personas atrapadas en el 5to piso.\n    Se escuchan gritos de auxilio. Temperatura ambiente alta. \n    Necesitamos respuesta urgente con bomberos y ambulancias.\n    \n\nResponde SOLO con el JSON de clasificación que incluya: tipo, codigo, score, razones, respuesta_ia y recursos."
    }
  ],
  "temperature": 0,
  "max_tokens": 500
}
```

---

## 🎯 3. QUÉ "VE" WATSON

### Mensaje del Sistema (Instrucciones)
Watson recibe estas instrucciones claras:
- Actuar como clasificador de emergencias de CABA
- Responder SOLO con JSON válido
- Seguir el schema exacto definido
- Incluir campo `recursos` con móviles/agentes recomendados
- Proporcionar respuesta operativa en castellano

### Mensaje del Usuario (Descripción de Emergencia)
Watson recibe:
```
Descripción: 
    Incendio en edificio de departamentos de 8 pisos en Av. Corrientes 2500.
    Hay humo visible desde la calle y vecinos reportan personas atrapadas en el 5to piso.
    Se escuchan gritos de auxilio. Temperatura ambiente alta. 
    Necesitamos respuesta urgente con bomberos y ambulancias.
```

---

## 📐 4. SCHEMA JSON QUE WATSON DEBE SEGUIR

```json
{
  "type": "object",
  "properties": {
    "tipo": {
      "type": "string",
      "enum": ["policial", "medico", "bomberos"]
    },
    "codigo": {
      "type": "string",
      "enum": ["rojo", "amarillo", "verde"]
    },
    "score": {
      "type": "number"
    },
    "razones": {
      "type": "array",
      "items": {"type": "string"}
    },
    "respuesta_ia": {
      "type": "string"
    },
    "recursos": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "tipo": {"type": "string"},
          "cantidad": {"type": "integer"},
          "detalle": {"type": "string"}
        }
      }
    }
  },
  "required": ["tipo", "codigo"]
}
```

---

## 📋 5. RESPUESTA ESPERADA DE WATSON

### Ejemplo de respuesta exitosa que Watson debería devolver:

```json
{
  "tipo": "bomberos",
  "codigo": "rojo",
  "score": 95,
  "razones": [
    "Incendio en edificio alto (8 pisos)",
    "Personas atrapadas en 5to piso",
    "Gritos de auxilio reportados",
    "Alto riesgo de propagación"
  ],
  "respuesta_ia": "Despachar inmediatamente 3 autobombas con escalera mecánica, 2 ambulancias y 1 patrulla para control de tránsito. Activar protocolo de evacuación.",
  "recursos": [
    {
      "tipo": "Camión de Bomberos con Escalera",
      "cantidad": 3,
      "detalle": "Para rescate en altura"
    },
    {
      "tipo": "Ambulancia SAME",
      "cantidad": 2,
      "detalle": "Atención víctimas"
    },
    {
      "tipo": "Patrulla Policía",
      "cantidad": 1,
      "detalle": "Control de perímetro"
    }
  ]
}
```

---

## 🚑 6. CÓMO DECIDE QUÉ AGENTES/MÓVILES ENVIAR

### Watson analiza la descripción y detecta:

1. **Palabras clave**: "incendio", "edificio", "pisos", "atrapadas", "gritos"
2. **Gravedad**: 
   - Altura del edificio (8 pisos) → Código ROJO
   - Personas en peligro → Score alto (90-100)
3. **Tipo de emergencia**:
   - "incendio" → tipo: "bomberos"
4. **Recursos necesarios**:
   - Edificio alto → Camiones con escalera
   - Personas heridas → Ambulancias
   - Control de zona → Patrulla policial

### Estructura del campo `recursos`:
```javascript
{
  "tipo": string,        // Tipo de móvil (ej: "Ambulancia", "Camión de Bomberos")
  "cantidad": integer,   // Cuántos móviles enviar (1-10)
  "detalle": string      // Opcional: especificaciones (ej: "con escalera mecánica")
}
```

---

## 🔄 7. FLUJO COMPLETO EN EL SISTEMA

```
1. Usuario reporta emergencia
   ↓
2. Sistema construye prompt con descripción
   ↓
3. Sistema intercambia API key por token IAM
   ↓
4. Sistema envía payload JSON a Watson
   ↓
5. Watson analiza:
   - Descripción de emergencia
   - Keywords detectadas
   - Gravedad estimada
   ↓
6. Watson devuelve JSON con:
   - tipo (bomberos/medico/policial)
   - codigo (rojo/amarillo/verde)
   - score (0-100)
   - razones (lista de factores)
   - respuesta_ia (recomendación)
   - recursos (móviles/agentes recomendados)
   ↓
7. Sistema parsea respuesta y:
   - Asigna código a Emergency
   - Asigna Force según tipo
   - Crea EmergencyDispatch
   - Asigna vehículos según recursos
   - Calcula rutas con RouteOptimizer
```

---

## ⚠️ 8. ESTADO ACTUAL

### ✅ Lo que funciona:
- Token IAM se obtiene correctamente (JWT de 1446 chars)
- Payload se construye correctamente
- Headers se envían correctamente
- Endpoint correcto: `../v1/chat/completions`

### ❌ El problema:
```
HTTP 404: Endpoint no disponible
```

**Causa**: La instancia de Watson Orchestrate **NO tiene habilitado el acceso programático** por API.

### 💡 Soluciones posibles:

1. **Habilitar API en Watson Console**:
   - Ve a: https://dl.watson-orchestrate.ibm.com/settings
   - Busca sección "API settings" o "Developer settings"
   - Activar "Programmatic access" o "Chat API"

2. **Usar Watson Assistant** (alternativa):
   - Crear un Watson Assistant con las mismas instrucciones
   - Obtener credentials de Watson Assistant API
   - Cambiar endpoint a Watson Assistant

3. **Usar fallback local** (actual):
   - Sistema usa reglas basadas en keywords
   - Siempre devuelve clasificación válida
   - No requiere Watson

---

## 📊 9. EJEMPLO REAL DE FALLBACK LOCAL

Si Watson no responde, el sistema usa `core/ai.py`:

```python
# Input
"Incendio en edificio de 8 pisos"

# Output (fallback local)
{
  "tipo": "bomberos",
  "codigo": "rojo",
  "score": 90,
  "razones": ["Incendio detectado", "Edificio de altura"],
  "respuesta_ia": "Código rojo: emergencia crítica",
  "recursos": [
    {"tipo": "Camión de Bomberos", "cantidad": 2}
  ],
  "fuente": "local"  # Indica que no usó Watson
}
```

---

## 🎯 10. CONCLUSIÓN

### Watson recibe estos datos para clasificar:

| Campo | Dato |
|-------|------|
| **Descripción completa** | Todo el texto de la emergencia |
| **Schema JSON** | Estructura exacta de respuesta esperada |
| **Instrucciones** | Cómo debe analizar y responder |
| **Temperature** | 0 (respuestas determinísticas) |
| **Max tokens** | 500 (suficiente para JSON completo) |

### Watson debe devolver:

| Campo | Descripción |
|-------|-------------|
| `tipo` | "policial", "medico" o "bomberos" |
| `codigo` | "rojo" (crítico), "amarillo" (urgente), "verde" (leve) |
| `score` | 0-100 (gravedad numérica) |
| `razones` | Array de strings explicando por qué |
| `respuesta_ia` | Recomendación operativa en castellano |
| `recursos` | Array de objetos con tipo, cantidad y detalle de móviles |

### El sistema usa estos datos para:
- Asignar la emergencia a la **Force** correcta (Bomberos/SAME/Policía)
- Establecer **prioridad** (10=rojo, 5=amarillo, 1=verde)
- Filtrar **vehículos disponibles** de ese tipo
- Calcular **rutas óptimas** con RouteOptimizer
- Crear **EmergencyDispatch** con asignaciones
- Persistir **CalculatedRoute** para trazabilidad

---

## 🔧 Para probar tú mismo:

```powershell
cd emergency_system
$env:AI_PROVIDER='watson'
$env:WATSON_API_KEY='tu-api-key'
$env:WATSON_INSTANCE_URL='https://api.dl.watson-orchestrate.ibm.com/instances/...'
$env:WATSON_IAM_URL='https://iam.platform.saas.ibm.com/siusermgr/api/1.0/apikeys/token'
python test_watson_real.py
```

Este script muestra TODO el proceso paso a paso.
