#!/usr/bin/env python
"""
Script de demostración del sistema de estacionamiento para emergencias
"""
import os
import sys
import django

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'emergency_app.settings')
sys.path.insert(0, os.path.dirname(__file__))
django.setup()

from core.routing import RouteOptimizer
from core.models import ParkingSpot
from django.utils import timezone
from core.llm import classify_with_ai
import argparse
import time


def narrate(msg: str, pause: float = 1.2, fast: bool = False):
    """Imprime un mensaje de narración y opcionalmente espera (modo rápido salta las esperas)."""
    prefix = "NARRACIÓN:" 
    print(f"{prefix} {msg}")
    if not fast and pause and pause > 0:
        time.sleep(pause)


def post_state_to_server(step: int, title: str, text: str, fast: bool = False):
    """Intentar postear el estado de la demo al servidor para sincronización (dev-only)."""
    try:
        import requests
        # Allow overriding the demo sync base URL via environment variable so the
        # script isn't hard-coded to localhost:8000. Keep timeout short and
        # fail silently unless DEMO_SYNC_VERBOSE=1 is set.
        base = os.environ.get('DEMO_SYNC_BASE_URL', 'http://127.0.0.1:8000')
        # server exposes demo sync endpoints at /demo/sync/... ; ensure we use that path
        url = f"{base.rstrip('/')}/demo/sync/state/update/"
        payload = {'step': step, 'title': title, 'text': text}
        # No bloquear si el servidor no está levantado; timeout corto
        requests.post(url, json=payload, timeout=0.8)
    except Exception:
        # Silencioso por defecto: el servidor puede no estar ejecutándose en demos
        # offline. Activa DEMO_SYNC_VERBOSE=1 para ver errores de conexión.
        if os.environ.get('DEMO_SYNC_VERBOSE') == '1':
            import traceback
            print("[demo sync] fallo al postear estado:")
            traceback.print_exc()
    return

def demo_emergency_parking():
    """Demostración del sistema de estacionamiento para emergencias"""
    parser = argparse.ArgumentParser(description='Demo narrada del sistema de estacionamiento (offline).')
    parser.add_argument('--fast', action='store_true', help='Modo rápido (sin esperas)')
    args = parser.parse_args()
    fast = args.fast

    print("\n🚨 DEMO NARRADA: Sistema de Estacionamiento para Emergencias")
    print("=" * 60)

    narrate("Iniciando demo y creando optimizador de rutas (fallback local habilitado).", pause=1.0, fast=fast)
    optimizer = RouteOptimizer()

    # Simular ubicación de emergencia en el centro de Buenos Aires
    emergency_location = (-34.6037, -58.3816)  # Obelisco
    narrate(f"Ubicación de emergencia simulada en: {emergency_location}", pause=1.0, fast=fast)

    # Simular ubicación de vehículo de emergencia
    vehicle_location = (-34.6050, -58.3800)  # Cerca del Obelisco
    narrate(f"Vehículo de emergencia ubicado en: {vehicle_location}", pause=1.0, fast=fast)

    # Paso: Clasificación por IA
    narrate("Paso: Clasificación automática de la emergencia por IA (cloud o fallback local).", pause=1.0, fast=fast)
    desc = 'Reporte: persona herida, ubicación cercana a zona concurrida, posible agresión.'
    try:
        ai_result = classify_with_ai(desc)
        narrate(f"Resultado IA: tipo={ai_result.get('tipo')}, codigo={ai_result.get('codigo')}, recursos={ai_result.get('recommended_resources')}", pause=1.0, fast=fast)
        post_state_to_server(2, 'Clasificación', f"IA: {ai_result.get('tipo')} / {ai_result.get('codigo')}", fast=fast)
    except Exception as e:
        narrate(f"La clasificación IA falló o devolvió fallback: {e}", pause=1.0, fast=fast)
        post_state_to_server(2, 'Clasificación', f"IA fallback: {e}", fast=fast)

    # Buscar estacionamientos disponibles
    narrate("Buscando estacionamientos disponibles cercanos (consulta local a DB).", pause=1.0, fast=fast)
    parking_options = optimizer.find_emergency_parking(
        emergency_location,
        max_distance_meters=800,
        min_spaces_required=1
    )

    if not parking_options:
        narrate("No se encontraron estacionamientos disponibles. Intentando fallback...", pause=1.0, fast=fast)
        print("❌ No se encontraron estacionamientos disponibles")
        return

    narrate(f"Encontradas {len(parking_options)} opciones de estacionamiento. Mostrando top 3.", pause=1.0, fast=fast)
    post_state_to_server(3, 'Estacionamientos encontrados', f"{len(parking_options)} opciones", fast=fast)
    for i, parking in enumerate(parking_options[:3], 1):
        narrate(f"Opción {i}: {parking['name']} — {parking['distance_meters']:.0f}m — espacios: {parking['available_spaces']} — pago: {'Sí' if parking['is_paid'] else 'No'}", pause=0.6, fast=fast)

    # Crear plan completo de estacionamiento
    narrate("Generando plan completo de estacionamiento y calculando rutas (optimización multi-proveedor con fallback).", pause=1.0, fast=fast)
    post_state_to_server(4, 'Generando plan', 'Calculando rutas y ETA', fast=fast)
    plan = optimizer.get_emergency_parking_plan(
        vehicle_location,
        emergency_location,
        max_parking_distance=600
    )

    if plan['success'] and plan['recommended_plan']:
        recommended = plan['recommended_plan']
        parking_info = recommended['parking_info']
        route_plan = recommended['route_plan']

        narrate("Plan recomendado generado:", pause=0.8, fast=fast)
        post_state_to_server(5, 'Plan recomendado', f"Estacionamiento: {parking_info['name']}", fast=fast)
        print(f"  - Estacionamiento: {parking_info['name']}")
        print(f"  - Dirección: {parking_info['address']}")
        print(f"  - Distancia a emergencia: {parking_info['distance_meters']:.0f} m")
        # route_plan may have driving_route or be None if fallback
        driving_route = route_plan.get('driving_route')
        if driving_route:
            duration_min = driving_route.get('duration', 0) / 60 if driving_route.get('duration') else None
            narrate(f"Tiempo estimado de manejo: {duration_min:.1f} min (según proveedor: {driving_route.get('provider', 'fallback')})", pause=0.8, fast=fast)
        else:
            narrate("No se calculó ruta de manejo; usando estimación de fallback.", pause=0.8, fast=fast)

        narrate(f"Tiempo caminando desde estacionamiento: {route_plan['walking_time_seconds']/60:.1f} min", pause=0.8, fast=fast)
        narrate(f"ETA total estimada: {recommended['total_eta_minutes']:.1f} min", pause=0.8, fast=fast)
        narrate(f"Espacios disponibles en el lugar: {parking_info['available_spaces']}", pause=0.6, fast=fast)
    else:
        narrate("No se pudo generar un plan de estacionamiento automáticamente.", pause=0.8, fast=fast)

    narrate("Demo finalizada. Resumen: clasificación IA, asignación de recursos y plan de estacionamiento creados (offline).", pause=1.0, fast=fast)
    post_state_to_server(7, 'Fin', 'Demo finalizada', fast=fast)
    print("\n" + "=" * 60)
    print("🎉 Demo completada exitosamente!")

if __name__ == '__main__':
    # Crear algunos datos de prueba si no existen
    if not ParkingSpot.objects.exists():
        print("📝 Creando datos de prueba...")
        ParkingSpot.objects.create(
            external_id='demo_parking_001',
            name='Estacionamiento Obelisco',
            address='Av. 9 de Julio 1234',
            lat=-34.6037,
            lon=-58.3816,
            total_spaces=100,
            available_spaces=45,
            spot_type='street',
            is_paid=True,
            max_duration_hours=2,
            is_active=True,
            last_updated=timezone.now()
        )
        ParkingSpot.objects.create(
            external_id='demo_parking_002',
            name='Estacionamiento Tribunales',
            address='Talcahuano 550',
            lat=-34.6018,
            lon=-58.3851,
            total_spaces=50,
            available_spaces=20,
            spot_type='garage',
            is_paid=False,
            max_duration_hours=8,
            is_active=True,
            last_updated=timezone.now()
        )
        print("✅ Datos de prueba creados")

    demo_emergency_parking()