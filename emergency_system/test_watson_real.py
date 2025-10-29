"""
Test REAL de clasificación con Watson mostrando TODOS los datos enviados
"""
import os
import sys
import json
from pathlib import Path

# Configurar Django PRIMERO (settings.py carga el .env automáticamente)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'emergency_app.settings')

import django
django.setup()

from core.llm import CloudAIClient, SYSTEM_PROMPT, JSON_SCHEMA_HINT
from django.conf import settings

def main():
    print("=" * 80)
    print("TEST REAL DE CLASIFICACIÓN CON WATSON")
    print("=" * 80)
    print()
    
    # 1. Mostrar configuración
    print("📋 CONFIGURACIÓN:")
    print(f"  AI_PROVIDER: {settings.AI_PROVIDER}")
    print(f"  WATSON_API_KEY: {settings.WATSON_API_KEY[:20] if settings.WATSON_API_KEY else 'NOT SET'}...")
    print(f"  WATSON_INSTANCE_URL: {settings.WATSON_INSTANCE_URL}")
    print(f"  WATSON_IAM_URL: {getattr(settings, 'WATSON_IAM_URL', 'NOT SET')}")
    print()
    
    # 2. Mostrar el SYSTEM_PROMPT que se envía
    print("🤖 SYSTEM PROMPT (lo que Watson recibe como instrucciones):")
    print("-" * 80)
    print(SYSTEM_PROMPT)
    print("-" * 80)
    print()
    
    # 3. Mostrar el schema JSON esperado
    print("📐 JSON SCHEMA (estructura que debe devolver Watson):")
    print("-" * 80)
    print(json.dumps(JSON_SCHEMA_HINT, indent=2, ensure_ascii=False))
    print("-" * 80)
    print()
    
    # 4. Descripción de emergencia a clasificar
    descripcion = """
    Incendio en edificio de departamentos de 8 pisos en Av. Corrientes 2500.
    Hay humo visible desde la calle y vecinos reportan personas atrapadas en el 5to piso.
    Se escuchan gritos de auxilio. Temperatura ambiente alta. 
    Necesitamos respuesta urgente con bomberos y ambulancias.
    """
    
    print("🚨 DESCRIPCIÓN DE EMERGENCIA A CLASIFICAR:")
    print("-" * 80)
    print(descripcion.strip())
    print("-" * 80)
    print()
    
    # 5. Mostrar el USER PROMPT completo que se construye
    user_prompt = (
        f"Clasifica la siguiente emergencia de CABA según el schema JSON del sistema:\n\n"
        f"Descripción: {descripcion}\n\n"
        f"Responde SOLO con el JSON de clasificación que incluya: tipo, codigo, score, razones, respuesta_ia y recursos."
    )
    
    print("💬 USER PROMPT (mensaje enviado a Watson):")
    print("-" * 80)
    print(user_prompt)
    print("-" * 80)
    print()
    
    # 6. Mostrar el payload COMPLETO que se envía
    payload = {
        'messages': [
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user', 'content': user_prompt}
        ],
        'temperature': 0,
        'max_tokens': 500
    }
    
    print("📦 PAYLOAD COMPLETO (JSON enviado a Watson):")
    print("-" * 80)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print("-" * 80)
    print()
    
    # 7. Obtener token IAM primero
    print("🔑 Paso 1: Obteniendo token IAM...")
    client = CloudAIClient()
    token = client._get_watson_jwt(settings.WATSON_API_KEY)
    
    if token:
        print(f"✅ Token obtenido (primeros 50 chars): {token[:50]}...")
        print(f"   Token completo tiene {len(token)} caracteres")
        print()
    else:
        print("❌ No se pudo obtener token IAM")
        print("   El sistema intentará usar x-api-key directamente")
        print()
    
    # 8. Headers que se envían
    if token:
        headers_display = {
            'Authorization': f'Bearer {token[:50]}... (token truncado, total {len(token)} chars)',
            'Content-Type': 'application/json'
        }
    else:
        api_key_display = settings.WATSON_API_KEY[:20] if settings.WATSON_API_KEY else 'NOT SET'
        headers_display = {
            'x-api-key': f"{api_key_display}... (truncado)",
            'Content-Type': 'application/json'
        }
    
    print("📨 HEADERS HTTP (enviados a Watson):")
    print("-" * 80)
    for key, value in headers_display.items():
        print(f"  {key}: {value}")
    print("-" * 80)
    print()
    
    # 9. URL del endpoint
    url = f"{settings.WATSON_INSTANCE_URL.rstrip('/')}/v1/chat/completions"
    print(f"🌐 ENDPOINT URL:")
    print(f"  {url}")
    print()
    
    # 10. Hacer la clasificación REAL
    print("⏳ Paso 2: Clasificando emergencia con Watson...")
    print("   (Esto puede tardar 5-15 segundos...)")
    print()
    
    result = client.classify(descripcion.strip())
    
    # 11. Mostrar resultado
    print("=" * 80)
    print("📊 RESULTADO DE WATSON:")
    print("=" * 80)
    
    if result:
        print("✅ CLASIFICACIÓN EXITOSA!")
        print()
        print(json.dumps(result, indent=2, ensure_ascii=False))
        print()
        print("-" * 80)
        print("INTERPRETACIÓN:")
        print("-" * 80)
        print(f"  🏷️  Tipo de emergencia: {result.get('tipo', 'N/A').upper()}")
        print(f"  🚨 Código de urgencia: {result.get('codigo', 'N/A').upper()}")
        print(f"  📊 Score de gravedad: {result.get('score', 'N/A')}/100")
        print(f"  📝 Razones:")
        for i, razon in enumerate(result.get('razones', []), 1):
            print(f"      {i}. {razon}")
        print(f"  💡 Respuesta IA: {result.get('respuesta_ia', 'N/A')}")
        
        recursos = result.get('recursos', [])
        if recursos:
            print(f"  🚑 Recursos recomendados:")
            for recurso in recursos:
                tipo = recurso.get('tipo', 'N/A')
                cantidad = recurso.get('cantidad', 1)
                detalle = recurso.get('detalle', '')
                detalle_str = f" - {detalle}" if detalle else ""
                print(f"      • {cantidad}x {tipo}{detalle_str}")
        
        print()
        print("🎯 DATOS QUE WATSON 'VIO':")
        print(f"   - Código de emergencia: {result.get('codigo')}")
        print(f"   - Tipo de fuerza: {result.get('tipo')}")
        print(f"   - Agentes/móviles recomendados: {len(recursos)} recursos")
        for recurso in recursos:
            print(f"     → {recurso.get('cantidad')}x {recurso.get('tipo')}")
        
    else:
        print("❌ LA CLASIFICACIÓN FALLÓ")
        print()
        print("Posibles causas:")
        print("  1. Watson API endpoint no disponible (404)")
        print("  2. Token IAM inválido o expirado")
        print("  3. Watson no tiene acceso programático habilitado")
        print("  4. La instancia de Watson necesita configuración adicional")
        print()
        print("💡 El sistema usará el fallback local (reglas basadas en keywords)")
    
    print()
    print("=" * 80)
    print("FIN DEL TEST")
    print("=" * 80)

if __name__ == '__main__':
    main()
