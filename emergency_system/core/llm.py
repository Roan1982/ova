import json
import time
import re
import requests
from django.conf import settings

JSON_SCHEMA_HINT = {
    "type": "object",
    "properties": {
        "tipo": {"type": "string", "enum": ["policial", "medico", "bomberos"]},
        "codigo": {"type": "string", "enum": ["rojo", "amarillo", "verde"]},
        "score": {"type": "number"},
        "razones": {"type": "array", "items": {"type": "string"}}
    },
    "required": ["tipo", "codigo"],
}

SYSTEM_PROMPT = (
    "Eres un clasificador de eventos de emergencias para CABA. "
    "Tareas: 1) Determinar el tipo de intervención primaria entre ['policial','medico','bomberos']; "
    "2) Determinar el código de prioridad entre ['rojo','amarillo','verde'] según gravedad y riesgo vital inmediato; "
    "3) Explicar brevemente las razones. "
    "Responde SOLO en JSON estricto. Ejemplo: {\"tipo\":\"medico\",\"codigo\":\"rojo\",\"score\":80,\"razones\":[\"...\",\"...\"]}. "
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
            time.sleep(min(2 * attempt, 5))
    # si no lo logramos, devolvemos None
    return None


def classify_with_ollama(description: str):
    if not description:
        return None
    payload = {
        "model": settings.OLLAMA_MODEL,
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
    if not result:
        return None
    # Validación básica
    tipo = (result.get('tipo') or '').strip().lower()
    codigo = (result.get('codigo') or '').strip().lower()
    if tipo not in ['policial', 'medico', 'bomberos']:
        return None
    if codigo not in ['rojo', 'amarillo', 'verde']:
        return None
    return {
        'tipo': tipo,
        'codigo': codigo,
        'score': result.get('score', None),
        'razones': result.get('razones', []),
    }
