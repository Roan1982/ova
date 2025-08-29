import json
import time
import re
import requests
from django.conf import settings
from .ai import get_ai_classification_with_response

JSON_SCHEMA_HINT = {
    "type": "object",
    "properties": {
        "tipo": {"type": "string", "enum": ["policial", "medico", "bomberos"]},
        "codigo": {"type": "string", "enum": ["rojo", "amarillo", "verde"]},
        "score": {"type": "number"},
        "razones": {"type": "array", "items": {"type": "string"}},
        "respuesta_ia": {"type": "string"}
    },
    "required": ["tipo", "codigo"],
}

SYSTEM_PROMPT = (
    "Eres un clasificador de eventos de emergencias para CABA. "
    "Tareas: 1) Determinar el tipo de intervención primaria entre ['policial','medico','bomberos']; "
    "2) Determinar el código de prioridad entre ['rojo','amarillo','verde'] según gravedad y riesgo vital inmediato; "
    "3) Explicar brevemente las razones; "
    "4) Generar una respuesta coherente como sistema de IA de emergencias. "
    "Responde SOLO en JSON estricto. Ejemplo: {\"tipo\":\"medico\",\"codigo\":\"rojo\",\"score\":80,\"razones\":[\"...\",\"...\"],\"respuesta_ia\":\"Emergencia médica crítica...\"} "
    "No incluyas texto fuera del JSON, no uses comillas curvas, no uses bloques ``` y separa con comas."
)


def _sanitize_content(content: str) -> str:
    # eliminar bloques ```...```
    content = re.sub(r"```[a-zA-Z]*\n|```", "", content)
    # extraer solo el primer bloque {...}
    m = re.search(r"\{[\s\S]*\}", content)
    if m:
        content = m.group(0)
    content = content.strip()
    # reparar comas faltantes entre strings adyacentes (p.ej. "x" "y" -> "x", "y")
    content = re.sub(r'"\s+"', '", "', content)
    return content


def _ollama_chat(payload):
    """Intenta conectar con Ollama. Retorna None si falla."""
    try:
        url = settings.OLLAMA_BASE_URL.rstrip('/') + '/api/chat'
        last_exc = None
        for attempt in range(1, settings.OLLAMA_MAX_RETRIES + 1):
            try:
                r = requests.post(url, json=payload, timeout=settings.OLLAMA_TIMEOUT)
                r.raise_for_status()
                data = r.json()
                content = data.get('message', {}).get('content', '')
                if not content:
                    return None
                content = _sanitize_content(content)
                return json.loads(content)
            except Exception as e:
                last_exc = e
                # backoff simple
                time.sleep(min(2 * attempt, 2))  # Reducido el backoff
        return None
    except Exception:
        # Si hay problemas de conectividad con Ollama, usar IA local
        return None


def classify_with_ollama(description: str):
    """Clasifica emergencia con Ollama, o IA local como respaldo"""
    if not description:
        return None
    
    # Primero intentar con Ollama
    payload = {
        "model": getattr(settings, 'OLLAMA_MODEL', 'gemma:4b'),
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": description},
        ],
        "format": "json",
        "stream": False,
        "options": {
            "temperature": 0
        }
    }
    
    result = _ollama_chat(payload)
    
    if result:
        # Validar respuesta de Ollama
        tipo = (result.get('tipo') or '').strip().lower()
        codigo = (result.get('codigo') or '').strip().lower()
        if tipo in ['policial', 'medico', 'bomberos'] and codigo in ['rojo', 'amarillo', 'verde']:
            # Ollama funcionó correctamente
            return {
                'tipo': tipo,
                'codigo': codigo,
                'score': result.get('score', None),
                'razones': result.get('razones', []),
                'respuesta_ia': result.get('respuesta_ia', 'Clasificación completada por IA.'),
                'fuente': 'ollama'
            }
    
    # Si Ollama falla, usar IA local mejorada
    try:
        local_result = get_ai_classification_with_response(description)
        local_result['fuente'] = 'local'
        return local_result
    except Exception as e:
        # Respuesta de emergencia si todo falla
        return {
            'tipo': 'policial',
            'codigo': 'amarillo',
            'score': 25,
            'razones': [f'Error en clasificación: {str(e)[:100]}'],
            'respuesta_ia': 'Sistema de clasificación no disponible. Emergencia asignada con prioridad media por precaución.',
            'fuente': 'fallback'
        }


def get_ai_status():
    """Verifica el estado de disponibilidad de los sistemas de IA"""
    status = {
        'ollama_available': False,
        'local_ai_available': True,
        'current_system': 'local'
    }
    
    try:
        # Test rápido de Ollama
        url = getattr(settings, 'OLLAMA_BASE_URL', 'http://localhost:11434').rstrip('/') + '/api/tags'
        response = requests.get(url, timeout=3)
        if response.status_code == 200:
            status['ollama_available'] = True
            status['current_system'] = 'ollama'
    except:
        pass
    
    return status
