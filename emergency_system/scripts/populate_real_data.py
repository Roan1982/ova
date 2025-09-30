import os
import sys
import django
import requests
import time
import random

# Asegurar que el proyecto esté en PYTHONPATH
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'emergency_app.settings')
django.setup()

from core.models import Force, Vehicle, Agent, Hospital, Facility

HEADERS = {'User-Agent': 'ova-emergency/1.0'}
CITY_SUFFIX = ', Ciudad Autónoma de Buenos Aires, Argentina'
RESET = True  # Si True, limpia datos previos de Hospital, Vehicle y Agent
SLEEP_SEC = 2.0  # espera entre requests a Nominatim

# Listas ampliadas (CABA)
HOSPITAL_NAMES = [
    # Generales de Agudos
    'Hospital General de Agudos Dr. Juan A. Fernández',
    'Hospital General de Agudos Bernardino Rivadavia',
    'Hospital General de Agudos Ignacio Pirovano',
    'Hospital General de Agudos Dr. Cosme Argerich',
    'Hospital General de Agudos Dr. Enrique Tornú',
    'Hospital General de Agudos Dr. Teodoro Álvarez',
    'Hospital General de Agudos Dr. Carlos G. Durand',
    'Hospital General de Agudos José María Ramos Mejía',
    'Hospital General de Agudos Dr. Pedro de Elizalde',
    'Hospital General de Agudos Dr. José María Penna',
    'Hospital General de Agudos Dr. Teodoro Álvarez',
    'Hospital General de Agudos Dr. Abel Zubizarreta',
    'Hospital General de Agudos Dr. I. Piñero',
    'Hospital General de Agudos Santojanni',
    # Especializados y pediátricos
    'Hospital de Infecciosas Dr. Francisco Javier Muñiz',
    'Hospital de Niños Ricardo Gutiérrez',
    'Hospital Garrahan',
]

FIRE_STATIONS = [
    'Cuartel de Bomberos de la Ciudad Recoleta',
    'Cuartel de Bomberos de la Ciudad Chacarita',
    'Cuartel de Bomberos de la Ciudad Villa Crespo',
    'Cuartel de Bomberos de la Ciudad Barracas',
    'Cuartel de Bomberos de la Ciudad Parque Patricios',
    'Cuartel de Bomberos de la Ciudad La Boca',
    'Cuartel de Bomberos de la Ciudad Caballito',
    'Cuartel de Bomberos de la Ciudad Flores',
    'Cuartel de Bomberos de la Ciudad Belgrano',
    'Cuartel de Bomberos de la Ciudad Palermo',
    'Cuartel de Bomberos de la Ciudad Mataderos',
    'Cuartel de Bomberos de la Ciudad Lugano',
    'Cuartel de Bomberos de la Ciudad Devoto',
]

POLICE_STATIONS = [
    'Comisaría 1A, Retiro',
    'Comisaría 2A, Recoleta',
    'Comisaría 3A, Balvanera',
    'Comisaría 4A, San Nicolás',
    'Comisaría 5A, Almagro',
    'Comisaría 6A, Caballito',
    'Comisaría 7A, Flores',
    'Comisaría 8A, Villa Soldati',
    'Comisaría 9A, Parque Patricios',
    'Comisaría 10A, Villa Real',
    'Comisaría 11A, Villa General Mitre',
    'Comisaría 12A, Coghlan',
    'Comisaría 13A, Belgrano',
    'Comisaría 14A, Palermo',
    'Comisaría 15A, Villa Ortúzar',
]

TRANSITO_BASES = [
    'Dirección General de Tránsito, Parque Rivadavia',
    'Centro de Gestión y Participación Comunal 7, Parque Centenario',
    'Dirección de Tránsito, 9 de Julio',
    'Centro de Tránsito, General Paz',
    'Centro de Control de Tránsito, Autopista Illia',
]

# Nombres plausibles para agentes
FIRST_NAMES = ['Juan','María','Carlos','Lucía','Pedro','Ana','Diego','Sofía','Martín','Laura','Pablo','Valentina','Joaquín','Camila','Nicolás','Florencia','Santiago','Julieta','Agustín','Carolina']
LAST_NAMES = ['Pérez','Gómez','Ruiz','Díaz','López','Torres','Fernández','Martínez','Castro','Sánchez','Romero','Ríos','Gutiérrez','Mendoza','Silva','Suárez','Vega','Ramos','Jiménez','Herrera']

ROLES = {
    'SAME': ['Chofer','Paramédico','Médico'],
    'Bomberos': ['Bombero','Cabo','Sargento','Oficial'],
    'Policía': ['Oficial','Cabo','Sargento','Subinspector'],
    'Tránsito': ['Inspector','Agente']
}


def geocode_one(name, retries=3):
    for attempt in range(retries):
        try:
            q = f"{name}{CITY_SUFFIX}"
            url = f"https://nominatim.openstreetmap.org/search?format=json&q={requests.utils.quote(q)}&limit=1"
            r = requests.get(url, headers=HEADERS, timeout=30)
            r.raise_for_status()
            arr = r.json()
            if arr:
                item = arr[0]
                return {
                    'display_name': item.get('display_name'),
                    'lat': float(item['lat']),
                    'lon': float(item['lon'])
                }
        except Exception as e:
            print(f"Intento {attempt+1} falló para {name}: {e}")
            if attempt < retries - 1:
                time.sleep(2)  # Espera antes de reintentar
    return None


def ensure_forces():
    names = ['SAME', 'Bomberos', 'Policía', 'Tránsito']
    out = {}
    for n in names:
        f, _ = Force.objects.get_or_create(name=n)
        out[n] = f
    return out


def reset_data():
    if RESET:
        print('Limpiando datos previos...')
        Agent.objects.all().delete()
        Vehicle.objects.all().delete()
        Hospital.objects.all().delete()


def create_hospitals():
    created = 0
    for name in HOSPITAL_NAMES:
        if Hospital.objects.filter(name=name).exists():
            continue
        g = geocode_one(name)
        time.sleep(SLEEP_SEC)
        if not g:
            print(f"No encontrado hospital: {name}")
            continue
        total = random.choice([150, 180, 200, 220, 250, 300])
        occupied = random.randint(int(total*0.3), int(total*0.85))
        Hospital.objects.create(
            name=name,
            address=g['display_name'],
            total_beds=total,
            occupied_beds=occupied,
            lat=g['lat'],
            lon=g['lon'],
        )
        created += 1
    print(f"Hospitales creados: {created}")


def create_facilities(forces):
    created = 0
    # Cuarteles (Bomberos)
    for name in FIRE_STATIONS:
        if Facility.objects.filter(name=name).exists():
            continue
        g = geocode_one(name)
        time.sleep(SLEEP_SEC)
        if not g:
            print(f"No encontrado cuartel (Facility): {name}")
            continue
        Facility.objects.create(
            name=name,
            kind='cuartel',
            force=forces['Bomberos'],
            address=g['display_name'],
            lat=g['lat'],
            lon=g['lon']
        )
        created += 1
    # Comisarías (Policía)
    for name in POLICE_STATIONS:
        if Facility.objects.filter(name=name).exists():
            continue
        g = geocode_one(name)
        time.sleep(SLEEP_SEC)
        if not g:
            print(f"No encontrada comisaría (Facility): {name}")
            continue
        Facility.objects.create(
            name=name,
            kind='comisaria',
            force=forces['Policía'],
            address=g['display_name'],
            lat=g['lat'],
            lon=g['lon']
        )
        created += 1
    # Bases de Tránsito
    for name in TRANSITO_BASES:
        if Facility.objects.filter(name=name).exists():
            continue
        g = geocode_one(name)
        time.sleep(SLEEP_SEC)
        if not g:
            print(f"No encontrada base de Tránsito (Facility): {name}")
            continue
        Facility.objects.create(
            name=name,
            kind='base_transito',
            force=forces['Tránsito'],
            address=g['display_name'],
            lat=g['lat'],
            lon=g['lon']
        )
        created += 1
    print(f"Instalaciones creadas: {created}")


def create_station_vehicles(forces):
    # Vehículos en hospitales (SAME)
    same = forces['SAME']
    amb_created = 0
    for h in Hospital.objects.all():
        count = random.randint(2, 8)
        for _ in range(count):
            Vehicle.objects.create(
                force=same, type='Ambulancia', status='disponible',
                current_lat=h.lat, current_lon=h.lon
            )
            amb_created += 1
    print(f"Ambulancias creadas: {amb_created}")

    # Bomberos por cuartel
    bomberos = forces['Bomberos']
    fire_created = 0
    for name in FIRE_STATIONS:
        g = geocode_one(name)
        time.sleep(SLEEP_SEC)
        if not g:
            print(f"No encontrado cuartel: {name}")
            continue
        count = random.randint(2, 6)
        for _ in range(count):
            Vehicle.objects.create(force=bomberos, type='Camión de Bomberos', status='disponible', current_lat=g['lat'], current_lon=g['lon'])
            fire_created += 1
    print(f"Camiones de Bomberos creados: {fire_created}")

    # Policía por comisaría
    policia = forces['Policía']
    patrol_created = 0
    for name in POLICE_STATIONS:
        g = geocode_one(name)
        time.sleep(SLEEP_SEC)
        if not g:
            print(f"No encontrada comisaría: {name}")
            continue
        count = random.randint(3, 10)
        for _ in range(count):
            Vehicle.objects.create(force=policia, type='Patrulla', status='disponible', current_lat=g['lat'], current_lon=g['lon'])
            patrol_created += 1
    print(f"Patrullas creadas: {patrol_created}")

    # Tránsito por base
    transito = forces['Tránsito']
    moto_created = 0
    for name in TRANSITO_BASES:
        g = geocode_one(name)
        time.sleep(SLEEP_SEC)
        if not g:
            print(f"No encontrada base de Tránsito: {name}")
            continue
        count = random.randint(3, 8)
        for _ in range(count):
            Vehicle.objects.create(force=transito, type='Moto de Tránsito', status='disponible', current_lat=g['lat'], current_lon=g['lon'])
            moto_created += 1
    print(f"Motos de Tránsito creadas: {moto_created}")


def create_agents(forces):
    def make_name():
        return f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"

    def jitter(lat, lon, meters=200):
        # ~1e-5 deg ~ 1.11m; 200m ~ 0.0018 deg
        if lat is None or lon is None:
            return None, None
        dx = (random.random() - 0.5) * 2
        dy = (random.random() - 0.5) * 2
        return lat + dy * 0.002, lon + dx * 0.002

    created = 0
    # Prepara anclas por fuerza
    anchors = {
        'SAME': [],
        'Bomberos': [],
        'Policía': [],
        'Tránsito': [],
    }
    def rand_in_caba():
        lat = -34.72 + random.random() * 0.20  # ~-34.72 a -34.52
        lon = -58.55 + random.random() * 0.25  # ~-58.55 a -58.30
        return lat, lon
    # Hospitales para SAME
    for h in Hospital.objects.exclude(lat__isnull=True).exclude(lon__isnull=True):
        anchors['SAME'].append((h.lat, h.lon))
    # Facilities
    for fac in Facility.objects.exclude(lat__isnull=True).exclude(lon__isnull=True):
        if fac.force and fac.force.name in anchors:
            anchors[fac.force.name].append((fac.lat, fac.lon))
    # Vehículos con coordenadas
    for v in Vehicle.objects.exclude(current_lat__isnull=True).exclude(current_lon__isnull=True):
        if v.force.name in anchors:
            anchors[v.force.name].append((v.current_lat, v.current_lon))

    # Escala agentes en relación a vehículos por fuerza
    for force_name, roles in ROLES.items():
        f = forces[force_name]
        vehicles = list(Vehicle.objects.filter(force=f))
        base_count = max(8, len(vehicles) * 2)
        for i in range(base_count):
            role = random.choice(roles)
            assigned_vehicle = random.choice(vehicles) if vehicles and random.random() < 0.6 else None
            alat, alon = (None, None)
            if anchors[force_name]:
                base_lat, base_lon = random.choice(anchors[force_name])
                alat, alon = jitter(base_lat, base_lon, meters=600)
            else:
                alat, alon = rand_in_caba()
            Agent.objects.create(
                name=make_name(),
                force=f,
                role=role,
                assigned_vehicle=assigned_vehicle,
                status=random.choice(['disponible','disponible','en_ruta','en_escena','ocupado']),
                lat=alat,
                lon=alon,
            )
            created += 1
    print(f"Agentes creados: {created}")


def main():
    forces = ensure_forces()
    reset_data()
    create_hospitals()
    create_facilities(forces)
    create_station_vehicles(forces)
    create_agents(forces)
    print('Población realista finalizada.')

if __name__ == '__main__':
    main()
