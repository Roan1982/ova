from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
import math
import requests
from django.db import models
from django.db.models import Count, Q
from .models import Emergency, Force, Vehicle, Agent, Hospital, EmergencyDispatch, Facility
from .forms import EmergencyForm
from .llm import classify_with_ollama

def home(request):
    emergencies = Emergency.objects.all()
    facilities = Facility.objects.all()
    agents = Agent.objects.exclude(lat__isnull=True).exclude(lon__isnull=True).select_related('force')
    ctx = {
        'emergencies': emergencies,
        'facilities': facilities,
        'agents': agents,
    }
    return render(request, 'core/home.html', ctx)

def create_emergency(request):
    if request.method == 'POST':
        form = EmergencyForm(request.POST)
        if form.is_valid():
            emergency = form.save(commit=False)
            # Obtener lat/lon de los campos ocultos si están presentes
            lat = request.POST.get('location_lat')
            lon = request.POST.get('location_lon')
            if lat and lon:
                emergency.location_lat = float(lat)
                emergency.location_lon = float(lon)
            elif emergency.address:
                # Geocodificar si no hay lat/lon
                url = f"https://nominatim.openstreetmap.org/search?format=json&q={emergency.address}, CABA, Argentina"
                headers = {'User-Agent': 'emergency_app/1.0'}
                response = requests.get(url, headers=headers)
                if response.status_code == 200 and response.json():
                    data = response.json()[0]
                    emergency.location_lat = float(data['lat'])
                    emergency.location_lon = float(data['lon'])
                else:
                    form.add_error('address', 'No se pudo encontrar la dirección. Por favor, intente nuevamente.')
                    return render(request, 'core/create_emergency.html', {'form': form})
            emergency.save()  # Activa clasificación y asignación
            return redirect('home')
    else:
        form = EmergencyForm()
    return render(request, 'core/create_emergency.html', {'form': form})

def emergency_list(request):
    emergencies = Emergency.objects.all().order_by('-reported_at')
    return render(request, 'core/emergency_list.html', {'emergencies': emergencies})


def _haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c


def process_emergency(request, pk):
    emergency = get_object_or_404(Emergency, pk=pk)

    # 1) Clasificación IA (Ollama) y actualización de código/prioridad/onda verde
    ia = classify_with_ollama(emergency.description)
    if ia:
        emergency.code = ia['codigo']
        emergency.priority = 10 if ia['codigo'] == 'rojo' else 5 if ia['codigo'] == 'amarillo' else 1
        emergency.onda_verde = (ia['codigo'] == 'rojo')
        # Sugerir fuerza según IA
        tipo = ia.get('tipo')
        if tipo == 'bomberos':
            # No forzamos vehicle aquí; lo hará process_ia
            pass
        elif tipo == 'medico':
            pass
        elif tipo == 'policial':
            pass
        # guardamos cambios mínimos
        emergency.save(update_fields=['code', 'priority', 'onda_verde'])
    else:
        # Fallback: usar clasificación local preexistente
        if not emergency.code:
            emergency.code = emergency.classify_code()
            emergency.save(update_fields=['code', 'priority'])

    # 2) Asignación de intervención/vehículo
    assigned_by_ia = False
    if ia and ia.get('tipo'):
        tipo_map = {'bomberos': 'Bomberos', 'medico': 'SAME', 'policial': 'Policía'}
        fuerza_nombre = tipo_map.get(ia['tipo'])
        if fuerza_nombre:
            fuerza = Force.objects.filter(name=fuerza_nombre).first()
            if fuerza:
                emergency.assigned_force = fuerza
                veh = Vehicle.objects.filter(force=fuerza, status='disponible').first()
                if veh:
                    emergency.assigned_vehicle = veh
                    veh.status = 'en_ruta'
                    veh.save()
                emergency.status = 'asignada'
                emergency.save(update_fields=['assigned_force','assigned_vehicle','status'])
                assigned_by_ia = True
    if not assigned_by_ia:
        # Reglas del sistema
        emergency.process_ia()

    # 3) Calcular distancia/ETA
    dist_txt = "N/D"
    eta_txt = "N/D"
    if emergency.location_lat and emergency.location_lon and emergency.assigned_vehicle and \
       emergency.assigned_vehicle.current_lat is not None and emergency.assigned_vehicle.current_lon is not None:
        dist_km = _haversine_km(
            emergency.assigned_vehicle.current_lat,
            emergency.assigned_vehicle.current_lon,
            emergency.location_lat,
            emergency.location_lon
        )
        base_speed = 30.0
        traffic_factor = 1.1
        if emergency.code == 'rojo' and emergency.onda_verde:
            base_speed = 50.0
            traffic_factor = 0.8
        eta_hours = dist_km / base_speed * traffic_factor
        eta_min = max(1, int(eta_hours * 60))
        dist_txt = f"{dist_km:.2f} km"
        eta_txt = f"{eta_min} min"

    # 4) Construir informe completo y sobrescribir notas
    razones = (ia.get('razones') if ia else []) or []
    score = ia.get('score') if ia else None
    tipo_info = ia.get('tipo') if ia else None
    informe = []
    informe.append(f"[ {timezone.localtime(timezone.now()).strftime('%d/%m/%Y %H:%M:%S')} ] Informe de Proceso - Completo")
    informe.append("")
    informe.append("Clasificación IA (Ollama)")
    if ia:
        informe.append(f"- Tipo: {tipo_info}")
        informe.append(f"- Código: {emergency.code}")
        if score is not None:
            informe.append(f"- Puntaje: {score}")
        if razones:
            informe.append("- Razones:")
            for r in razones:
                informe.append(f"  - {r}")
    else:
        informe.append("- IA no disponible (se mantuvo la clasificación existente)")
        informe.append(f"- Código: {emergency.code}")

    informe.append("")
    informe.append("Intervención")
    informe.append(f"- Fuerza: {emergency.assigned_force.name if emergency.assigned_force else 'N/D'}")
    informe.append(f"- Vehículo: {emergency.assigned_vehicle.type if emergency.assigned_vehicle else 'N/D'}")

    informe.append("")
    informe.append("Movilidad")
    informe.append(f"- Distancia estimada: {dist_txt}")
    informe.append(f"- ETA: {eta_txt}")
    informe.append(f"- Onda Verde: {'ACTIVADA' if emergency.onda_verde else 'NO'}")

    informe.append("")
    informe.append("Estado")
    informe.append(f"- Estado actual: {emergency.status}")
    informe.append(f"- Reportado: {timezone.localtime(emergency.reported_at).strftime('%d/%m/%Y %H:%M')}")
    if emergency.resolved_at:
        informe.append(f"- Resuelto: {timezone.localtime(emergency.resolved_at).strftime('%d/%m/%Y %H:%M')}")

    emergency.resolution_notes = "\n".join(informe)
    emergency.save(update_fields=['resolution_notes'])

    messages.success(request, f"Emergencia #{emergency.pk} procesada (informe completo generado).")
    return redirect('emergency_detail', pk=emergency.pk)


def emergency_detail(request, pk):
    emergency = get_object_or_404(Emergency, pk=pk)
    return render(request, 'core/emergency_detail.html', { 'emergency': emergency })

# Listados

def agentes_list(request):
    agentes = Agent.objects.select_related('force', 'assigned_vehicle').all().order_by('force__name','name')
    return render(request, 'core/agentes_list.html', {'agentes': agentes})


def unidades_por_fuerza(request):
    fuerzas = Force.objects.all().order_by('name')
    data = []
    for f in fuerzas:
        unidades = Vehicle.objects.filter(force=f)
        data.append({'force': f, 'unidades': unidades})
    return render(request, 'core/unidades_por_fuerza.html', {'data': data})


def hospitales_list(request):
    hospitales = Hospital.objects.all().order_by('name')
    return render(request, 'core/hospitales_list.html', {'hospitales': hospitales})


def facilities_list(request):
    kind = request.GET.get('tipo')
    facilities_qs = Facility.objects.all().select_related('force').order_by('kind', 'name')
    hospitals_qs = Hospital.objects.all().order_by('name')

    installations = []
    # Facilities -> dicts
    for f in facilities_qs:
        installations.append({
            'name': f.name,
            'kind': f.kind,
            'kind_display': f.get_kind_display(),
            'force_name': f.force.name if f.force else '',
            'address': f.address,
            'lat': f.lat,
            'lon': f.lon,
        })
    # Hospitals as installations
    for h in hospitals_qs:
        installations.append({
            'name': h.name,
            'kind': 'hospital',
            'kind_display': 'Hospital',
            'force_name': 'SAME',
            'address': h.address,
            'lat': h.lat,
            'lon': h.lon,
        })

    if kind:
        allowed = {'comisaria', 'cuartel', 'base_transito', 'hospital'}
        if kind in allowed:
            installations = [i for i in installations if i['kind'] == kind]

    # Ordenar por tipo y nombre
    installations.sort(key=lambda x: (x['kind_display'], x['name']))

    return render(request, 'core/facilities_list.html', {
        'installations': installations,
        'kind': kind,
    })


# Dashboard

def dashboard(request):
    # Resumen general de emergencias
    emergencias_total = Emergency.objects.count()
    emergencias_activas = Emergency.objects.exclude(status='resuelta').count()
    emergencias_pendientes = Emergency.objects.filter(status='reportada').count()
    emergencias_asignadas = Emergency.objects.filter(status='asignada').count()
    emergencias_en_curso = Emergency.objects.filter(status='en_curso').count()
    
    # Emergencias por código de prioridad
    emergencias_rojo = Emergency.objects.filter(code='rojo').exclude(status='resuelta').count()
    emergencias_amarillo = Emergency.objects.filter(code='amarillo').exclude(status='resuelta').count()
    emergencias_verde = Emergency.objects.filter(code='verde').exclude(status='resuelta').count()

    # Datos por fuerza
    fuerzas_data = []
    fuerzas = Force.objects.all().order_by('name')
    
    for fuerza in fuerzas:
        # Vehículos por fuerza
        vehiculos = Vehicle.objects.filter(force=fuerza)
        vehiculos_total = vehiculos.count()
        vehiculos_disponibles = vehiculos.filter(status='disponible').count()
        vehiculos_en_ruta = vehiculos.filter(status='en_ruta').count()
        vehiculos_ocupados = vehiculos.filter(status='ocupado').count()
        
        # Agentes por fuerza
        agentes = Agent.objects.filter(force=fuerza)
        agentes_total = agentes.count()
        agentes_disponibles = agentes.filter(status='disponible').count()
        agentes_en_ruta = agentes.filter(status='en_ruta').count()
        agentes_ocupados = agentes.filter(status='ocupado').count()
        agentes_en_escena = agentes.filter(status='en_escena').count()
        
        # Emergencias asignadas a esta fuerza
        emergencias_asignadas_fuerza = Emergency.objects.filter(assigned_force=fuerza).exclude(status='resuelta').count()
        
        # Instalaciones de esta fuerza
        instalaciones = Facility.objects.filter(force=fuerza).count()
        
        fuerzas_data.append({
            'fuerza': fuerza,
            'vehiculos': {
                'total': vehiculos_total,
                'disponibles': vehiculos_disponibles,
                'en_ruta': vehiculos_en_ruta,
                'ocupados': vehiculos_ocupados,
                'porcentaje_disponible': round((vehiculos_disponibles / vehiculos_total * 100) if vehiculos_total > 0 else 0, 1)
            },
            'agentes': {
                'total': agentes_total,
                'disponibles': agentes_disponibles,
                'en_ruta': agentes_en_ruta,
                'ocupados': agentes_ocupados,
                'en_escena': agentes_en_escena,
                'porcentaje_disponible': round((agentes_disponibles / agentes_total * 100) if agentes_total > 0 else 0, 1)
            },
            'emergencias_asignadas': emergencias_asignadas_fuerza,
            'instalaciones': instalaciones
        })

    # Totales generales
    total_vehiculos = Vehicle.objects.count()
    total_vehiculos_disponibles = Vehicle.objects.filter(status='disponible').count()
    total_vehiculos_ocupados = Vehicle.objects.filter(Q(status='en_ruta') | Q(status='ocupado')).count()
    
    total_agentes = Agent.objects.count()
    total_agentes_disponibles = Agent.objects.filter(status='disponible').count()
    total_agentes_ocupados = Agent.objects.exclude(status='disponible').count()

    # Camas hospitalarias
    camas_totales = Hospital.objects.aggregate(total=models.Sum('total_beds'))['total'] or 0
    camas_ocupadas = Hospital.objects.aggregate(total=models.Sum('occupied_beds'))['total'] or 0
    camas_disponibles = max(0, camas_totales - camas_ocupadas)
    total_hospitales = Hospital.objects.count()

    # Despachos activos
    despachos_activos = EmergencyDispatch.objects.exclude(status='finalizado').count()

    ctx = {
        # Emergencias
        'emergencias_total': emergencias_total,
        'emergencias_activas': emergencias_activas,
        'emergencias_pendientes': emergencias_pendientes,
        'emergencias_asignadas': emergencias_asignadas,
        'emergencias_en_curso': emergencias_en_curso,
        'emergencias_rojo': emergencias_rojo,
        'emergencias_amarillo': emergencias_amarillo,
        'emergencias_verde': emergencias_verde,
        
        # Datos por fuerza
        'fuerzas_data': fuerzas_data,
        
        # Totales generales
        'total_vehiculos': total_vehiculos,
        'total_vehiculos_disponibles': total_vehiculos_disponibles,
        'total_vehiculos_ocupados': total_vehiculos_ocupados,
        'porcentaje_vehiculos_disponibles': round((total_vehiculos_disponibles / total_vehiculos * 100) if total_vehiculos > 0 else 0, 1),
        
        'total_agentes': total_agentes,
        'total_agentes_disponibles': total_agentes_disponibles,
        'total_agentes_ocupados': total_agentes_ocupados,
        'porcentaje_agentes_disponibles': round((total_agentes_disponibles / total_agentes * 100) if total_agentes > 0 else 0, 1),
        
        # Hospitales
        'camas_totales': camas_totales,
        'camas_ocupadas': camas_ocupadas,
        'camas_disponibles': camas_disponibles,
        'total_hospitales': total_hospitales,
        'porcentaje_camas_disponibles': round((camas_disponibles / camas_totales * 100) if camas_totales > 0 else 0, 1),
        
        # Otros
        'despachos_activos': despachos_activos,
    }
    return render(request, 'core/dashboard.html', ctx)


def resolve_emergency(request, pk):
    emergency = get_object_or_404(Emergency, pk=pk)
    if request.method == 'POST':
        notes = request.POST.get('notas', '')
        emergency.resolve(notes)
        messages.success(request, f"Emergencia #{emergency.pk} resuelta.")
        return redirect('emergency_detail', pk=emergency.pk)
    # Si es GET, mostrar formulario simple en el detalle (redirigir)
    return redirect('emergency_detail', pk=emergency.pk)
