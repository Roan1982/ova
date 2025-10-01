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

def demo_emergency_parking():
    """Demostración del sistema de estacionamiento para emergencias"""

    print("🚨 DEMO: Sistema de Estacionamiento para Emergencias")
    print("=" * 60)

    # Crear optimizador de rutas
    optimizer = RouteOptimizer()

    # Simular ubicación de emergencia en el centro de Buenos Aires
    emergency_location = (-34.6037, -58.3816)  # Obelisco
    print(f"📍 Ubicación de emergencia: {emergency_location}")

    # Simular ubicación de vehículo de emergencia
    vehicle_location = (-34.6050, -58.3800)  # Cerca del Obelisco
    print(f"🚐 Ubicación del vehículo: {vehicle_location}")

    # Buscar estacionamientos disponibles
    print("\n🏪 Buscando estacionamientos disponibles...")
    parking_options = optimizer.find_emergency_parking(
        emergency_location,
        max_distance_meters=800,
        min_spaces_required=1
    )

    if not parking_options:
        print("❌ No se encontraron estacionamientos disponibles")
        return

    print(f"✅ Encontrados {len(parking_options)} opciones de estacionamiento")

    # Mostrar las mejores opciones
    print("\n📋 Mejores opciones de estacionamiento:")
    for i, parking in enumerate(parking_options[:3], 1):
        print(f"{i}. {parking['name']}")
        print(f"   📍 Dirección: {parking['address']}")
        print(f"   📏 Distancia: {parking['distance_meters']:.0f}m")
        print(f"   🏃 Tiempo caminando: {parking['walking_time_minutes']:.1f} min")
        print(f"   🚗 Espacios disponibles: {parking['available_spaces']}")
        print(f"   💰 Pago requerido: {'Sí' if parking['is_paid'] else 'No'}")
        print()

    # Crear plan completo de estacionamiento
    print("📝 Generando plan completo de estacionamiento...")
    plan = optimizer.get_emergency_parking_plan(
        vehicle_location,
        emergency_location,
        max_parking_distance=600
    )

    if plan['success'] and plan['recommended_plan']:
        recommended = plan['recommended_plan']
        parking_info = recommended['parking_info']
        route_plan = recommended['route_plan']

        print("✅ Plan de estacionamiento recomendado:")
        print(f"🏪 Estacionamiento: {parking_info['name']}")
        print(f"📍 Dirección: {parking_info['address']}")
        print(f"📏 Distancia a emergencia: {parking_info['distance_meters']:.0f}m")
        print(f"🚗 Tiempo de manejo: {route_plan['driving_route']['duration']/60:.1f} min")
        print(f"🏃 Tiempo caminando: {route_plan['walking_time_seconds']/60:.1f} min")
        print(f"⏱️ ETA total: {recommended['total_eta_minutes']:.1f} min")
        print(f"📊 Espacios disponibles: {parking_info['available_spaces']}")

    else:
        print("❌ No se pudo generar un plan de estacionamiento")

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