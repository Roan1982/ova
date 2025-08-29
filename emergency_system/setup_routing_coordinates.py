#!/usr/bin/env python3
"""
Script para agregar coordenadas a emergencias existentes y crear algunas de prueba
"""

import os
import sys
import django
import random

# Configurar Django
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'emergency_app.settings')
django.setup()

from core.models import Emergency, Vehicle, Agent

# Coordenadas de CABA (aproximadas)
CABA_BOUNDS = {
    'south': -34.7056,
    'north': -34.5266,
    'west': -58.5315,
    'east': -58.3324
}

# Direcciones comunes en CABA con coordenadas aproximadas
SAMPLE_LOCATIONS = [
    {"address": "Av. 9 de Julio 1000, CABA", "lat": -34.6037, "lon": -58.3816},
    {"address": "Av. Corrientes 1500, CABA", "lat": -34.6037, "lon": -58.3915},
    {"address": "Florida 800, CABA", "lat": -34.5998, "lon": -58.3748},
    {"address": "San Martín 400, Microcentro", "lat": -34.6045, "lon": -58.3734},
    {"address": "Av. Santa Fe 2000, Recoleta", "lat": -34.5945, "lon": -58.3960},
    {"address": "Av. Las Heras 1800, Recoleta", "lat": -34.5895, "lon": -58.3945},
    {"address": "Scalabrini Ortiz 1200, Palermo", "lat": -34.5750, "lon": -58.4210},
    {"address": "Av. Cabildo 3000, Belgrano", "lat": -34.5632, "lon": -58.4561},
    {"address": "Av. Rivadavia 5000, Caballito", "lat": -34.6185, "lon": -58.4365},
    {"address": "Defensa 400, San Telmo", "lat": -34.6178, "lon": -58.3730},
    {"address": "Paseo Colón 850, Barracas", "lat": -34.6298, "lon": -58.3645},
    {"address": "Av. Juan B. Justo 2500, Villa Crespo", "lat": -34.5945, "lon": -58.4385},
    {"address": "Monroe 2800, Belgrano", "lat": -34.5589, "lon": -58.4502},
    {"address": "Av. Directorio 2000, Parque Chacabuco", "lat": -34.6298, "lon": -58.4345},
    {"address": "Av. Warnes 1500, Villa Crespo", "lat": -34.5856, "lon": -58.4298}
]

def random_caba_coordinates():
    """Genera coordenadas aleatorias dentro de CABA"""
    lat = random.uniform(CABA_BOUNDS['south'], CABA_BOUNDS['north'])
    lon = random.uniform(CABA_BOUNDS['west'], CABA_BOUNDS['east'])
    return lat, lon

def update_existing_emergencies():
    """Actualiza emergencias existentes con coordenadas"""
    emergencies = Emergency.objects.filter(
        models.Q(location_lat__isnull=True) | models.Q(location_lon__isnull=True)
    )
    
    print(f"Actualizando {emergencies.count()} emergencias sin coordenadas...")
    
    for emergency in emergencies:
        # Usar ubicación de muestra si está disponible
        if len(SAMPLE_LOCATIONS) > 0:
            location = random.choice(SAMPLE_LOCATIONS)
            emergency.location_lat = location['lat']
            emergency.location_lon = location['lon']
            if not emergency.address:
                emergency.address = location['address']
        else:
            # Coordenadas aleatorias en CABA
            emergency.location_lat, emergency.location_lon = random_caba_coordinates()
            if not emergency.address:
                emergency.address = "CABA, Argentina"
        
        emergency.save(update_fields=['location_lat', 'location_lon', 'address'])
        print(f"✅ Emergencia #{emergency.id}: {emergency.address}")

def update_vehicles_positions():
    """Actualiza posiciones de vehículos"""
    vehicles = Vehicle.objects.filter(
        models.Q(current_lat__isnull=True) | models.Q(current_lon__isnull=True)
    )
    
    print(f"Actualizando posiciones de {vehicles.count()} vehículos...")
    
    for vehicle in vehicles:
        vehicle.current_lat, vehicle.current_lon = random_caba_coordinates()
        vehicle.save(update_fields=['current_lat', 'current_lon'])
        print(f"✅ {vehicle.type} ({vehicle.force.name})")

def update_agents_positions():
    """Actualiza posiciones de agentes"""
    agents = Agent.objects.filter(
        models.Q(lat__isnull=True) | models.Q(lon__isnull=True)
    )
    
    print(f"Actualizando posiciones de {agents.count()} agentes...")
    
    for agent in agents:
        agent.lat, agent.lon = random_caba_coordinates()
        agent.save(update_fields=['lat', 'lon'])
        print(f"✅ {agent.name} ({agent.force.name})")

def create_test_emergencies():
    """Crear algunas emergencias de prueba con coordenadas"""
    test_emergencies = [
        {
            "description": "Incendio en edificio de oficinas con personas atrapadas",
            "address": "Av. 9 de Julio 1200, Microcentro",
            "lat": -34.6037,
            "lon": -58.3816,
            "code": "rojo"
        },
        {
            "description": "Accidente de tránsito con heridos graves",
            "address": "Av. Santa Fe y Scalabrini Ortiz, Palermo",
            "lat": -34.5845,
            "lon": -58.4210,
            "code": "amarillo"
        },
        {
            "description": "Persona inconsciente en vía pública",
            "address": "Florida 500, Microcentro",
            "lat": -34.5998,
            "lon": -58.3748,
            "code": "amarillo"
        },
        {
            "description": "Robo en comercio",
            "address": "Defensa 800, San Telmo",
            "lat": -34.6178,
            "lon": -58.3730,
            "code": "verde"
        }
    ]
    
    print(f"Creando {len(test_emergencies)} emergencias de prueba...")
    
    for data in test_emergencies:
        if not Emergency.objects.filter(description=data["description"]).exists():
            emergency = Emergency.objects.create(
                description=data["description"],
                address=data["address"],
                location_lat=data["lat"],
                location_lon=data["lon"],
                code=data["code"],
                status='pendiente'
            )
            print(f"✅ Emergencia #{emergency.id}: {data['description'][:50]}...")
        else:
            print(f"⚠️ Ya existe: {data['description'][:50]}...")

if __name__ == '__main__':
    from django.db import models
    
    print("🚨 Configurando coordenadas para sistema de ruteo...")
    print("=" * 60)
    
    # Actualizar emergencias existentes
    update_existing_emergencies()
    print()
    
    # Actualizar vehículos
    update_vehicles_positions()
    print()
    
    # Actualizar agentes
    update_agents_positions()
    print()
    
    # Crear emergencias de prueba
    create_test_emergencies()
    print()
    
    print("=" * 60)
    print("✅ Configuración de coordenadas completada!")
    print()
    print("Resumen:")
    print(f"📍 Emergencias: {Emergency.objects.exclude(location_lat__isnull=True).count()}")
    print(f"🚗 Vehículos: {Vehicle.objects.exclude(current_lat__isnull=True).count()}")
    print(f"👮 Agentes: {Agent.objects.exclude(lat__isnull=True).count()}")
    print()
    print("🗺️ El sistema de ruteo está listo para usar!")
    print("   - Haga clic en una emergencia en el mapa")
    print("   - Use '🗺️ Calcular Rutas' para ver rutas optimizadas")  
    print("   - Use '⚡ Asignar Óptimo' para despachar recursos")
