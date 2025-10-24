"""
Probar diferentes endpoints de Watson Orchestrate con el token válido
"""
import os
import sys
from pathlib import Path
import requests
import json

# Cargar .env
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).resolve().parent / '.env'
    if env_path.exists():
        load_dotenv(env_path, override=True)
except Exception:
    pass

# Configurar Django para usar CloudAIClient
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'emergency_app.settings')
os.environ.setdefault('AI_PROVIDER', 'watson')

import django
django.setup()

from core.llm import CloudAIClient
from django.conf import settings

# Obtener token
client = CloudAIClient()
token = client._get_watson_jwt(settings.WATSON_API_KEY)

if not token:
    print("❌ No se pudo obtener token")
    exit(1)

print(f"✅ Token obtenido")
print()

base_url = settings.WATSON_INSTANCE_URL.rstrip('/')

# Probar diferentes endpoints posibles
endpoints_to_try = [
    f"{base_url}/v1/chat/completions",  # Estilo OpenAI (fallando)
    f"{base_url}/chat/completions",  # Sin /v1
    f"{base_url}/v1/chat",  # Sin /completions
    f"{base_url}/chat",  # Mínimo
    f"{base_url}/v1/completions",  # Completions solo
    f"{base_url}/api/v1/chat/completions",  # Con /api prefix
]

headers = {
    'Authorization': f'Bearer {token}',
    'Content-Type': 'application/json',
    'Accept': 'application/json'
}

payload = {
    'messages': [
        {'role': 'user', 'content': 'Hola'}
    ],
    'max_tokens': 10
}

print("Probando endpoints:")
print("=" * 70)

for endpoint in endpoints_to_try:
    print(f"\n{endpoint}")
    try:
        resp = requests.post(endpoint, headers=headers, json=payload, timeout=10)
        print(f"  Status: {resp.status_code}")
        print(f"  Content-Type: {resp.headers.get('Content-Type', 'N/A')}")
        
        if resp.status_code == 200:
            print(f"  ✅ SUCCESS!")
            try:
                print(f"  Response: {json.dumps(resp.json(), indent=4)[:200]}...")
            except:
                print(f"  Response (text): {resp.text[:200]}...")
            break
        elif resp.status_code == 404:
            print(f"  ❌ 404 Not Found")
        elif resp.status_code == 401:
            print(f"  ❌ 401 Unauthorized")
        else:
            print(f"  ⚠️  {resp.status_code}: {resp.text[:100]}")
    except Exception as e:
        print(f"  ❌ Exception: {e}")

print()
print("=" * 70)
