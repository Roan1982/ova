import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'emergency_app.settings')
django.setup()

from core.models import Force, Vehicle, Agent

# Obtener la fuerza de Policía
try:
    policia = Force.objects.get(name='Policía')
    print(f"✓ Fuerza de Policía encontrada: {policia}")
except Force.DoesNotExist:
    policia = Force.objects.create(name='Policía')
    print(f"✓ Fuerza de Policía creada: {policia}")

# Verificar vehículos existentes de Policía
vehiculos_policia = Vehicle.objects.filter(force=policia)
print(f"🚔 Vehículos de Policía existentes: {vehiculos_policia.count()}")

# Verificar agentes de Policía
agentes_policia = Agent.objects.filter(force=policia)
print(f"👮 Agentes de Policía existentes: {agentes_policia.count()}")

# Si no hay vehículos de Policía, crear algunos
if vehiculos_policia.count() == 0:
    print("⚠️ No hay vehículos de Policía. Creando algunos...")
    
    # Crear vehículos de Policía en diferentes ubicaciones de Córdoba
    Vehicle.objects.create(
        force=policia,
        type='Patrulla',
        current_lat=-31.4201,  # Centro de Córdoba
        current_lon=-64.1888,
        status='disponible'
    )
    
    Vehicle.objects.create(
        force=policia,
        type='Móvil Policial',
        current_lat=-31.4135,  # Nueva Córdoba
        current_lon=-64.1810,
        status='disponible'
    )
    
    Vehicle.objects.create(
        force=policia,
        type='Patrulla',
        current_lat=-31.4255,  # Güemes
        current_lon=-64.1875,
        status='disponible'
    )
    
    print("✅ Vehículos de Policía creados exitosamente")

# Si no hay agentes de Policía, crear algunos
if agentes_policia.count() == 0:
    print("⚠️ No hay agentes de Policía. Creando algunos...")
    
    Agent.objects.create(
        name='Oficial Rodríguez',
        force=policia,
        lat=-31.4201,
        lon=-64.1888,
        available=True
    )
    
    Agent.objects.create(
        name='Sargento García',
        force=policia,
        lat=-31.4135,
        lon=-64.1810,
        available=True
    )
    
    Agent.objects.create(
        name='Inspector López',
        force=policia,
        lat=-31.4255,
        lon=-64.1875,
        available=True
    )
    
    print("✅ Agentes de Policía creados exitosamente")

# Verificar resultado final
vehiculos_policia = Vehicle.objects.filter(force=policia)
agentes_policia = Agent.objects.filter(force=policia)
print(f"\n📊 Resumen final:")
print(f"   🚔 Vehículos de Policía: {vehiculos_policia.count()}")
print(f"   👮 Agentes de Policía: {agentes_policia.count()}")

print("\n🚔 Vehículos de Policía:")
for v in vehiculos_policia:
    print(f"   - {v.type}: {v.current_lat}, {v.current_lon} ({v.status})")

print("\n👮 Agentes de Policía:")
for a in agentes_policia:
    status = 'Disponible' if hasattr(a, 'available') and a.available else 'Sin estado específico'
    print(f"   - {a.name}: {a.lat}, {a.lon} ({status})")
