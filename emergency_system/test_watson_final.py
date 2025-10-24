"""
Test final: clasificación completa con Watson usando endpoint platform.saas
"""
import os
import sys
from pathlib import Path

# Cargar .env ANTES de importar Django
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).resolve().parent / '.env'
    if env_path.exists():
        load_dotenv(env_path, override=True)  # override=True para forzar recarga
        print(f"✅ .env cargado desde: {env_path}")
        print(f"   WATSON_IAM_URL: {os.getenv('WATSON_IAM_URL')}")
        print()
except Exception as e:
    print(f"⚠️  Error cargando .env: {e}")

# Ahora sí configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'emergency_app.settings')
os.environ.setdefault('AI_PROVIDER', 'watson')

import django
django.setup()

from core.llm import CloudAIClient
import json

def main():
    client = CloudAIClient()
    
    # Verificar configuración
    from django.conf import settings
    print("Configuración Django:")
    print(f"  AI_PROVIDER: {settings.AI_PROVIDER}")
    print(f"  WATSON_IAM_URL: {getattr(settings, 'WATSON_IAM_URL', 'NOT SET')}")
    print(f"  WATSON_API_KEY: {settings.WATSON_API_KEY[:20] if settings.WATSON_API_KEY else 'NOT SET'}...")
    print(f"  WATSON_INSTANCE_URL: {settings.WATSON_INSTANCE_URL}")
    print()
    
    # Probar intercambio IAM primero
    print("Paso 1: Intercambiando API key por token IAM...")
    token = client._get_watson_jwt(settings.WATSON_API_KEY)
    if token:
        print(f"✅ Token obtenido (primeros 50 chars): {token[:50]}...")
        print()
    else:
        print("❌ No se pudo obtener token IAM")
        return
    
    # Ahora clasificar
    print("Paso 2: Clasificando emergencia con Watson...")
    description = "Accidente de tránsito con heridos graves en Av. Corrientes y Callao. Solicito ambulancia urgente."
    
    result = client.classify(description)
    
    if result:
        print("✅ CLASIFICACIÓN EXITOSA!")
        print()
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("❌ La clasificación falló (revisar logs)")

if __name__ == '__main__':
    main()
