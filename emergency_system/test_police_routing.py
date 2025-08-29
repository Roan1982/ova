import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'emergency_app.settings')
django.setup()

from core.models import Force, Emergency
from django.utils import timezone

# Obtener la fuerza de Policía
try:
    policia = Force.objects.get(name='Policía')
    print(f"✓ Fuerza de Policía encontrada: {policia}")
except Force.DoesNotExist:
    policia = Force.objects.create(name='Policía')
    print(f"✓ Fuerza de Policía creada: {policia}")

# Crear emergencia que requiere Policía
emergency = Emergency.objects.create(
    description="Disturbios en manifestación - necesario control de multitudes",
    code="rojo",  # Código correcto del modelo
    location_lat=-31.4159,  # Campo correcto para latitud
    location_lon=-64.1841,  # Campo correcto para longitud
    address="Plaza San Martín, Córdoba",
    status="pendiente",  # Status correcto del modelo
    assigned_force=policia,  # Asignamos la instancia de Force
    priority=10,  # Prioridad numérica
    ai_response="Emergencia de seguridad pública - Se requiere intervención policial inmediata para control de multitudes y mantenimiento del orden público.",
    reported_at=timezone.now()  # Campo correcto para timestamp
)

print(f"✅ Emergencia creada exitosamente:")
print(f"   ID: {emergency.id}")
print(f"   Descripción: {emergency.description}")
print(f"   Fuerza asignada: {emergency.assigned_force.name}")
print(f"   Código: {emergency.code}")
print(f"   Ubicación: {emergency.location_lat}, {emergency.location_lon}")
print(f"   Dirección: {emergency.address}")
print(f"   Prioridad: {emergency.priority}")

# Verificar que aparezca en la lista
emergencies = Emergency.objects.filter(status='pendiente').order_by('-reported_at')
print(f"\n📋 Total de emergencias pendientes: {emergencies.count()}")
for i, e in enumerate(emergencies[:5], 1):
    force_name = e.assigned_force.name if e.assigned_force else "No asignada"
    print(f"   {i}. ID {e.id}: {e.description[:50]}... - Fuerza: {force_name}")
