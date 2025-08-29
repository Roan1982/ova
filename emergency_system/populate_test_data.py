import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'emergency_app.settings')
django.setup()

from core.models import Force, Vehicle, Emergency

# Limpiar datos existentes
Force.objects.all().delete()
Vehicle.objects.all().delete()
Emergency.objects.all().delete()

# Crear fuerzas (comenzando con Bomberos)
bomberos = Force.objects.create(name='Bomberos')
same = Force.objects.create(name='SAME')
policia = Force.objects.create(name='Policía')

# Crear vehículos
Vehicle.objects.create(force=bomberos, type='Camión de Bomberos', current_lat=-34.6037, current_lon=-58.3816, status='disponible')
Vehicle.objects.create(force=same, type='Ambulancia', current_lat=-34.6097, current_lon=-58.3916, status='disponible')

# Crear emergencias de prueba
Emergency.objects.create(
    description='Incendio masivo en edificio',
    address='Av. 9 de Julio 100, CABA',
    location_lat=-34.5997,
    location_lon=-58.3756
)  # Se clasificará como 'rojo'

Emergency.objects.create(
    description='Accidente de tránsito con heridos',
    address='Av. Corrientes 2000, CABA',
    location_lat=-34.6157,
    location_lon=-58.3856
)  # 'amarillo'

Emergency.objects.create(
    description='Dolor de cabeza leve',
    address='Calle Florida 500, CABA',
    location_lat=-34.6057,
    location_lon=-58.3956
)  # 'verde'

print('Datos de prueba poblados exitosamente.')
