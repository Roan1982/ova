from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django.http import JsonResponse
import math
import requests
import json
from django.db import models
from django.db.models import Count, Q
from .models import Emergency, Force, Vehicle, Agent, Hospital, EmergencyDispatch, Facility
from .forms import EmergencyForm
from .llm import classify_with_ollama
from .routing import calculate_emergency_routes, get_real_time_eta

# Importar sistema de onda verde
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from traffic_light_system import traffic_manager, activate_emergency_green_wave

def home(request):
    # Solo mostrar emergencias activas (no resueltas) en el mapa
    emergencies = Emergency.objects.filter(status__in=['pendiente', 'asignada'])
    facilities = Facility.objects.all()
    agents = Agent.objects.exclude(lat__isnull=True).exclude(lon__isnull=True).select_related('force')
    # Agregar hospitales para el mapa
    hospitals = Hospital.objects.all()
    ctx = {
        'emergencies': emergencies,
        'facilities': facilities,
        'agents': agents,
        'hospitals': hospitals,
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
    # Emergencias activas sin procesar por IA
    emergencias_pendientes = Emergency.objects.filter(
        status__in=['pendiente'], 
        ai_response__isnull=True
    ).order_by('-priority', '-reported_at')
    
    # Emergencias activas procesadas por IA
    emergencias_procesadas = Emergency.objects.filter(
        status='asignada',
        ai_response__isnull=False
    ).order_by('-priority', '-reported_at')
    
    # Emergencias finalizadas
    emergencias_finalizadas = Emergency.objects.filter(
        status='resuelta'
    ).order_by('-resolved_at')
    
    context = {
        'emergencias_pendientes': emergencias_pendientes,
        'emergencias_procesadas': emergencias_procesadas, 
        'emergencias_finalizadas': emergencias_finalizadas,
        'total_pendientes': emergencias_pendientes.count(),
        'total_procesadas': emergencias_procesadas.count(),
        'total_finalizadas': emergencias_finalizadas.count(),
    }
    
    return render(request, 'core/emergency_list.html', context)


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
        
        # Guardar respuesta de la IA
        respuesta_ia = ia.get('respuesta_ia', 'Clasificación completada por sistema de IA.')
        fuente_ia = ia.get('fuente', 'desconocida')
        emergency.ai_response = f"[Sistema {fuente_ia.upper()}] {respuesta_ia}"
        
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
        emergency.save(update_fields=['code', 'priority', 'onda_verde', 'ai_response'])
    else:
        # Fallback: usar clasificación local preexistente
        if not emergency.code:
            emergency.code = emergency.classify_code()
            emergency.ai_response = "Sistema de IA no disponible. Clasificación realizada por reglas básicas."
            emergency.save(update_fields=['code', 'priority', 'ai_response'])

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
    fuerzas = Force.objects.all().order_by('name')
    
    # Calcular estadísticas
    total = agentes.count()
    disponibles = agentes.filter(status='disponible').count()
    en_ruta = agentes.filter(status='en_ruta').count()
    ocupados = agentes.filter(status='ocupado').count()
    en_escena = agentes.filter(status='en_escena').count()
    
    stats = {
        'total': total,
        'disponibles': disponibles,
        'en_ruta': en_ruta,
        'ocupados': ocupados,
        'en_escena': en_escena
    }
    
    return render(request, 'core/agentes_list.html', {
        'agentes': agentes,
        'fuerzas': fuerzas,
        'stats': stats
    })


def unidades_por_fuerza(request):
    fuerzas = Force.objects.all().order_by('name')
    data = []
    for f in fuerzas:
        unidades = Vehicle.objects.filter(force=f)
        
        # Calcular estadísticas
        total = unidades.count()
        disponibles = unidades.filter(status='disponible').count()
        en_ruta = unidades.filter(status='en_ruta').count()
        ocupados = unidades.filter(status='ocupado').count()
        
        data.append({
            'force': f, 
            'unidades': unidades,
            'stats': {
                'total': total,
                'disponibles': disponibles,
                'en_ruta': en_ruta,
                'ocupados': ocupados,
                'porcentaje_disponible': round((disponibles / total * 100) if total > 0 else 0, 1)
            }
        })
    return render(request, 'core/unidades_por_fuerza.html', {'data': data})


def hospitales_list(request):
    hospitales = Hospital.objects.all().order_by('name')
    
    # Calcular estadísticas generales
    total_hospitales = hospitales.count()
    camas_totales = sum(h.total_beds for h in hospitales)
    camas_ocupadas = sum(h.occupied_beds for h in hospitales)
    camas_disponibles = camas_totales - camas_ocupadas
    porcentaje_ocupacion = round((camas_ocupadas / camas_totales * 100) if camas_totales > 0 else 0, 1)
    
    # Estadísticas por nivel de ocupación
    hospitales_normal = 0  # <60%
    hospitales_medio = 0   # 60-80%
    hospitales_alto = 0    # >80%
    
    # Agregar datos calculados a cada hospital
    hospitales_with_stats = []
    for hospital in hospitales:
        occupancy_percentage = round((hospital.occupied_beds / hospital.total_beds * 100) if hospital.total_beds > 0 else 0, 1)
        
        # Clasificar por nivel de ocupación
        if occupancy_percentage < 60:
            hospitales_normal += 1
        elif occupancy_percentage <= 80:
            hospitales_medio += 1
        else:
            hospitales_alto += 1
        
        # Crear un objeto con los datos calculados (sin modificar el modelo)
        hospital_data = {
            'hospital': hospital,
            'occupancy_percentage': occupancy_percentage
        }
        hospitales_with_stats.append(hospital_data)
    
    stats = {
        'total_hospitales': total_hospitales,
        'camas_totales': camas_totales,
        'camas_ocupadas': camas_ocupadas,
        'camas_disponibles': camas_disponibles,
        'porcentaje_ocupacion': porcentaje_ocupacion,
        'hospitales_normal': hospitales_normal,
        'hospitales_medio': hospitales_medio,
        'hospitales_alto': hospitales_alto
    }
    
    return render(request, 'core/hospitales_list.html', {
        'hospitales_data': hospitales_with_stats,
        'stats': stats
    })


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

    # Calcular estadísticas antes del filtro
    total_instalaciones = len(installations)
    comisarias = len([i for i in installations if i['kind'] == 'comisaria'])
    cuarteles = len([i for i in installations if i['kind'] == 'cuartel'])
    bases_transito = len([i for i in installations if i['kind'] == 'base_transito'])
    hospitales = len([i for i in installations if i['kind'] == 'hospital'])
    
    con_coordenadas = len([i for i in installations if i['lat'] and i['lon']])
    sin_coordenadas = total_instalaciones - con_coordenadas
    porcentaje_coordenadas = round((con_coordenadas / total_instalaciones * 100) if total_instalaciones > 0 else 0, 1)

    # Aplicar filtro si existe
    if kind:
        allowed = {'comisaria', 'cuartel', 'base_transito', 'hospital'}
        if kind in allowed:
            installations = [i for i in installations if i['kind'] == kind]

    # Ordenar por tipo y nombre
    installations.sort(key=lambda x: (x['kind_display'], x['name']))

    stats = {
        'total_instalaciones': total_instalaciones,
        'comisarias': comisarias,
        'cuarteles': cuarteles,
        'bases_transito': bases_transito,
        'hospitales': hospitales,
        'con_coordenadas': con_coordenadas,
        'sin_coordenadas': sin_coordenadas,
        'porcentaje_coordenadas': porcentaje_coordenadas
    }

    return render(request, 'core/facilities_list.html', {
        'installations': installations,
        'kind': kind,
        'stats': stats
    })


def ai_status_view(request):
    """Vista para mostrar el estado del sistema de IA"""
    from django.conf import settings
    from .llm import get_ai_status, classify_with_ollama
    
    status = get_ai_status()
    
    # Test de clasificación
    test_description = "Accidente de tránsito con heridos en Av. Corrientes"
    test_result = None
    test_error = None
    
    try:
        test_result = classify_with_ollama(test_description)
    except Exception as e:
        test_error = str(e)
    
    context = {
        'status': status,
        'test_description': test_description,
        'test_result': test_result,
        'test_error': test_error,
        'settings_config': {
            'OLLAMA_BASE_URL': getattr(settings, 'OLLAMA_BASE_URL', 'No configurado'),
            'OLLAMA_MODEL': getattr(settings, 'OLLAMA_MODEL', 'No configurado'),
            'OLLAMA_TIMEOUT': getattr(settings, 'OLLAMA_TIMEOUT', 'No configurado'),
            'OLLAMA_MAX_RETRIES': getattr(settings, 'OLLAMA_MAX_RETRIES', 'No configurado'),
        }
    }
    
    return render(request, 'core/ai_status.html', context)


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

def calculate_routes_api(request, emergency_id):
    """
    API endpoint para calcular rutas optimizadas para una emergencia
    """
    emergency = get_object_or_404(Emergency, pk=emergency_id)
    
    if not (emergency.location_lat and emergency.location_lon):
        return JsonResponse({
            'error': 'La emergencia no tiene coordenadas válidas',
            'routes': []
        }, status=400)
    
    try:
        # Calcular rutas optimizadas
        route_assignments = calculate_emergency_routes(emergency)
        
        # Formatear respuesta para el frontend
        routes_data = []
        for assignment in route_assignments[:5]:  # Top 5 recursos más cercanos
            resource = assignment['resource']
            route_info = assignment['route_info']
            
            routes_data.append({
                'resource_id': resource['id'],
                'resource_name': resource['name'],
                'resource_type': resource['resource_type'],
                'distance_km': round(assignment['distance_km'], 2),
                'eta_minutes': round(assignment['estimated_arrival'], 1),
                'route_geometry': route_info['geometry'],
                'provider': route_info['provider'],
                'priority_score': assignment['priority_score']
            })
        
        return JsonResponse({
            'emergency_id': emergency_id,
            'emergency_coords': [emergency.location_lat, emergency.location_lon],
            'routes': routes_data,
            'total_resources': len(route_assignments)
        })
        
    except Exception as e:
        return JsonResponse({
            'error': f'Error calculando rutas: {str(e)}',
            'routes': []
        }, status=500)

def assign_optimal_resources(request, emergency_id):
    """
    Vista para asignar automáticamente los recursos más óptimos a una emergencia
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    
    emergency = get_object_or_404(Emergency, pk=emergency_id)
    
    try:
        # Calcular rutas optimizadas
        route_assignments = calculate_emergency_routes(emergency)
        
        if not route_assignments:
            return JsonResponse({
                'error': 'No hay recursos disponibles para asignar',
                'assigned': []
            })
        
        assigned_resources = []
        
        # Asignar los mejores recursos basado en tipo de emergencia
        emergency_type = emergency.code or 'verde'
        max_assignments = 3 if emergency_type == 'rojo' else 2 if emergency_type == 'amarillo' else 1
        
        for i, assignment in enumerate(route_assignments[:max_assignments]):
            resource = assignment['resource']
            resource_obj = resource['resource_obj']
            
            # Actualizar estado del recurso
            if resource['resource_type'] == 'vehicle':
                resource_obj.status = 'en_ruta'
                resource_obj.target_lat = emergency.location_lat
                resource_obj.target_lon = emergency.location_lon
                resource_obj.save()
                
                # Asignar vehículo a emergencia si es el primero
                if i == 0 and not emergency.assigned_vehicle:
                    emergency.assigned_vehicle = resource_obj
                    emergency.assigned_force = resource_obj.force
                    
            elif resource['resource_type'] == 'agent':
                resource_obj.status = 'en_ruta'
                resource_obj.target_lat = emergency.location_lat
                resource_obj.target_lon = emergency.location_lon
                resource_obj.save()
            
            assigned_resources.append({
                'resource_id': resource['id'],
                'resource_name': resource['name'],
                'eta_minutes': round(assignment['estimated_arrival'], 1),
                'distance_km': round(assignment['distance_km'], 2)
            })
        
        # Actualizar estado de emergencia
        if emergency.status == 'pendiente':
            emergency.status = 'asignada'
        
        emergency.save()
        
        return JsonResponse({
            'success': True,
            'emergency_id': emergency_id,
            'assigned': assigned_resources,
            'message': f'Se asignaron {len(assigned_resources)} recursos a la emergencia'
        })
        
    except Exception as e:
        return JsonResponse({
            'error': f'Error asignando recursos: {str(e)}',
            'assigned': []
        }, status=500)

def real_time_tracking(request):
    """
    API para seguimiento en tiempo real de recursos en ruta
    """
    # Obtener todos los recursos en ruta
    vehicles_in_route = Vehicle.objects.filter(status='en_ruta').select_related('force')
    agents_in_route = Agent.objects.filter(status='en_ruta').select_related('force')
    
    tracking_data = []
    
    # Procesar vehículos en ruta
    for vehicle in vehicles_in_route:
        if vehicle.current_lat and vehicle.current_lon and vehicle.target_lat and vehicle.target_lon:
            # Calcular ETA actual
            eta_data = get_real_time_eta(
                (vehicle.current_lat, vehicle.current_lon),
                (vehicle.target_lat, vehicle.target_lon)
            )
            
            tracking_data.append({
                'id': f'vehicle_{vehicle.id}',
                'type': 'vehicle',
                'name': f"{vehicle.type} - {vehicle.force.name}",
                'current_position': [vehicle.current_lat, vehicle.current_lon],
                'target_position': [vehicle.target_lat, vehicle.target_lon],
                'eta_minutes': round(eta_data['eta_minutes'], 1),
                'distance_remaining_km': round(eta_data['distance_km'], 2),
                'route_geometry': eta_data['route_geometry'],
                'status': vehicle.status
            })
    
    # Procesar agentes en ruta
    for agent in agents_in_route:
        if agent.lat and agent.lon and agent.target_lat and agent.target_lon:
            # Calcular ETA actual
            eta_data = get_real_time_eta(
                (agent.lat, agent.lon),
                (agent.target_lat, agent.target_lon)
            )
            
            tracking_data.append({
                'id': f'agent_{agent.id}',
                'type': 'agent',
                'name': f"{agent.name} - {agent.force.name}",
                'current_position': [agent.lat, agent.lon],
                'target_position': [agent.target_lat, agent.target_lon],
                'eta_minutes': round(eta_data['eta_minutes'], 1),
                'distance_remaining_km': round(eta_data['distance_km'], 2),
                'route_geometry': eta_data['route_geometry'],
                'status': agent.status
            })
    
    return JsonResponse({
        'tracking_data': tracking_data,
        'total_resources_in_route': len(tracking_data),
        'timestamp': timezone.now().isoformat()
    })

def activate_green_wave_api(request, emergency_id):
    """
    API para activar onda verde para una emergencia código rojo
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    
    emergency = get_object_or_404(Emergency, pk=emergency_id)
    
    try:
        result = activate_emergency_green_wave(emergency)
        
        if result['success']:
            # Actualizar la emergencia para marcar onda verde como activa
            emergency.onda_verde = True
            emergency.save(update_fields=['onda_verde'])
            
            return JsonResponse({
                'success': True,
                'message': result['message'],
                'total_intersections': result.get('total_intersections', 0),
                'results': result['results'],
                'emergency_id': emergency_id
            })
        else:
            return JsonResponse({
                'success': False,
                'message': result['message'],
                'emergency_id': emergency_id
            })
            
    except Exception as e:
        return JsonResponse({
            'error': f'Error activando onda verde: {str(e)}',
            'success': False
        }, status=500)

def traffic_status_api(request):
    """
    API para obtener estado actual de semáforos y ondas verdes
    """
    try:
        active_waves = traffic_manager.get_active_green_waves()
        
        # Preparar datos de respuesta
        waves_data = []
        total_intersections = 0
        
        for wave_id, wave_data in active_waves.items():
            intersections_info = []
            for timing in wave_data['timing']:
                intersections_info.append({
                    'name': timing['intersection']['name'],
                    'lat': timing['intersection']['lat'],
                    'lon': timing['intersection']['lon'],
                    'arrival_time': timing['arrival_time'].isoformat(),
                    'green_start': timing['green_start'].isoformat(),
                    'green_end': timing['green_end'].isoformat(),
                    'priority': timing['priority']
                })
            
            total_intersections += len(intersections_info)
            
            waves_data.append({
                'wave_id': wave_id,
                'created_at': wave_data['created_at'].isoformat(),
                'vehicle_position': wave_data['vehicle_position'],
                'target_position': wave_data['target_position'],
                'intersections': intersections_info,
                'status': wave_data['status']
            })
        
        return JsonResponse({
            'success': True,
            'active_waves': len(waves_data),
            'total_intersections': total_intersections,
            'waves_data': waves_data,
            'timestamp': timezone.now().isoformat()
        })
        
    except Exception as e:
        return JsonResponse({
            'error': f'Error obteniendo estado de tráfico: {str(e)}',
            'success': False
        }, status=500)

def redistribute_resources_api(request):
    """
    API para redistribuir recursos evitando el río
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    
    try:
        # Ejecutar script de redistribución
        import subprocess
        import sys
        
        script_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
            'redistribute_resources.py'
        )
        
        result = subprocess.run([
            sys.executable, script_path
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            return JsonResponse({
                'success': True,
                'message': 'Recursos redistribuidos exitosamente',
                'output': result.stdout
            })
        else:
            return JsonResponse({
                'success': False,
                'message': 'Error en redistribución',
                'error': result.stderr
            }, status=500)
            
    except Exception as e:
        return JsonResponse({
            'error': f'Error redistribuyendo recursos: {str(e)}',
            'success': False
        }, status=500)
