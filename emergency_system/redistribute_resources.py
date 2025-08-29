#!/usr/bin/env python3
"""
Script mejorado para distribución inteligente de recursos en CABA
Evita el río y distribuye por barrios reales
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

from core.models import Emergency, Vehicle, Agent, Facility

# Zonas seguras de CABA (evitando el río y áreas no urbanas)
CABA_NEIGHBORHOODS = {
    'Microcentro': {
        'bounds': {'south': -34.6150, 'north': -34.5950, 'west': -58.3850, 'east': -58.3650},
        'weight': 3  # Mayor probabilidad
    },
    'San Telmo': {
        'bounds': {'south': -34.6250, 'north': -34.6150, 'west': -58.3750, 'east': -58.3650},
        'weight': 2
    },
    'Recoleta': {
        'bounds': {'south': -34.5950, 'north': -34.5800, 'west': -58.4050, 'east': -58.3850},
        'weight': 3
    },
    'Palermo': {
        'bounds': {'south': -34.5800, 'north': -34.5650, 'west': -58.4350, 'east': -58.4050},
        'weight': 4  # Área grande
    },
    'Belgrano': {
        'bounds': {'south': -34.5650, 'north': -34.5500, 'west': -58.4650, 'east': -58.4350},
        'weight': 3
    },
    'Villa Crespo': {
        'bounds': {'south': -34.5950, 'north': -34.5800, 'west': -58.4450, 'east': -58.4250},
        'weight': 2
    },
    'Caballito': {
        'bounds': {'south': -34.6250, 'north': -34.6100, 'west': -58.4450, 'east': -58.4250},
        'weight': 3
    },
    'Barracas': {
        'bounds': {'south': -34.6400, 'north': -34.6250, 'west': -58.3750, 'east': -58.3550},
        'weight': 2
    },
    'La Boca': {
        'bounds': {'south': -34.6450, 'north': -34.6300, 'west': -58.3650, 'east': -58.3550},
        'weight': 1
    },
    'Once': {
        'bounds': {'south': -34.6150, 'north': -34.6000, 'west': -58.4150, 'east': -58.3950},
        'weight': 2
    },
    'Balvanera': {
        'bounds': {'south': -34.6100, 'north': -34.5950, 'west': -58.4050, 'east': -58.3850},
        'weight': 2
    },
    'Almagro': {
        'bounds': {'south': -34.6100, 'north': -34.5950, 'west': -58.4250, 'east': -58.4050},
        'weight': 2
    },
    'Flores': {
        'bounds': {'south': -34.6400, 'north': -34.6200, 'west': -58.4700, 'east': -58.4450},
        'weight': 2
    },
    'Chacarita': {
        'bounds': {'south': -34.5850, 'north': -34.5700, 'west': -58.4550, 'east': -58.4350},
        'weight': 2
    },
    'Villa Urquiza': {
        'bounds': {'south': -34.5650, 'north': -34.5500, 'west': -58.4850, 'east': -58.4650},
        'weight': 2
    },
    'Paternal': {
        'bounds': {'south': -34.6000, 'north': -34.5850, 'west': -58.4650, 'east': -58.4450},
        'weight': 2
    }
}

# Ubicaciones específicas de bases/comisarías/cuarteles
BASE_LOCATIONS = [
    {"name": "Comisaría 1ra - Microcentro", "lat": -34.6037, "lon": -58.3748, "type": "policia"},
    {"name": "Cuartel Bomberos Recoleta", "lat": -34.5894, "lon": -58.3974, "type": "bomberos"},
    {"name": "Base SAME Central", "lat": -34.6037, "lon": -58.3816, "type": "same"},
    {"name": "Comisaría 4ta - San Telmo", "lat": -34.6178, "lon": -58.3730, "type": "policia"},
    {"name": "Cuartel Bomberos Palermo", "lat": -34.5750, "lon": -58.4210, "type": "bomberos"},
    {"name": "Base SAME Norte", "lat": -34.5632, "lon": -58.4361, "type": "same"},
    {"name": "Comisaría 14ta - Palermo", "lat": -34.5845, "lon": -58.4285, "type": "policia"},
    {"name": "Cuartel Bomberos Belgrano", "lat": -34.5589, "lon": -58.4502, "type": "bomberos"},
    {"name": "Base SAME Sur", "lat": -34.6298, "lon": -58.3645, "type": "same"},
    {"name": "Comisaría 6ta - Flores", "lat": -34.6298, "lon": -58.4445, "type": "policia"}
]

def get_weighted_neighborhood():
    """Selecciona un barrio basado en pesos probabilísticos"""
    neighborhoods = list(CABA_NEIGHBORHOODS.keys())
    weights = [CABA_NEIGHBORHOODS[n]['weight'] for n in neighborhoods]
    return random.choices(neighborhoods, weights=weights)[0]

def get_neighborhood_coordinates(neighborhood):
    """Genera coordenadas aleatorias dentro de un barrio específico"""
    bounds = CABA_NEIGHBORHOODS[neighborhood]['bounds']
    lat = random.uniform(bounds['south'], bounds['north'])
    lon = random.uniform(bounds['west'], bounds['east'])
    return lat, lon

def get_base_coordinates_for_force(force_name):
    """Obtiene coordenadas de bases reales para una fuerza específica"""
    force_bases = [loc for loc in BASE_LOCATIONS if loc['type'] == force_name.lower()]
    if force_bases:
        base = random.choice(force_bases)
        # Añadir pequeña variación aleatoria alrededor de la base
        lat_offset = random.uniform(-0.002, 0.002)  # ~200m
        lon_offset = random.uniform(-0.002, 0.002)
        return base['lat'] + lat_offset, base['lon'] + lon_offset
    else:
        # Fallback a coordenadas de barrio
        neighborhood = get_weighted_neighborhood()
        return get_neighborhood_coordinates(neighborhood)

def redistribute_vehicles_intelligently():
    """Redistribuye vehículos de manera inteligente"""
    vehicles = Vehicle.objects.all()
    print(f"🚗 Redistribuyendo {vehicles.count()} vehículos...")
    
    updated = 0
    for vehicle in vehicles:
        # Obtener coordenadas basadas en la fuerza
        lat, lon = get_base_coordinates_for_force(vehicle.force.name)
        
        vehicle.current_lat = lat
        vehicle.current_lon = lon
        vehicle.save(update_fields=['current_lat', 'current_lon'])
        
        updated += 1
        if updated % 50 == 0:
            print(f"   ✅ {updated} vehículos redistribuidos...")
    
    print(f"   🎯 Total: {updated} vehículos redistribuidos inteligentemente")

def redistribute_agents_intelligently():
    """Redistribuye agentes de manera inteligente"""
    agents = Agent.objects.all()
    print(f"👮 Redistribuyendo {agents.count()} agentes...")
    
    updated = 0
    for agent in agents:
        # Obtener coordenadas basadas en la fuerza
        lat, lon = get_base_coordinates_for_force(agent.force.name)
        
        agent.lat = lat
        agent.lon = lon
        agent.save(update_fields=['lat', 'lon'])
        
        updated += 1
        if updated % 50 == 0:
            print(f"   ✅ {updated} agentes redistribuidos...")
    
    print(f"   🎯 Total: {updated} agentes redistribuidos inteligentemente")

def validate_coordinates():
    """Valida que no haya coordenadas en el río"""
    print("🔍 Validando distribución...")
    
    # Verificar vehículos
    vehicles_in_river = Vehicle.objects.filter(
        current_lat__lt=-34.58,  # Al norte del río
        current_lon__gt=-58.37   # Al este, zona río
    ).count()
    
    # Verificar agentes
    agents_in_river = Agent.objects.filter(
        lat__lt=-34.58,
        lon__gt=-58.37
    ).count()
    
    print(f"   🚗 Vehículos posiblemente en río: {vehicles_in_river}")
    print(f"   👮 Agentes posiblemente en río: {agents_in_river}")
    
    if vehicles_in_river == 0 and agents_in_river == 0:
        print("   ✅ Distribución correcta - Sin recursos en el río")
    else:
        print("   ⚠️ Algunos recursos podrían estar en zonas problemáticas")

def show_distribution_stats():
    """Muestra estadísticas de distribución por barrio"""
    print("\n📊 Estadísticas de Distribución:")
    
    for neighborhood, data in CABA_NEIGHBORHOODS.items():
        bounds = data['bounds']
        
        vehicles_count = Vehicle.objects.filter(
            current_lat__gte=bounds['south'],
            current_lat__lte=bounds['north'],
            current_lon__gte=bounds['west'],
            current_lon__lte=bounds['east']
        ).count()
        
        agents_count = Agent.objects.filter(
            lat__gte=bounds['south'],
            lat__lte=bounds['north'],
            lon__gte=bounds['west'],
            lon__lte=bounds['east']
        ).count()
        
        if vehicles_count > 0 or agents_count > 0:
            print(f"   📍 {neighborhood}: {vehicles_count} vehículos, {agents_count} agentes")

if __name__ == '__main__':
    print("🗺️ REDISTRIBUCIÓN INTELIGENTE DE RECURSOS CABA")
    print("=" * 60)
    
    # Redistribuir recursos
    redistribute_vehicles_intelligently()
    print()
    redistribute_agents_intelligently()
    print()
    
    # Validar distribución
    validate_coordinates()
    
    # Mostrar estadísticas
    show_distribution_stats()
    
    print("\n=" * 60)
    print("✅ Redistribución inteligente completada!")
    print("🎯 Los recursos ahora están distribuidos en zonas urbanas reales")
    print("🚫 Se evitaron el río y zonas no urbanas")
