"""
Test directo al endpoint de Watson que sabemos que acepta x-api-key
(basado en el test exitoso de test_orchestrate.py)
"""
import requests
import json
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    env_path = Path(__file__).resolve().parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
except Exception:
    pass

# Leer configuración
api_key = os.getenv('WATSON_API_KEY')
instance_url = os.getenv('WATSON_INSTANCE_URL')

if not api_key or not instance_url:
    print("ERROR: WATSON_API_KEY o WATSON_INSTANCE_URL no configuradas en .env")
    exit(1)

print(f"API Key (primeros 20 chars): {api_key[:20]}...")
print(f"Instance URL: {instance_url}")
print()

# Probar el endpoint /v1/chat/completions con múltiples métodos de auth
url = f"{instance_url.rstrip('/')}/v1/chat/completions"

# PRUEBA 1: Solo x-api-key
headers_xapikey = {
    'x-api-key': api_key,
    'Content-Type': 'application/json',
    'Accept': 'application/json'
}

# PRUEBA 2: x-api-key + Authorization Bearer (como sugirió el agente)
headers_both = {
    'x-api-key': api_key,
    'Authorization': f'Bearer {api_key}',
    'Content-Type': 'application/json',
    'Accept': 'application/json'
}

# PRUEBA 3: Solo Authorization Bearer
headers_bearer = {
    'Authorization': f'Bearer {api_key}',
    'Content-Type': 'application/json',
    'Accept': 'application/json'
}

# Usaremos la opción combinada (PRUEBA 2)
headers = headers_both

payload = {
    'messages': [
        {
            'role': 'system',
            'content': 'Clasifica emergencias en Buenos Aires según tipo (policial/medico/bomberos) y código (rojo/amarillo/verde).'
        },
        {
            'role': 'user',
            'content': 'Accidente de tránsito con heridos en Av. Corrientes'
        }
    ],
    'temperature': 0,
    'max_tokens': 400
}

print(f"POST {url}")
print(f"Headers:")
print(f"  x-api-key: {api_key[:10]}...")
print(f"  Authorization: Bearer {api_key[:10]}...")
print(f"Payload: {json.dumps(payload, indent=2)}")
print()
print("Enviando request con AMBOS headers (x-api-key + Authorization)...")

try:
    response = requests.post(url, headers=headers, json=payload, timeout=30)
    
    print(f"Status: {response.status_code}")
    print(f"Content-Type: {response.headers.get('Content-Type')}")
    print()
    
    if response.status_code == 200:
        try:
            data = response.json()
            print("✅ SUCCESS! Respuesta JSON:")
            print(json.dumps(data, indent=2, ensure_ascii=False))
        except Exception as e:
            print("⚠️  Response es 200 pero no es JSON válido:")
            print(response.text[:1000])
    else:
        print(f"❌ ERROR {response.status_code}")
        print("Response body:")
        print(response.text[:1000])
        
except Exception as e:
    print(f"❌ Exception: {e}")
