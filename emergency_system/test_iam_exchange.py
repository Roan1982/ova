"""
Probar intercambio de API key por token IAM en AMBOS endpoints de IBM
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

api_key = os.getenv('WATSON_API_KEY')

if not api_key:
    print("ERROR: WATSON_API_KEY no configurada")
    exit(1)

print(f"API Key (primeros 20 chars): {api_key[:20]}...")
print()

# ENDPOINT 1: IAM clásico (form-encoded)
print("=" * 60)
print("PRUEBA 1: Endpoint IAM clásico (form-encoded)")
print("=" * 60)
iam_classic_url = "https://iam.cloud.ibm.com/identity/token"
headers_classic = {'Content-Type': 'application/x-www-form-urlencoded'}
data_classic = {
    'grant_type': 'urn:ibm:params:oauth:grant-type:apikey',
    'apikey': api_key
}

try:
    resp = requests.post(iam_classic_url, data=data_classic, headers=headers_classic, timeout=10)
    print(f"Status: {resp.status_code}")
    print(f"Response:")
    try:
        print(json.dumps(resp.json(), indent=2))
    except:
        print(resp.text[:500])
    
    if resp.status_code == 200:
        token = resp.json().get('access_token')
        if token:
            print(f"\n✅ TOKEN OBTENIDO (primeros 50 chars): {token[:50]}...")
        else:
            print("\n⚠️ Response 200 pero sin access_token")
except Exception as e:
    print(f"❌ Exception: {e}")

print()

# ENDPOINT 2: Platform SAAS (JSON)
print("=" * 60)
print("PRUEBA 2: Endpoint platform.saas (JSON)")
print("=" * 60)
iam_saas_url = "https://iam.platform.saas.ibm.com/siusermgr/api/1.0/apikeys/token"
headers_saas = {'Content-Type': 'application/json', 'Accept': 'application/json'}
payload_saas = {'apikey': api_key}

try:
    resp = requests.post(iam_saas_url, json=payload_saas, headers=headers_saas, timeout=10)
    print(f"Status: {resp.status_code}")
    print(f"Response:")
    try:
        print(json.dumps(resp.json(), indent=2))
    except:
        print(resp.text[:500])
    
    if resp.status_code == 200:
        j = resp.json()
        token = j.get('access_token') or j.get('token') or j.get('jwt')
        if token:
            print(f"\n✅ TOKEN OBTENIDO (primeros 50 chars): {token[:50]}...")
        else:
            print("\n⚠️ Response 200 pero sin token")
except Exception as e:
    print(f"❌ Exception: {e}")

print()
print("=" * 60)
print("CONCLUSIÓN:")
print("Si ambas pruebas fallan con BXNIM0415E, la API key actual")
print("NO es una IBM Cloud API key válida para intercambio IAM.")
print("Necesitás generar una desde: https://cloud.ibm.com/iam/apikeys")
print("=" * 60)
