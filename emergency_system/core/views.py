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
    qs = Facility.objects.all().select_related('force').order_by('kind', 'name')
    if kind in ['comisaria', 'cuartel', 'base_transito']:
        qs = qs.filter(kind=kind)
    return render(request, 'core/facilities_list.html', {'facilities': qs, 'kind': kind})


# Dashboard

def dashboard(request):
    # Vehículos
    total_vehiculos = Vehicle.objects.count()
    ocupados_vehiculos = Vehicle.objects.filter(Q(status='en_ruta') | Q(status='ocupado')).count()
    disponibles_vehiculos = Vehicle.objects.filter(status='disponible').count()

    # Camas
    camas_totales = Hospital.objects.aggregate(total=models.Sum('total_beds'))['total'] or 0
    camas_ocupadas = Hospital.objects.aggregate(total=models.Sum('occupied_beds'))['total'] or 0
    camas_disponibles = max(0, camas_totales - camas_ocupadas)

    # Despachos activos
    despachos_activos = EmergencyDispatch.objects.exclude(status='finalizado').count()

    ctx = {
        'total_vehiculos': total_vehiculos,
        'ocupados_vehiculos': ocupados_vehiculos,
        'disponibles_vehiculos': disponibles_vehiculos,
        'camas_totales': camas_totales,
        'camas_ocupadas': camas_ocupadas,
        'camas_disponibles': camas_disponibles,
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
