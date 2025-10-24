# 📤 Instrucciones para Subir Knowledge Source a Watson Orchestrate

## Archivos Disponibles

Tienes **2 versiones** del mismo documento (elige la que prefieras):

1. **`WATSON_KNOWLEDGE_SOURCE.md`** (Markdown, 26.53 KB)
2. **`WATSON_KNOWLEDGE_SOURCE.txt`** (Texto plano, 26.53 KB)

✅ Ambos archivos están **muy por debajo del límite de 5 MB** para archivos de texto.

---

## Pasos para Subir a Watson Orchestrate

### 1️⃣ Acceder a Watson Orchestrate
1. Ve a: https://dl.watson-orchestrate.ibm.com/home
2. Inicia sesión con tus credenciales IBM

### 2️⃣ Ir a Knowledge Sources
1. En el menú lateral, busca **"Knowledge sources"** o **"Fuentes de conocimiento"**
2. Haz clic en el botón **"Upload files"** o **"Subir archivos"**

### 3️⃣ Subir el Archivo
1. Selecciona el archivo:
   - **Opción A**: `WATSON_KNOWLEDGE_SOURCE.txt` (recomendado para máxima compatibilidad)
   - **Opción B**: `WATSON_KNOWLEDGE_SOURCE.md` (si Watson soporta Markdown)

2. Verifica la información:
   - **Nombre**: Sistema de Emergencias CABA
   - **Descripción**: Knowledge source completo del sistema de gestión de emergencias
   - **Tags** (sugeridos): 
     - `emergencias`
     - `caba`
     - `django`
     - `api`
     - `routing`
     - `ia-clasificacion`

3. Haz clic en **"Upload"** o **"Cargar"**

### 4️⃣ Configurar el Agente
1. Ve a tu agente o skill en Watson Orchestrate
2. En la configuración, agrega el Knowledge Source recién subido
3. Guarda los cambios

---

## Validación Post-Carga

Después de subir el archivo, **prueba el agente** con estas preguntas:

### Preguntas de Validación:

**Básicas:**
- "¿Qué modelos de datos tiene el sistema?"
- "¿Cuáles son los endpoints disponibles?"
- "¿Cómo funciona el sistema de clasificación de emergencias?"

**Técnicas:**
- "¿Qué proveedores de ruteo soporta el sistema?"
- "Explica el flujo de activación de onda verde"
- "¿Cuál es el schema JSON que espera la IA?"

**Integración:**
- "¿Cómo integro Watson Orchestrate como proveedor de IA?"
- "¿Qué variables de entorno necesito configurar?"
- "¿Cuál es el fallback chain propuesto?"

**Ejemplo completo:**
- "Describe el flujo completo cuando se reporta un incendio"

---

## Estructura del Knowledge Source

El documento incluye:

✅ **Información General**
- Propósito del sistema
- Tecnologías utilizadas
- Estructura del proyecto

✅ **Modelos de Datos**
- Emergency, Force, Vehicle, Agent
- CalculatedRoute, EmergencyDispatch
- Facility, Hospital
- Modelos de transporte (StreetClosure, ParkingSpot, etc.)

✅ **APIs Completas**
- Endpoints frontend
- APIs JSON (emergencias, ruteo, onda verde)
- Noticias y datos externos
- Gestión de recursos

✅ **Sistema de Clasificación IA**
- Schema JSON esperado
- Prompt del sistema
- Flujo de clasificación
- Proveedores configurados (OpenAI, Ollama, Watson)

✅ **Sistema de Ruteo**
- RouteOptimizer
- Proveedores multi-API
- Función de cálculo de rutas

✅ **Sistema de Onda Verde**
- Intersecciones principales
- TrafficManager
- Funciones helper

✅ **Configuración**
- Settings de seguridad
- Variables de entorno
- Comandos Django

✅ **Flujos de Trabajo**
- Reporte de emergencia
- Procesamiento manual
- Activación onda verde
- Seguimiento en tiempo real
- Resolución

✅ **Ejemplo Completo**
- Caso práctico: Incendio en edificio
- Paso a paso con código y respuestas

---

## Límites de Watson Orchestrate (Información de Referencia)

📋 **Restricciones de archivos:**
- Máximo **20 archivos** por batch
- Tamaño total del batch: **30 MB**
- Tamaño máximo por archivo:
  - `.docx`, `.pdf`, `.pptx`, `.xlsx`: **25 MB**
  - `.csv`, `.html`, `.txt`: **5 MB**

✅ **Nuestro archivo**: 26.53 KB (0.03 MB) - **Muy por debajo del límite**

---

## Próximos Pasos Después de la Carga

### 1. **Probar el Agente**
Valida que el agente puede responder correctamente usando el knowledge source.

### 2. **Integrar Watson en el Código**
Una vez que el agente funcione, necesitaremos:
- Endpoint URL de Watson Orchestrate
- API Key / método de autenticación
- Formato exacto de request/response

### 3. **Implementar en `core/llm.py`**
Agregar el método `_call_watson()` con la lógica de integración.

### 4. **Configurar Variables de Entorno**
```bash
AI_PROVIDER=watson
WATSON_API_KEY=your-key-here
WATSON_API_BASE=https://api.watson-orchestrate.ibm.com/v1
WATSON_MODEL=default
```

### 5. **Probar Fallback Chain**
Validar que el sistema funciona:
- Watson (primario) ✅
- OpenAI (si Watson falla) ✅
- Ollama (si OpenAI falla) ✅
- Local rules (último recurso) ✅

---

## Soporte

Si encuentras algún problema:

1. **Verifica el formato**: Watson debe soportar `.txt` o `.md`
2. **Revisa el tamaño**: Debe ser < 5 MB (nuestro archivo es 26.53 KB ✅)
3. **Valida el contenido**: El documento debe estar completo (1013 líneas ✅)

**Contacto:**
- Repositorio: https://github.com/Roan1982/ova
- Issues: https://github.com/Roan1982/ova/issues

---

## Checklist Pre-Carga

Antes de subir, verifica:

- [x] Archivo generado correctamente
- [x] Tamaño válido (< 5 MB)
- [x] Versión .txt creada
- [x] Contenido completo (1013 líneas)
- [x] Estructurado en secciones claras
- [x] Incluye ejemplos prácticos
- [x] Documenta integración Watson
- [ ] Usuario tiene acceso a Watson Orchestrate
- [ ] Usuario conoce URL del workspace

---

**¡Listo para cargar! 🚀**

El knowledge source está preparado y optimizado para Watson Orchestrate.
