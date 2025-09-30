from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django.http import JsonResponse, Http404
from django.core.serializers.json import DjangoJSONEncoder
import math
import requests
import json
import random
from datetime import timedelta
from django.db import models
from django.db.models import Count, Q
from django.conf import settings
from .models import Emergency, Force, Vehicle, Agent, Hospital, EmergencyDispatch, Facility, CalculatedRoute
from .forms import EmergencyForm
from .llm import classify_with_ai
from .routing import calculate_emergency_routes, get_real_time_eta, get_route_optimizer
from .news import get_latest_news, get_weather_status, get_incident_items

# Importar sistema de onda verde
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from traffic_light_system import traffic_manager, activate_emergency_green_wave

def home(request):
    # Solo mostrar emergencias activas (no resueltas) en el mapa - LIMITAR CANTIDAD
    emergencies = Emergency.objects.filter(status__in=['pendiente', 'asignada'])[:20]  # Máximo 20
    facilities = Facility.objects.all()[:50]  # Limitar facilities
    agents = Agent.objects.exclude(lat__isnull=True).exclude(lon__isnull=True).select_related('force')[:100]  # Limitar agentes
    # Agregar hospitales para el mapa
    hospitals = Hospital.objects.all()
    
    # NO CALCULAR RUTAS AUTOMÁTICAMENTE - Solo preparar estructura vacía
    # Las rutas se calcularán bajo demanda cuando el usuario haga clic
    emergency_routes = {}
    
    # Obtener noticias y clima (caché interno maneja eficiencia)
    try:
        news_items = get_latest_news()
    except Exception as e:
        news_items = []
        print(f"Error obteniendo noticias: {e}")
    try:
        incident_items = get_incident_items(limit=10)
    except Exception as e:
        incident_items = []
        print(f"Error obteniendo incidentes: {e}")
    try:
        weather = get_weather_status()
    except Exception as e:
        weather = None
        print(f"Error obteniendo clima: {e}")

    ctx = {
        'emergencies': emergencies,
        'facilities': facilities,
        'agents': agents,
        'hospitals': hospitals,
        'emergency_routes': json.dumps(emergency_routes, cls=DjangoJSONEncoder),  # Array vacío inicialmente
        'news_items': news_items,
        'weather': weather,
        'incident_items': incident_items,
    }
    return render(request, 'core/home.html', ctx)

def news_api(request):
    """JSON API para noticias (refrescables por frontend)."""
    try:
        items = get_latest_news()
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e), 'items': []})
    return JsonResponse({'success': True, 'items': items, 'total': len(items)})

def weather_api(request):
    """JSON API para clima actual y mini pronóstico."""
    try:
        data = get_weather_status()
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e), 'weather': None})
    return JsonResponse({'success': True, 'weather': data})

def incidents_api(request):
    """JSON API para incidentes / tránsito / emergencias destacadas."""
    try:
        items = get_incident_items(limit=15)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e), 'items': []})
    return JsonResponse({'success': True, 'items': items, 'total': len(items)})

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
            # Autocálculo inicial de rutas si hay ubicación válida
            if emergency.location_lat is not None and emergency.location_lon is not None:
                try:
                    route_assignments = calculate_emergency_routes(emergency)
                    if route_assignments:
                        # Persistir rutas principales (reutilizando lógica existente simplificada)
                        CalculatedRoute.objects.filter(emergency=emergency, status='activa').delete()
                        for stored in route_assignments[:5]:
                            resource_info = stored.get('resource', {})
                            route_info = stored.get('route_info') or {}
                            CalculatedRoute.objects.create(
                                emergency=emergency,
                                resource_id=resource_info.get('id', 'recurso'),
                                resource_type=resource_info.get('name', resource_info.get('resource_type', 'Recurso')),
                                distance_km=stored.get('distance_km') or 0,
                                estimated_time_minutes=stored.get('estimated_arrival') or 0,
                                priority_score=stored.get('priority_score') or 999,
                                route_geometry=route_info.get('geometry', {}),
                                status='activa'
                            )
                except Exception as e:
                    print(f"Error autocálculo rutas post-creación: {e}")
            return redirect('emergency_detail', pk=emergency.pk)
    else:
        form = EmergencyForm()
    return render(request, 'core/create_emergency.html', {'form': form})

def emergency_list(request):
    # Emergencias activas (pendientes y asignadas)
    emergencias_pendientes = Emergency.objects.filter(
        status='pendiente'
    ).order_by('-priority', '-reported_at')
    
    # Emergencias activas procesadas por IA (asignadas)
    emergencias_procesadas = Emergency.objects.filter(
        status='asignada'
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


def _determine_traffic_factor(route_obj, emergency):
    """Simula niveles de tráfico consistentes para una ruta determinada."""
    seed = f"{route_obj.resource_id}-{route_obj.emergency_id}"
    rng = random.Random(seed)

    base = rng.uniform(0.85, 1.35)

    now = timezone.now()
    if 7 <= now.hour <= 10 or 17 <= now.hour <= 20:
        base *= rng.uniform(1.05, 1.25)

    if emergency and emergency.code == 'rojo':
        if emergency.onda_verde:
            base *= 0.6
        else:
            base *= 0.85

    return max(0.45, min(base, 1.75))


def _traffic_level_metadata(factor):
    if factor <= 0.7:
        return {'level': 'libre', 'label': 'Tráfico libre', 'color': '#22c55e'}
    if factor <= 1.0:
        return {'level': 'moderado', 'label': 'Tráfico moderado', 'color': '#f59e0b'}
    return {'level': 'congestionado', 'label': 'Tráfico congestionado', 'color': '#dc2626'}


def _interpolate_route_point(route_geometry, progress):
    if not route_geometry:
        return None

    coordinates = route_geometry.get('coordinates') or []
    if not coordinates:
        return None

    latlon_points = [(coord[1], coord[0]) for coord in coordinates]
    if len(latlon_points) == 1:
        return latlon_points[0]

    distances = []
    total_distance = 0.0

    for idx in range(len(latlon_points) - 1):
        start = latlon_points[idx]
        end = latlon_points[idx + 1]
        segment = _haversine_km(start[0], start[1], end[0], end[1])
        distances.append((segment, start, end))
        total_distance += segment

    if total_distance == 0:
        return latlon_points[-1]

    target_distance = total_distance * max(0.0, min(1.0, progress))
    covered = 0.0

    for segment_length, start, end in distances:
        if covered + segment_length >= target_distance:
            remaining = target_distance - covered
            ratio = 0 if segment_length == 0 else remaining / segment_length
            lat = start[0] + (end[0] - start[0]) * ratio
            lon = start[1] + (end[1] - start[1]) * ratio
            return lat, lon
        covered += segment_length

    return latlon_points[-1]


def _build_vehicle_tracking(dispatch, route_obj):
    vehicle = dispatch.vehicle
    emergency = dispatch.emergency
    if not (vehicle and emergency and route_obj):
        return None

    total_seconds = max((route_obj.estimated_time_minutes or 1) * 60, 60)
    traffic_factor = _determine_traffic_factor(route_obj, emergency)
    adjusted_total = total_seconds * traffic_factor
    elapsed = max(0.0, (timezone.now() - route_obj.calculated_at).total_seconds())
    progress = min(1.0, elapsed / adjusted_total)

    point = _interpolate_route_point(route_obj.route_geometry, progress)
    if point is None:
        point = (
            vehicle.current_lat or emergency.location_lat,
            vehicle.current_lon or emergency.location_lon
        )

    remaining_distance_km = max((route_obj.distance_km or 0) * (1 - progress), 0)
    base_speed = (route_obj.distance_km or 0) / max(route_obj.estimated_time_minutes / 60 or 0.1, 0.1)
    speed_kmh = base_speed / max(traffic_factor, 0.1)
    eta_remaining = max(0.0, adjusted_total - elapsed) / 60

    traffic_meta = _traffic_level_metadata(traffic_factor)

    return {
        'id': f'vehicle_{vehicle.id}',
        'type': 'vehicle',
        'name': f"{vehicle.type} - {vehicle.force.name if vehicle.force else ''}",
        'current_position': [round(point[0], 6), round(point[1], 6)],
        'target_position': [emergency.location_lat, emergency.location_lon],
        'eta_minutes': round(eta_remaining, 1),
        'distance_remaining_km': round(remaining_distance_km, 2),
        'route_geometry': route_obj.route_geometry,
        'status': 'en_ruta' if progress < 1 else 'en_escena',
        'progress': round(progress, 3),
        'speed_kmh': round(speed_kmh, 1),
        'traffic_level': traffic_meta['level'],
        'traffic_label': traffic_meta['label'],
        'traffic_color': traffic_meta['color'],
        'is_code_red': emergency.code == 'rojo',
        'emergency_id': emergency.id,
        'onda_verde': emergency.onda_verde,
    }


def _persist_routes_for_emergency(emergency, assignments, include_dispatches=True, max_routes=12):
    """Guarda rutas calculadas y asegura cobertura para todos los despachos."""
    if not (emergency.location_lat and emergency.location_lon):
        return {}

    assignment_lookup = {}
    persisted_ids = set()

    CalculatedRoute.objects.filter(emergency=emergency, status='activa').delete()

    for assignment in assignments[:max_routes]:
        resource = assignment.get('resource', {}) or {}
        resource_id = resource.get('id')
        if not resource_id or resource_id in persisted_ids:
            continue

        route_info = assignment.get('route_info') or {}
        CalculatedRoute.objects.create(
            emergency=emergency,
            resource_id=resource_id,
            resource_type=resource.get('name', resource.get('resource_type', 'Recurso')),
            distance_km=assignment.get('distance_km', 0) or 0,
            estimated_time_minutes=assignment.get('estimated_arrival', 0) or 0,
            priority_score=assignment.get('priority_score', 999),
            route_geometry=route_info.get('geometry', {}),
            status='activa'
        )

        assignment_lookup[resource_id] = assignment
        persisted_ids.add(resource_id)

    if include_dispatches:
        optimizer = get_route_optimizer()
        emergency_coords = (emergency.location_lat, emergency.location_lon)
        dispatches = EmergencyDispatch.objects.filter(emergency=emergency).select_related('vehicle', 'force')

        for dispatch in dispatches:
            vehicle = dispatch.vehicle
            if not vehicle or vehicle.current_lat is None or vehicle.current_lon is None:
                continue

            resource_id = f"vehicle_{vehicle.id}"
            if resource_id in persisted_ids:
                continue

            route_info = optimizer.get_best_route((vehicle.current_lat, vehicle.current_lon), emergency_coords)
            distance_m = route_info.get('distance') or 0
            duration_s = route_info.get('duration') or 0
            distance_km = distance_m / 1000 if distance_m else 0
            eta_minutes = duration_s / 60 if duration_s else 0
            priority_score = duration_s or distance_m or 999
            resource_label = f"{vehicle.type} - {vehicle.force.name if vehicle.force else 'Fuerza'}"

            CalculatedRoute.objects.create(
                emergency=emergency,
                resource_id=resource_id,
                resource_type=resource_label,
                distance_km=distance_km,
                estimated_time_minutes=eta_minutes,
                priority_score=priority_score,
                route_geometry=route_info.get('geometry', {}),
                status='activa'
            )

            assignment_lookup[resource_id] = {
                'resource': {
                    'id': resource_id,
                    'name': resource_label,
                    'resource_type': 'vehicle',
                    'lat': vehicle.current_lat,
                    'lon': vehicle.current_lon,
                    'resource_obj': vehicle,
                },
                'route_info': route_info,
                'distance_km': distance_km,
                'estimated_arrival': eta_minutes,
                'priority_score': priority_score,
                'is_dispatch_resource': True,
            }
            persisted_ids.add(resource_id)

    return assignment_lookup


def process_emergency(request, pk):
    emergency = get_object_or_404(Emergency, pk=pk)

    # 1) Clasificación IA en la nube y actualización de código/prioridad/onda verde
    ia = classify_with_ai(emergency.description)
    provider_label = (ia.get('fuente') if ia else 'local').upper()

    if ia:
        emergency.code = ia['codigo']
        emergency.priority = 10 if ia['codigo'] == 'rojo' else 5 if ia['codigo'] == 'amarillo' else 1
        emergency.onda_verde = (ia['codigo'] == 'rojo')
        respuesta_ia = ia.get('respuesta_ia', 'Clasificación completada por sistema de IA.')
        emergency.ai_response = f"[Sistema {provider_label}] {respuesta_ia}"
        tipo = ia.get('tipo')
        tipo_map = {'bomberos': 'Bomberos', 'medico': 'SAME', 'policial': 'Policía'}
        fuerza_nombre = tipo_map.get(tipo)
        if fuerza_nombre:
            fuerza = Force.objects.filter(name=fuerza_nombre).first()
            if fuerza:
                emergency.assigned_force = fuerza
    else:
        if not emergency.code:
            emergency.code = emergency.classify_code()
        emergency.ai_response = "Sistema de IA no disponible. Clasificación realizada por reglas básicas."

    # 2) Calcular rutas óptimas y asignar recursos priorizando ETA
    route_assignments = calculate_emergency_routes(emergency)
    best_assignment = None

    recommended_resources = []
    if ia:
        recommended_resources = ia.get('recursos') or ia.get('recommended_resources') or []

    if recommended_resources:
        max_assignments = max(1, sum(rec.get('cantidad', 1) for rec in recommended_resources))
    else:
        max_assignments = 3 if emergency.code == 'rojo' else 2 if emergency.code == 'amarillo' else 1

    if route_assignments:
        # Persistir rutas calculadas para consulta posterior
        CalculatedRoute.objects.filter(emergency=emergency, status='activa').delete()
        for stored in route_assignments[:5]:
            resource_info = stored.get('resource', {})
            route_info = stored.get('route_info') or {}
            CalculatedRoute.objects.create(
                emergency=emergency,
                resource_id=resource_info.get('id', 'recurso'),
                resource_type=resource_info.get('name', resource_info.get('resource_type', 'Recurso')),
                distance_km=stored.get('distance_km') or 0,
                estimated_time_minutes=stored.get('estimated_arrival') or 0,
                priority_score=stored.get('priority_score') or 999,
                route_geometry=route_info.get('geometry', {}),
                status='activa'
            )

        for idx, assignment in enumerate(route_assignments[:max_assignments]):
            resource = assignment.get('resource', {})
            resource_obj = resource.get('resource_obj')
            resource_type = resource.get('resource_type') or resource.get('type')

            if best_assignment is None:
                best_assignment = assignment

            if resource_obj:
                if resource_type == 'vehicle':
                    resource_obj.status = 'en_ruta'
                    resource_obj.target_lat = emergency.location_lat
                    resource_obj.target_lon = emergency.location_lon
                    resource_obj.save(update_fields=['status', 'target_lat', 'target_lon'])

                    dispatch, _ = EmergencyDispatch.objects.get_or_create(
                        emergency=emergency,
                        force=resource_obj.force,
                        defaults={'vehicle': resource_obj, 'status': 'en_ruta'}
                    )
                    dispatch.vehicle = resource_obj
                    dispatch.status = 'en_ruta'
                    dispatch.save(update_fields=['vehicle', 'status'])

                    if idx == 0:
                        emergency.assigned_vehicle = resource_obj
                        if emergency.assigned_force_id in (None, resource_obj.force_id):
                            emergency.assigned_force = resource_obj.force

                elif resource_type == 'agent':
                    resource_obj.status = 'en_ruta'
                    resource_obj.target_lat = emergency.location_lat
                    resource_obj.target_lon = emergency.location_lon
                    resource_obj.save(update_fields=['status', 'target_lat', 'target_lon'])

        emergency.status = 'asignada'
    else:
        emergency.process_ia()

    _persist_routes_for_emergency(
        emergency,
        route_assignments,
        include_dispatches=True,
        max_routes=max(12, len(route_assignments))
    )

    calculated_routes = list(
        CalculatedRoute.objects.filter(emergency=emergency).order_by('priority_score', 'distance_km')
    )
    dispatches = list(emergency.dispatches.select_related('vehicle', 'force'))
    dispatch_resource_ids = {
        f"vehicle_{dispatch.vehicle_id}" for dispatch in dispatches if dispatch.vehicle_id
    }

    dispatch_summary = []
    for idx, route in enumerate(calculated_routes, start=1):
        dispatch_summary.append({
            'rank': idx,
            'name': route.resource_type,
            'eta': route.estimated_time_minutes,
            'distance': route.distance_km,
            'resource_type': route.resource_type,
            'is_dispatch': route.resource_id in dispatch_resource_ids,
        })

    calculated_ids = {route.resource_id for route in calculated_routes}
    for dispatch in dispatches:
        if not dispatch.vehicle_id:
            continue
        resource_id = f"vehicle_{dispatch.vehicle_id}"
        if resource_id in calculated_ids:
            continue
        name = f"{dispatch.vehicle.type} - {dispatch.force.name}" if dispatch.vehicle else dispatch.force.name
        dispatch_summary.append({
            'rank': len(dispatch_summary) + 1,
            'name': name,
            'eta': None,
            'distance': None,
            'resource_type': dispatch.vehicle.type if dispatch.vehicle else dispatch.force.name,
            'is_dispatch': True,
        })

    if best_assignment is None and calculated_routes:
        best_assignment = {
            'distance_km': calculated_routes[0].distance_km,
            'estimated_arrival': calculated_routes[0].estimated_time_minutes,
        }

    # 3) Calcular distancia/ETA tomando el mejor recurso
    dist_txt = "N/D"
    eta_txt = "N/D"
    if best_assignment:
        distance = best_assignment.get('distance_km')
        eta = best_assignment.get('estimated_arrival')
        if distance is not None:
            dist_txt = f"{distance:.2f} km"
        if eta is not None:
            eta_txt = f"{eta:.0f} min"
    elif (
        emergency.assigned_vehicle
        and emergency.location_lat is not None
        and emergency.location_lon is not None
        and emergency.assigned_vehicle.current_lat is not None
        and emergency.assigned_vehicle.current_lon is not None
    ):
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
    informe.append(f"Clasificación IA ({provider_label})")
    if ia:
        informe.append(f"- Tipo: {tipo_info}")
        informe.append(f"- Código: {emergency.code}")
        if score is not None:
            informe.append(f"- Puntaje: {score}")
        if razones:
            informe.append("- Razones:")
            for r in razones:
                informe.append(f"  - {r}")
        recursos = ia.get('recursos') or []
        if recursos:
            informe.append("- Recursos sugeridos por IA:")
            for rec in recursos:
                cantidad = rec.get('cantidad', 1)
                detalle = rec.get('detalle')
                detalle_txt = f" ({detalle})" if detalle else ""
                informe.append(f"  - {cantidad} x {rec.get('tipo')}{detalle_txt}")
    else:
        informe.append("- IA no disponible (se mantuvo la clasificación existente)")
        informe.append(f"- Código: {emergency.code}")

    informe.append("")
    informe.append("Recursos asignados (orden por ETA)")
    if dispatch_summary:
        for item in dispatch_summary:
            eta_val = item['eta']
            distance_val = item['distance']
            eta_txt_item = f"{eta_val:.1f} min" if eta_val is not None else "N/D"
            dist_txt_item = f"{distance_val:.1f} km" if distance_val is not None else "N/D"
            prefix = "🚦" if emergency.onda_verde and item.get('is_dispatch') else ("🚨" if item.get('is_dispatch') else "🛡️")
            informe.append(f"- #{item['rank']} {prefix} {item['name']} → {dist_txt_item} / {eta_txt_item}")
    else:
        informe.append("- No se encontraron recursos óptimos. Se aplicó fallback estándar.")

    informe.append("")
    informe.append("Estado de movilidad")
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
    emergency.save()

    messages.success(request, f"Emergencia #{emergency.pk} procesada con IA {provider_label} y rutas optimizadas.")
    return redirect('emergency_detail', pk=emergency.pk)


def emergency_detail(request, pk):
    emergency = get_object_or_404(Emergency, pk=pk)
    calculated_routes = CalculatedRoute.objects.filter(emergency=emergency).order_by('priority_score', 'distance_km')
    # Serialize routes for map (Leaflet expects [lat, lon])
    routes_payload = []
    for r in calculated_routes:
        geom = r.route_geometry or {}
        coords = []
        if geom.get('type') == 'LineString':
            # Stored as lon,lat -> convert to lat,lon
            for c in geom.get('coordinates', []):
                if isinstance(c, (list, tuple)) and len(c) >= 2:
                    coords.append([c[1], c[0]])
        routes_payload.append({
            'resource_id': r.resource_id,
            'resource_type': r.resource_type,
            'distance_km': r.distance_km,
            'eta_min': r.estimated_time_minutes,
            'priority_score': r.priority_score,
            'status': r.status,
            'calculated_at': r.calculated_at.isoformat() if r.calculated_at else None,
            'completed_at': r.completed_at.isoformat() if r.completed_at else None,
            'coordinates': coords,
            'raw_geometry': geom,
        })
    emergency_payload = {
        'id': emergency.id,
        'code': emergency.code,
        'status': emergency.status,
        'onda_verde': emergency.onda_verde,
        'lat': emergency.location_lat,
        'lon': emergency.location_lon,
        'address': emergency.address,
        'description': emergency.description,
    }
    context = {
        'emergency': emergency,
        'calculated_routes': calculated_routes,
        'routes_json': json.dumps(routes_payload, cls=DjangoJSONEncoder),
        'emergency_json': json.dumps(emergency_payload, cls=DjangoJSONEncoder),
    }
    return render(request, 'core/emergency_detail.html', context)

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
    from .llm import get_ai_status, classify_with_ai
    
    status = get_ai_status()
    
    # Test de clasificación
    test_description = "Accidente de tránsito con heridos en Av. Corrientes"
    test_result = None
    test_error = None
    
    try:
        test_result = classify_with_ai(test_description)
    except Exception as e:
        test_error = str(e)
    
    context = {
        'status': status,
        'test_description': test_description,
        'test_result': test_result,
        'test_error': test_error,
        'settings_config': {
            'AI_PROVIDER': getattr(settings, 'AI_PROVIDER', 'openai'),
            'OPENAI_MODEL': getattr(settings, 'OPENAI_MODEL', 'No configurado'),
            'OPENAI_API_BASE': getattr(settings, 'OPENAI_API_BASE', 'https://api.openai.com/v1'),
            'OPENAI_API_KEY_CONFIGURADO': bool(getattr(settings, 'OPENAI_API_KEY', None)),
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
    try:
        emergency = get_object_or_404(Emergency, pk=emergency_id)
    except Http404:
        print(f"Emergencia {emergency_id} no encontrada, devolviendo ruta de prueba")
        return JsonResponse({
            'success': True,
            'routes': [{
                'resource_id': 'fallback',
                'resource_type': f'Recurso Prueba #{emergency_id}',
                'distance': '2.5',
                'duration': '8',
                'geometry': {
                    'type': 'LineString',
                    'coordinates': [
                        [-58.4173, -34.6118],
                        [-58.3816, -34.6037]
                    ]
                },
                'score': 75,
                'coordinates': [[-34.6118, -58.4173], [-34.6037, -58.3816]]
            }],
            'emergency': {
                'id': emergency_id,
                'type': 'Emergencia Test',
                'priority': 'Normal',
                'address': 'Ubicación de prueba'
            }
        })

    # Si la emergencia ya está resuelta, no recalcular rutas: devolver estado congelado
    if emergency.status == 'resuelta':
        calculated_routes = list(
            CalculatedRoute.objects.filter(emergency=emergency).order_by('priority_score', 'distance_km')
        )
        routes_data = []
        for idx, route_obj in enumerate(calculated_routes, start=1):
            routes_data.append({
                'resource_id': route_obj.resource_id,
                'resource_type': route_obj.resource_type,
                'resource_name': route_obj.resource_type,
                'distance': f"{route_obj.distance_km:.1f}",
                'duration': f"{route_obj.estimated_time_minutes:.0f}",
                'geometry': route_obj.route_geometry or {},
                'score': route_obj.priority_score,
                'coordinates': None,
                'is_dispatch': False,
                'vehicle_type': '',
                'dispatch_info': None,
                'rank': idx,
                'is_primary': idx == 1,
                'frozen': True,
            })
        return JsonResponse({
            'success': True,
            'routes': routes_data,
            'emergency': {
                'id': emergency.id,
                'type': getattr(emergency, 'type', 'Emergencia'),
                'priority': getattr(emergency, 'priority', 'Normal'),
                'address': getattr(emergency, 'address', 'Sin dirección'),
                'status': emergency.status,
                'onda_verde': emergency.onda_verde,
            },
            'green_wave_active': emergency.onda_verde,
            'frozen': True,
            'message': 'Emergencia resuelta: rutas congeladas (no se recalculan).'
        })

    try:
        routes = calculate_emergency_routes(emergency)
        start_coords = {}
        for assignment in routes:
            resource = assignment.get('resource') or {}
            resource_id = resource.get('id')
            lat = resource.get('lat')
            lon = resource.get('lon')
            if resource_id and lat is not None and lon is not None:
                start_coords[resource_id] = (lat, lon)

        if not routes:
            print(f"No se calcularon rutas para {emergency_id}, creando ruta de respaldo")
            fallback_geometry = {
                'type': 'LineString',
                'coordinates': [
                    [-58.4173, -34.6118],
                    [emergency.location_lon, emergency.location_lat]
                ]
            }
            routes = [{
                'resource': {
                    'id': f'fallback_{emergency_id}',
                    'name': f'Recurso Provisional #{emergency_id}',
                    'type': 'Simulado'
                },
                'route_info': {
                    'geometry': fallback_geometry,
                    'distance': 3200,
                    'duration': 720
                },
                'priority_score': 999,
                'estimated_arrival': 12,
                'distance_km': 3.2
            }]

        max_routes = getattr(settings, 'ROUTING_MAX_RESULTS', 6)
        _persist_routes_for_emergency(
            emergency,
            routes,
            include_dispatches=True,
            max_routes=max(max_routes, len(routes))
        )

        calculated_routes = list(
            CalculatedRoute.objects.filter(emergency=emergency).order_by('priority_score', 'distance_km')
        )

        dispatches = list(emergency.dispatches.select_related('vehicle', 'force'))
        dispatch_resource_ids = {
            f"vehicle_{dispatch.vehicle_id}" for dispatch in dispatches if dispatch.vehicle_id
        }
        dispatch_map = {
            f"vehicle_{dispatch.vehicle_id}": dispatch
            for dispatch in dispatches if dispatch.vehicle_id
        }

        for dispatch in dispatches:
            if dispatch.vehicle and dispatch.vehicle.current_lat is not None and dispatch.vehicle.current_lon is not None:
                start_coords[f"vehicle_{dispatch.vehicle_id}"] = (
                    dispatch.vehicle.current_lat,
                    dispatch.vehicle.current_lon
                )

        routes_data = []
        for idx, route_obj in enumerate(calculated_routes, start=1):
            start = start_coords.get(route_obj.resource_id)
            coordinates = None
            if start:
                coordinates = [[start[0], start[1]], [emergency.location_lat, emergency.location_lon]]

            dispatch = dispatch_map.get(route_obj.resource_id)
            dispatch_info = None
            if dispatch:
                dispatch_info = {
                    'id': dispatch.id,
                    'force': dispatch.force.name if dispatch.force else '',
                    'vehicle_id': dispatch.vehicle_id,
                    'vehicle_name': str(dispatch.vehicle) if dispatch.vehicle else '',
                    'status': dispatch.status,
                }

            routes_data.append({
                'resource_id': route_obj.resource_id,
                'resource_type': route_obj.resource_type,
                'resource_name': route_obj.resource_type,
                'distance': f"{route_obj.distance_km:.1f}",
                'duration': f"{route_obj.estimated_time_minutes:.0f}",
                'geometry': route_obj.route_geometry or {},
                'score': route_obj.priority_score,
                'coordinates': coordinates,
                'is_dispatch': route_obj.resource_id in dispatch_resource_ids,
                'vehicle_type': dispatch.vehicle.type if dispatch and dispatch.vehicle else '',
                'dispatch_info': dispatch_info,
                'rank': idx,
                'is_primary': idx == 1,
            })

        if not routes_data:
            raise ValueError("No se pudieron construir rutas válidas")

        print(f"Devolviendo {len(routes_data)} rutas para emergencia {emergency_id}")

        return JsonResponse({
            'success': True,
            'routes': routes_data,
            'emergency': {
                'id': emergency.id,
                'type': getattr(emergency, 'type', 'Emergencia'),
                'priority': getattr(emergency, 'priority', 'Normal'),
                'address': getattr(emergency, 'address', 'Sin dirección'),
                'status': emergency.status,
                'onda_verde': emergency.onda_verde,
            },
            'green_wave_active': emergency.onda_verde,
        })

    except Exception as e:
        print(f"Error calculando rutas para emergencia {emergency_id}: {e}")
        return JsonResponse({
            'success': True,
            'routes': [{
                'resource_id': 'fallback_error',
                'resource_type': f'Ruta de Emergencia {emergency_id}',
                'resource_name': f'Ruta de Emergencia {emergency_id}',
                'distance': '1.5',
                'duration': '5',
                'geometry': {
                    'type': 'LineString',
                    'coordinates': [
                        [-58.4173, -34.6118],
                        [-58.4100, -34.6050]
                    ]
                },
                'score': 50,
                'coordinates': [[-34.6118, -58.4173], [-34.6050, -58.4100]],
                'is_dispatch': False,
                'vehicle_type': '',
                'dispatch_info': None,
            }],
            'emergency': {
                'id': emergency_id,
                'type': 'Emergencia',
                'priority': 'Normal',
                'address': 'Error - Ruta de respaldo',
                'status': 'desconocido',
                'onda_verde': False,
            },
            'green_wave_active': False,
            'error': str(e),
        })

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
    tracking_entries = []

    active_routes = {
        (route.emergency_id, route.resource_id): route
        for route in CalculatedRoute.objects.filter(status='activa').select_related('emergency')
    }

    dispatches = EmergencyDispatch.objects.select_related('vehicle', 'emergency', 'force').filter(
        status__in=['despachado', 'en_ruta']
    )

    for dispatch in dispatches:
        if not dispatch.vehicle:
            continue

        lookup_key = (dispatch.emergency_id, f'vehicle_{dispatch.vehicle_id}')
        route_obj = active_routes.get(lookup_key)
        if not route_obj:
            continue

        tracking_entry = _build_vehicle_tracking(dispatch, route_obj)
        if tracking_entry:
            tracking_entries.append(tracking_entry)

    agents_in_route = Agent.objects.filter(status='en_ruta').select_related('force')
    for agent in agents_in_route:
        if not (agent.lat and agent.lon and agent.target_lat and agent.target_lon):
            continue

        eta_data = get_real_time_eta(
            (agent.lat, agent.lon),
            (agent.target_lat, agent.target_lon)
        )

        tracking_entries.append({
            'id': f'agent_{agent.id}',
            'type': 'agent',
            'name': f"{agent.name} - {agent.force.name}",
            'current_position': [agent.lat, agent.lon],
            'target_position': [agent.target_lat, agent.target_lon],
            'eta_minutes': round(eta_data['eta_minutes'], 1),
            'distance_remaining_km': round(eta_data['distance_km'], 2),
            'route_geometry': eta_data['route_geometry'],
            'status': agent.status,
            'traffic_level': 'moderado',
            'traffic_label': 'Movimiento simulado',
            'traffic_color': '#3b82f6',
            'progress': 0.5,
            'speed_kmh': round((eta_data['distance_km'] / max(eta_data['eta_minutes'] / 60, 0.1)), 1),
            'is_code_red': False,
            'onda_verde': False,
        })

    tracking_entries.sort(key=lambda entry: (entry['type'] != 'vehicle', entry.get('eta_minutes', 999)))

    return JsonResponse({
        'success': True,
        'tracking_data': tracking_entries,
        'total_resources_in_route': len(tracking_entries),
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

def route_details_api(request, emergency_id):
    """API para obtener detalles completos de una ruta"""
    try:
        emergency = get_object_or_404(Emergency, id=emergency_id)
        
        # Calcular ruta actual
        routes = calculate_emergency_routes(emergency)
        if not routes:
            return JsonResponse({
                'success': False,
                'error': 'No se pudo calcular la ruta'
            })
        
        best_route = routes[0]  # Tomar la mejor ruta
        
        # Obtener detalles del recurso asignado
        resource_info = {
            'type': 'No asignado',
            'id': 'N/A',
            'current_location': 'Ubicación desconocida'
        }
        
        if emergency.assigned_force:
            vehicles = Vehicle.objects.filter(force=emergency.assigned_force).first()
            if vehicles:
                resource_info = {
                    'type': f"{vehicles.type} - {emergency.assigned_force.name}",
                    'id': vehicles.license_plate,
                    'current_location': f"Base {emergency.assigned_force.name}"
                }
        
        # Contar semáforos en la ruta (simulado)
        traffic_lights_count = max(1, int(best_route['distance'] * 2))  # Aproximación
        
        route_details = {
            'emergency_type': emergency.type,
            'priority': emergency.priority,
            'address': emergency.address or f"Lat: {emergency.lat}, Lon: {emergency.lon}",
            'resource_type': resource_info['type'],
            'resource_id': resource_info['id'],
            'current_location': resource_info['current_location'],
            'distance': f"{best_route['distance']:.1f}",
            'duration': f"{best_route['duration']:.0f}",
            'traffic_lights_count': traffic_lights_count
        }
        
        return JsonResponse({
            'success': True,
            'route_details': route_details
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Error al obtener detalles: {str(e)}'
        })

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

def stored_routes_api(request, emergency_id):
    """Devuelve las rutas ya guardadas (CalculatedRoute) sin recalcular nada."""
    try:
        emergency = get_object_or_404(Emergency, pk=emergency_id)
        routes = CalculatedRoute.objects.filter(emergency=emergency).order_by('priority_score','distance_km')
        payload = []
        for idx, r in enumerate(routes, start=1):
            geom = r.route_geometry or {}
            coords = []
            if geom.get('type') == 'LineString':
                for c in geom.get('coordinates', []):
                    if isinstance(c,(list,tuple)) and len(c)>=2:
                        coords.append([c[1], c[0]])
            payload.append({
                'resource_id': r.resource_id,
                'resource_type': r.resource_type,
                'distance': f"{r.distance_km:.1f}",
                'duration': f"{r.estimated_time_minutes:.0f}",
                'geometry': geom,
                'coordinates': coords,
                'score': r.priority_score,
                'rank': idx,
                'is_primary': idx == 1,
                'status': r.status,
            })
        return JsonResponse({
            'success': True,
            'routes': payload,
            'emergency': {
                'id': emergency.id,
                'status': emergency.status,
                'onda_verde': emergency.onda_verde,
                'code': emergency.code,
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e), 'routes': []}, status=500)


def emergency_mobility_api(request, emergency_id):
    """API que devuelve progreso por recurso (rutas calculadas) + ventanas de onda verde personalizadas.

    Estructura:
    {
      success: true,
      frozen: bool,
      emergency: {...},
      resources: [
         {resource_id, name, type, progress, distance_km, distance_remaining_km, eta_minutes,
          speed_kmh, traffic: {...}, intersections:[{name, arrival_time, green_start, green_end, priority}]}
      ]
    }
    """
    try:
        emergency = get_object_or_404(Emergency, pk=emergency_id)
        frozen = emergency.status == 'resuelta'
        # Obtener todas las rutas calculadas (persistidas)
        routes = list(CalculatedRoute.objects.filter(emergency=emergency).order_by('priority_score','distance_km'))
        # Pre-cargar despachos para mapear resource_id -> dispatch
        dispatches = {f"vehicle_{d.vehicle_id}": d for d in emergency.dispatches.select_related('vehicle','force') if d.vehicle_id}

        resources_payload = []
        now = timezone.now()
        for r in routes:
            # Cálculo de progreso / dinámica
            est_minutes = r.estimated_time_minutes or 0
            total_seconds = max(int(est_minutes * 60), 60)
            # Traffic factor determinístico
            traffic_factor = _determine_traffic_factor(r, emergency)
            adjusted_total = total_seconds * traffic_factor
            calc_time = r.calculated_at or (emergency.reported_at if hasattr(emergency,'reported_at') else now)
            elapsed = (now - calc_time).total_seconds()
            progress = 1.0 if frozen else min(1.0, elapsed / adjusted_total if adjusted_total>0 else 0)

            # Posición interpolada sobre la geometría
            current_point = _interpolate_route_point(r.route_geometry, progress)
            # Distancias
            distance_km = r.distance_km or 0.0
            remaining_km = max(distance_km * (1 - progress), 0)
            # Velocidad media base asumida (km/h)
            base_speed = 0.0
            if est_minutes > 0:
                base_speed = distance_km / (est_minutes/60)
            speed_kmh = base_speed / max(traffic_factor, 0.1) if base_speed else 0.0
            eta_minutes = 0.0 if progress >= 1 else (remaining_km / speed_kmh * 60 if speed_kmh>1 else remaining_km/ (30/60) if remaining_km>0 else 0)
            traffic_meta = _traffic_level_metadata(traffic_factor)

            # Green wave windows específicas para esta ruta
            intersections_data = []
            try:
                if emergency.location_lat and emergency.location_lon:
                    # Definir punto de inicio dinámico: posición actual si disponible, sino primer punto de la geometría
                    if current_point:
                        start_lat, start_lon = current_point
                    else:
                        coords = (r.route_geometry or {}).get('coordinates') or []
                        if coords:
                            # GeoJSON lon,lat
                            start_lat, start_lon = coords[0][1], coords[0][0]
                        else:
                            start_lat, start_lon = emergency.location_lat, emergency.location_lon
                    end_lat, end_lon = emergency.location_lat, emergency.location_lon

                    # Intersecciones potenciales sobre la línea recta (aprox) del tramo restante
                    route_intersections = traffic_manager.find_intersections_on_route(
                        start_lat, start_lon, end_lat, end_lon, max_distance=600
                    )
                    if route_intersections:
                        # Ajustar distancias para el progreso ya recorrido (restante)
                        total_m = distance_km * 1000
                        progressed_m = total_m * progress
                        remaining_intersections = []
                        for itx in route_intersections:
                            # Filtrar intersecciones ya pasadas
                            remaining_m = itx['distance_from_start'] - progressed_m
                            if remaining_m <= 50:  # ya pasada (<=50m)
                                continue
                            # Crear copia ajustada con distance_from_start relativo al punto actual
                            adjusted = dict(itx)
                            adjusted['distance_from_start'] = remaining_m
                            remaining_intersections.append(adjusted)
                        if remaining_intersections:
                            avg_speed_kmh = speed_kmh if speed_kmh>5 else max(30, speed_kmh)
                            timing = traffic_manager.calculate_green_wave_timing(remaining_intersections, avg_speed_kmh=avg_speed_kmh)
                            # Limitar para payload ligero
                            for t in timing[:6]:
                                intersections_data.append({
                                    'id': t['intersection']['id'],
                                    'name': t['intersection']['name'],
                                    'lat': t['intersection']['lat'],
                                    'lon': t['intersection']['lon'],
                                    'arrival_time': t['arrival_time'].isoformat(),
                                    'green_start': t['green_start'].isoformat(),
                                    'green_end': t['green_end'].isoformat(),
                                    'priority': t['priority'],
                                    'window_seconds': int((t['green_end'] - t['green_start']).total_seconds())
                                })
            except Exception as ge:
                print(f"Error calculando ventanas onda verde recurso {r.resource_id}: {ge}")

            dispatch = dispatches.get(r.resource_id)
            resources_payload.append({
                'resource_id': r.resource_id,
                'name': r.resource_type,
                'type': 'vehicle' if r.resource_id.startswith('vehicle_') else 'resource',
                'distance_km': round(distance_km, 3),
                'distance_remaining_km': round(remaining_km, 3),
                'eta_minutes': round(eta_minutes, 2),
                'progress': round(progress, 4),
                'speed_kmh': round(speed_kmh, 2),
                'traffic': {
                    'level': traffic_meta['level'],
                    'label': traffic_meta['label'],
                    'color': traffic_meta['color'],
                    'factor': round(traffic_factor, 2)
                },
                'intersections': intersections_data,
                'status': 'en_ruta' if (progress < 1 and not frozen) else 'en_escena',
                'dispatch_id': dispatch.id if dispatch else None,
                'frozen': frozen,
            })

        # Ordenar por ETA y progreso
        resources_payload.sort(key=lambda x: (x['progress']>=1, x['eta_minutes'] if x['eta_minutes'] else 9999))

        return JsonResponse({
            'success': True,
            'frozen': frozen,
            'emergency': {
                'id': emergency.id,
                'status': emergency.status,
                'onda_verde': emergency.onda_verde,
                'code': emergency.code,
            },
            'resources': resources_payload,
            'generated_at': timezone.now().isoformat()
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
