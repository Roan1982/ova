import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'emergency_app.settings')
django.setup()

from core.models import Force, Emergency
from django.utils import timezone

# Obtener la fuerza de Policía
policia = Force.objects.get(name='Policía')

# Crear emergencia que requiere Policía en Buenos Aires (donde están los vehículos)
emergency = Emergency.objects.create(
    description="Disturbios en Plaza de Mayo - control de multitudes necesario",
    code="rojo",  # Emergencia crítica
    location_lat=-34.608, # Plaza de Mayo, Buenos Aires
    location_lon=-58.372,
    address="Plaza de Mayo, CABA",
    status="pendiente",
    assigned_force=policia,
    priority=10,
    ai_response="Emergencia de seguridad pública crítica - Se requiere intervención policial inmediata para control de multitudes en zona céntrica de Buenos Aires.",
    reported_at=timezone.now()
)

print(f"✅ Nueva emergencia de Policía creada en Buenos Aires:")
print(f"   ID: {emergency.id}")
print(f"   Descripción: {emergency.description}")
print(f"   Fuerza asignada: {emergency.assigned_force.name}")
print(f"   Ubicación: {emergency.location_lat}, {emergency.location_lon}")
print(f"   Dirección: {emergency.address}")

# Mostrar vehículos de policía disponibles cercanos
from core.models import Vehicle
vehiculos_policia = Vehicle.objects.filter(force=policia, status='disponible')
print(f"\n🚔 Vehículos de Policía disponibles: {vehiculos_policia.count()}")

# Calcular distancia aproximada a algunos vehículos cercanos
import math

def distancia_aproximada(lat1, lon1, lat2, lon2):
    """Calcula distancia aproximada en km usando fórmula haversine simplificada"""
    R = 6371  # Radio de la Tierra en km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

print(f"\n📍 Vehículos más cercanos a la emergencia:")
distancias = []
for v in vehiculos_policia[:10]:  # Solo los primeros 10 para no sobrecargar
    dist = distancia_aproximada(emergency.location_lat, emergency.location_lon, v.current_lat, v.current_lon)
    distancias.append((v, dist))

# Ordenar por distancia
distancias.sort(key=lambda x: x[1])

for i, (vehiculo, dist) in enumerate(distancias[:5], 1):
    print(f"   {i}. {vehiculo.type}: {dist:.2f}km ({vehiculo.current_lat:.3f}, {vehiculo.current_lon:.3f})")
