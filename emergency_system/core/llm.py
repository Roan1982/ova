import json
import time
import re
import logging
from typing import Any, Dict, List, Optional

import requests
from django.conf import settings

from .ai import get_ai_classification_with_response

logger = logging.getLogger(__name__)

JSON_SCHEMA_HINT = {
    "type": "object",
    "properties": {
        "tipo": {"type": "string", "enum": ["policial", "medico", "bomberos"]},
        "codigo": {"type": "string", "enum": ["rojo", "amarillo", "verde"]},
        "score": {"type": "number"},
        "razones": {"type": "array", "items": {"type": "string"}},
        "respuesta_ia": {"type": "string"},
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
    "required": ["tipo", "codigo"],
}

SYSTEM_PROMPT = (
    "Eres un clasificador de emergencias para la Ciudad Autónoma de Buenos Aires. "
    "Sigue exactamente estas instrucciones y responde en JSON válido contra el siguiente esquema: "
    f"{json.dumps(JSON_SCHEMA_HINT)}. "
    "Incluye un campo opcional 'recursos' con una lista de objetos que indiquen los móviles o agentes recomendados, con campos: tipo (string), cantidad (entero) y detalle (opcional). "
    "El campo 'respuesta_ia' debe contener una recomendación operativa corta en castellano. "
    "No agregues texto fuera del JSON, no uses comillas curvas ni bloques ``` y evita texto introductorio."
)


def _sanitize_content(content: str) -> str:
    content = re.sub(r"```[a-zA-Z]*\n|```", "", content)
    match = re.search(r"\{[\s\S]*\}", content)
    if match:
        content = match.group(0)
    return content.strip()


def _parse_json_content(raw_content: str) -> Optional[Dict[str, Any]]:
    try:
        cleaned = _sanitize_content(raw_content)
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.warning("No se pudo parsear respuesta JSON de IA: %s", exc)
        return None


def _normalize_result(result: Dict[str, Any], fuente: str) -> Dict[str, Any]:
    tipo = (result.get('tipo') or 'policial').strip().lower()
    codigo = (result.get('codigo') or 'verde').strip().lower()
    score = result.get('score')
    try:
        score = int(score) if score is not None else None
    except (ValueError, TypeError):
        score = None

    razones = result.get('razones') or []
    if isinstance(razones, str):
        razones = [razones]

    response_text = result.get('respuesta_ia') or 'Clasificación completada por IA.'

    recursos_formateados: List[Dict[str, Any]] = []
    recursos = result.get('recursos') or []
    if isinstance(recursos, list):
        for item in recursos:
            if isinstance(item, dict):
                tipo_recurso = item.get('tipo')
                if not tipo_recurso:
                    continue
                recursos_formateados.append({
                    'tipo': str(tipo_recurso).strip(),
                    'cantidad': int(item.get('cantidad') or 1),
                    'detalle': item.get('detalle')
                })
            elif isinstance(item, str):
                recursos_formateados.append({'tipo': item.strip(), 'cantidad': 1})

    normalized = {
        'tipo': tipo,
        'codigo': codigo,
        'score': score,
        'razones': razones,
        'respuesta_ia': response_text,
        'recursos': recursos_formateados,
        'recommended_resources': recursos_formateados,
        'fuente': fuente
    }
    return normalized


class CloudAIClient:
    def __init__(self):
        self.provider = getattr(settings, 'AI_PROVIDER', 'openai').lower()
        self.timeout = getattr(settings, 'AI_TIMEOUT', 20)
        self.max_retries = max(1, getattr(settings, 'AI_MAX_RETRIES', 3))

    def classify(self, description: str) -> Optional[Dict[str, Any]]:
        if not description:
            return None

        if self.provider == 'openai':
            return self._call_openai(description)
        if self.provider == 'ollama':
            return self._call_ollama(description)

        logger.warning("Proveedor de IA '%s' no soportado", self.provider)
        return None

    def _call_openai(self, description: str) -> Optional[Dict[str, Any]]:
        api_key = getattr(settings, 'OPENAI_API_KEY', None)
        if not api_key:
            logger.warning("OPENAI_API_KEY no configurada")
            return None

        base_url = getattr(settings, 'OPENAI_API_BASE', 'https://api.openai.com/v1').rstrip('/')
        model = getattr(settings, 'OPENAI_MODEL', 'gpt-4o-mini')
        url = f"{base_url}/chat/completions"

        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }

        payload = {
            'model': model,
            'messages': [
                {'role': 'system', 'content': SYSTEM_PROMPT},
                {'role': 'user', 'content': description}
            ],
            'temperature': 0,
            'max_tokens': 400,
            'response_format': {'type': 'json_object'}
        }

        last_error: Optional[str] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
                if response.status_code == 200:
                    data = response.json()
                    choices = data.get('choices') or []
                    if not choices:
                        last_error = 'Respuesta sin choices'
                        continue
                    content = choices[0].get('message', {}).get('content')
                    if not content:
                        last_error = 'Respuesta sin contenido'
                        continue
                    parsed = _parse_json_content(content)
                    if parsed:
                        return parsed
                else:
                    last_error = f"HTTP {response.status_code}: {response.text[:200]}"
            except requests.RequestException as exc:
                last_error = str(exc)

            time.sleep(min(2 ** attempt, 5))

        if last_error:
            logger.error("Fallo en OpenAI luego de %s intentos: %s", self.max_retries, last_error)
        return None

    def _call_ollama(self, description: str) -> Optional[Dict[str, Any]]:
        base_url = getattr(settings, 'OLLAMA_BASE_URL', None)
        if not base_url:
            logger.warning("OLLAMA_BASE_URL no configurada")
            return None

        payload = {
            'model': getattr(settings, 'OLLAMA_MODEL', 'gemma:4b'),
            'messages': [
                {'role': 'system', 'content': SYSTEM_PROMPT},
                {'role': 'user', 'content': description}
            ],
            'format': 'json',
            'stream': False,
            'options': {'temperature': 0}
        }

        return _ollama_chat(base_url, payload, self.timeout, self.max_retries)


def _ollama_chat(base_url: str, payload: Dict[str, Any], timeout: int, retries: int) -> Optional[Dict[str, Any]]:
    url = base_url.rstrip('/') + '/api/chat'
    last_error: Optional[str] = None
    for attempt in range(1, retries + 1):
        try:
            response = requests.post(url, json=payload, timeout=timeout)
            if response.status_code == 200:
                data = response.json()
                content = data.get('message', {}).get('content')
                if not content:
                    last_error = 'Respuesta sin contenido'
                    continue
                parsed = _parse_json_content(content)
                if parsed:
                    return parsed
            else:
                last_error = f"HTTP {response.status_code}: {response.text[:200]}"
        except requests.RequestException as exc:
            last_error = str(exc)
        time.sleep(min(2 ** attempt, 3))

    if last_error:
        logger.error("Fallo en Ollama luego de %s intentos: %s", retries, last_error)
    return None


def classify_with_ai(description: str) -> Dict[str, Any]:
    client = CloudAIClient()
    try:
        result = client.classify(description)
        if result:
            return _normalize_result(result, client.provider)
    except Exception as exc:
        logger.exception("Error clasificando con IA en la nube: %s", exc)

    fallback = get_ai_classification_with_response(description)
    fallback['fuente'] = 'local'
    fallback.setdefault('recursos', fallback.get('recommended_resources', []))
    fallback['recommended_resources'] = fallback.get('recursos', [])
    return fallback


# Compatibilidad hacia atrás
def classify_with_ollama(description: str) -> Dict[str, Any]:
    return classify_with_ai(description)


def get_ai_status() -> Dict[str, Any]:
    provider = getattr(settings, 'AI_PROVIDER', 'openai').lower()
    status: Dict[str, Any] = {
        'provider': provider,
        'cloud_available': False,
        'local_ai_available': True,
        'current_system': 'local',
        'details': {}
    }

    if provider == 'openai':
        api_key = getattr(settings, 'OPENAI_API_KEY', None)
        model = getattr(settings, 'OPENAI_MODEL', 'gpt-4o-mini')
        if api_key:
            headers = {'Authorization': f'Bearer {api_key}'}
            base_url = getattr(settings, 'OPENAI_API_BASE', 'https://api.openai.com/v1').rstrip('/')
            url = f"{base_url}/models/{model}"
            try:
                response = requests.get(url, headers=headers, timeout=5)
                status['cloud_available'] = response.status_code == 200
                if not status['cloud_available']:
                    status['details']['last_error'] = f"HTTP {response.status_code}: {response.text[:200]}"
            except requests.RequestException as exc:
                status['details']['last_error'] = str(exc)
        else:
            status['details']['last_error'] = 'OPENAI_API_KEY no configurada'
    elif provider == 'ollama':
        base_url = getattr(settings, 'OLLAMA_BASE_URL', None)
        if base_url:
            try:
                response = requests.get(base_url.rstrip('/') + '/api/tags', timeout=3)
                status['cloud_available'] = response.status_code == 200
                if not status['cloud_available']:
                    status['details']['last_error'] = f"HTTP {response.status_code}: {response.text[:200]}"
            except requests.RequestException as exc:
                status['details']['last_error'] = str(exc)
        else:
            status['details']['last_error'] = 'OLLAMA_BASE_URL no configurada'

    status['current_system'] = provider if status['cloud_available'] else 'local'
    return status
