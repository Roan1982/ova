"""
Script de prueba para verificar la integración de Watson Orchestrate.
Ejecutar: python test_watson_integration.py
"""

import os
import sys
import json
import django
from pathlib import Path

# Hacer import resolvible: añadir el directorio padre del proyecto (workspace root)
# Ej: si este archivo está en .../ova/emergency_system/, añadimos .../ova
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Cargar .env local si está presente (opcional, settings.py también lo carga)
try:
	from dotenv import load_dotenv
	env_path = Path(__file__).resolve().parent / '.env'
	if env_path.exists():
		load_dotenv(env_path)
except Exception:
	# dotenv no instalada o falla; no es crítico si las variables están en el entorno
	pass

# Forzar el proveedor a 'watson' porque elegiste la Opción 1 (llamado en vivo)
os.environ.setdefault('AI_PROVIDER', 'watson')

# Configurar el módulo de settings correcto para este proyecto Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'emergency_app.settings')

django.setup()

def main():
	"""Script sencillo para invocar CloudAIClient.classify() con Watson si está configurado."""
	# Leer variables importantes (settings.py también las carga desde os.environ)
	watson_key = os.environ.get('WATSON_API_KEY')
	watson_url = os.environ.get('WATSON_INSTANCE_URL')

	if not watson_key or not watson_url:
		print("[ERROR] WATSON_API_KEY o WATSON_INSTANCE_URL no están configuradas en el entorno (.env).")
		print(" - Coloca tu clave en emergency_system/.env como WATSON_API_KEY=<tu_api_key> o exportala en el entorno.")
		print(" - No se realizará la llamada en vivo. Si quieres que agregue la key al .env, confirma y la escribiré.")
		sys.exit(2)

	# Importar el cliente de IA en la app
	try:
		from core.llm import CloudAIClient
	except Exception as exc:
		print(f"[ERROR] No se pudo importar CloudAIClient: {exc}")
		sys.exit(3)

	client = CloudAIClient()

	sample_description = (
		"Reportan un accidente de tránsito en Av. Corrientes con una persona inconsciente y posibles heridas. "
		"Se solicita clasificación rápida y recursos necesarios."
	)

	print("Llamando a Watson Orchestrate (CloudAIClient.classify) con AI_PROVIDER=watson... Esto puede tardar unos segundos.")
	try:
		result = client.classify(sample_description)
		if not result:
			print("No se obtuvo respuesta o la clasificación falló. Revisa los logs o la clave.")
			sys.exit(1)

		# Imprimir resultado JSON de forma legible
		print(json.dumps(result, ensure_ascii=False, indent=2))
	except Exception as exc:
		print(f"[ERROR] Excepción al invocar la IA en la nube: {exc}")
		sys.exit(4)


if __name__ == '__main__':
	main()