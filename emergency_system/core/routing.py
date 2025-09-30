"""
Sistema de ruteo y optimización de rutas para emergencias
"""

import requests
import json
import math
import time
import copy
from collections import OrderedDict
from django.conf import settings
from typing import List, Dict, Tuple, Optional
import logging

logger = logging.getLogger(__name__)

# Configuración por defecto para CABA
CABA_BOUNDS = {
    'south': -34.7056,
    'west': -58.5315,
    'north': -34.5266, 
    'east': -58.3324
}

class RouteOptimizer:
    """
    Optimizador de rutas para emergencias usando múltiples APIs de ruteo
    """
    
    def __init__(self):
        # API Keys - se pueden configurar en settings.py
        self.openroute_key = getattr(settings, 'OPENROUTE_API_KEY', None)
        self.mapbox_key = getattr(settings, 'MAPBOX_API_KEY', None)
        self.graphhopper_key = getattr(settings, 'GRAPHOPPER_API_KEY', None)
        self._route_cache: OrderedDict[str, Dict] = OrderedDict()
        self._route_cache_size = getattr(settings, 'ROUTING_CACHE_SIZE', 128)
        self._openroute_rate_limited_until = 0.0
        
    def calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Calcula distancia euclidiana entre dos puntos (en metros aproximados)
        """
        R = 6371000  # Radio de la Tierra en metros
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)
        
        a = (math.sin(delta_lat / 2) * math.sin(delta_lat / 2) +
             math.cos(lat1_rad) * math.cos(lat2_rad) *
             math.sin(delta_lon / 2) * math.sin(delta_lon / 2))
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        distance = R * c
        
        return distance

    def get_route_openroute(self, start_coords: Tuple[float, float], 
                           end_coords: Tuple[float, float], 
                           profile: str = 'driving-car') -> Optional[Dict]:
        """
        Obtiene ruta usando OpenRouteService API
        """
        if not self.openroute_key:
            logger.warning("OpenRoute API key no configurada")
            return None

        now_ts = time.time()
        if now_ts < self._openroute_rate_limited_until:
            logger.info("OpenRouteService en backoff temporal; usando fallback")
            return None
            
        url = f"https://api.openrouteservice.org/v2/directions/{profile}"
        
        headers = {
            'Authorization': self.openroute_key,
            'Content-Type': 'application/json'
        }
        
        data = {
            'coordinates': [
                [start_coords[1], start_coords[0]],  # lon, lat
                [end_coords[1], end_coords[0]]       # lon, lat
            ],
            'format': 'geojson',
            'instructions': True,
            'units': 'm'
        }
        
        try:
            response = requests.post(url, json=data, headers=headers, timeout=10)
            if response.status_code == 200:
                return response.json()
            if response.status_code == 429:
                logger.error("OpenRoute API rate limit alcanzado (HTTP 429). Activando backoff de 2 minutos.")
                self._openroute_rate_limited_until = now_ts + getattr(settings, 'OPENROUTE_BACKOFF_SECONDS', 120)
                return None
            logger.error(f"OpenRoute API error: {response.status_code}")
            return None
        except requests.RequestException as e:
            logger.error(f"Error conectando con OpenRoute API: {e}")
            return None

    def get_route_mapbox(self, start_coords: Tuple[float, float], 
                        end_coords: Tuple[float, float]) -> Optional[Dict]:
        """
        Obtiene ruta usando Mapbox Directions API
        """
        if not self.mapbox_key:
            logger.warning("Mapbox API key no configurada")
            return None
            
        url = f"https://api.mapbox.com/directions/v5/mapbox/driving/{start_coords[1]},{start_coords[0]};{end_coords[1]},{end_coords[0]}"
        
        params = {
            'access_token': self.mapbox_key,
            'geometries': 'geojson',
            'steps': 'true',
            'overview': 'full'
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Mapbox API error: {response.status_code}")
                return None
        except requests.RequestException as e:
            logger.error(f"Error conectando con Mapbox API: {e}")
            return None

    def get_route_osrm(self, start_coords: Tuple[float, float], 
                      end_coords: Tuple[float, float]) -> Optional[Dict]:
        """
        Obtiene ruta usando el servidor público OSRM (driving) con geometría GeoJSON.
        Timeout corto para evitar bloqueos; fallback silencioso.
        """
        return self._get_route_osrm_multi(start_coords, end_coords)

    def _get_route_osrm_multi(self, start_coords: Tuple[float, float], end_coords: Tuple[float, float]) -> Optional[Dict]:
        """Prueba múltiples hosts OSRM públicos para mejorar resiliencia y retorna la primera ruta válida."""
        hosts = [
            "https://router.project-osrm.org/route/v1/driving",
            # Servidor comunitario OSM (limites de uso: solo demostración, no producción)
            "https://routing.openstreetmap.de/routed-car/route/v1/driving"
        ]
        start_lon, start_lat = start_coords[1], start_coords[0]
        end_lon, end_lat = end_coords[1], end_coords[0]
        params = {
            'overview': 'full',
            'geometries': 'geojson',
            'steps': 'true'
        }
        for base in hosts:
            url = f"{base}/{start_lon},{start_lat};{end_lon},{end_lat}"
            try:
                response = requests.get(url, params=params, timeout=6)
                if response.status_code != 200:
                    logger.debug(f"OSRM host {base} fallo HTTP {response.status_code}")
                    continue
                data = response.json()
                if not data.get('routes'):
                    continue
                # Validar que la geometría no sea trivial (2 puntos) – rara vez pasa pero filtramos
                geom = data['routes'][0].get('geometry') or {}
                if geom.get('type') == 'LineString' and len(geom.get('coordinates', [])) < 3:
                    logger.debug("OSRM devolvió geometría trivial (<3 puntos), intentando siguiente host")
                    continue
                return data
            except requests.RequestException as e:
                logger.debug(f"OSRM host {base} error: {e}")
                continue
        return None

    def get_route_graphhopper(self, start_coords: Tuple[float,float], end_coords: Tuple[float,float]) -> Optional[Dict]:
        """Obtiene ruta usando GraphHopper (si hay API key) con geometría GeoJSON (points_encoded=false)."""
        if not self.graphhopper_key:
            return None
        url = "https://graphhopper.com/api/1/route"
        params = {
            'point': [f"{start_coords[0]},{start_coords[1]}", f"{end_coords[0]},{end_coords[1]}"],
            'profile': 'car',
            'points_encoded': 'false',
            'locale': 'es',
            'instructions': 'true',
            'calc_points': 'true',
            'key': self.graphhopper_key
        }
        try:
            # `requests` no arma multi 'point' automáticamente con list, construimos manual
            flat_params = []
            for k,v in params.items():
                if isinstance(v, list):
                    for item in v:
                        flat_params.append((k,item))
                else:
                    flat_params.append((k,v))
            response = requests.get(url, params=flat_params, timeout=10)
            if response.status_code != 200:
                logger.warning(f"GraphHopper error HTTP {response.status_code}")
                return None
            data = response.json()
            if not data.get('paths'):
                return None
            path = data['paths'][0]
            geo = path.get('points')  # GeoJSON when points_encoded=false
            if geo and geo.get('type') == 'LineString' and len(geo.get('coordinates', [])) >= 3:
                return data
            return None
        except requests.RequestException as e:
            logger.warning(f"GraphHopper error: {e}")
            return None

    def get_best_route(self, start_coords: Tuple[float, float], 
                      end_coords: Tuple[float, float]) -> Dict:
        """
        Obtiene la mejor ruta disponible probando múltiples APIs
        """
        cache_key = self._build_cache_key(start_coords, end_coords)
        cached = self._route_cache.get(cache_key)
        if cached:
            # Refrescar orden LRU
            self._route_cache.move_to_end(cache_key)
            return copy.deepcopy(cached)

    # Orden de preferencia: Mapbox -> OpenRoute -> OSRM (multi-host) -> GraphHopper -> Directo mejorado
        # 1. Mapbox
        if self.mapbox_key:
            route = self.get_route_mapbox(start_coords, end_coords)
            if route and route.get('routes'):
                best = route['routes'][0]
                result = {
                    'provider': 'Mapbox',
                    'route': best,
                    'geometry': best.get('geometry'),
                    'distance': best.get('distance'),
                    'duration': best.get('duration'),
                    'steps': best.get('legs', [{}])[0].get('steps', [])
                }
                if result['geometry']:
                    self._store_cache(cache_key, result)
                    return copy.deepcopy(result)

        # 2. OpenRouteService
        route = self.get_route_openroute(start_coords, end_coords)
        if route and 'features' in route and route['features']:
            feature = route['features'][0]
            result = {
                'provider': 'OpenRoute',
                'route': feature,
                'geometry': feature['geometry'],
                'distance': feature['properties']['segments'][0]['distance'],
                'duration': feature['properties']['segments'][0]['duration'],
                'steps': feature['properties']['segments'][0].get('steps', [])
            }
            self._store_cache(cache_key, result)
            return copy.deepcopy(result)

        # 3. OSRM público (multi-host)
        route = self.get_route_osrm(start_coords, end_coords)
        if route and 'routes' in route and route['routes']:
            r0 = route['routes'][0]
            result = {
                'provider': 'OSRM',
                'route': r0,
                'geometry': r0.get('geometry'),
                'distance': r0.get('distance'),
                'duration': r0.get('duration'),
                'steps': r0.get('legs', [{}])[0].get('steps', [])
            }
            if result['geometry']:
                self._store_cache(cache_key, result)
                return copy.deepcopy(result)

        # 4. GraphHopper (opcional)
        gh = self.get_route_graphhopper(start_coords, end_coords)
        if gh and gh.get('paths'):
            path = gh['paths'][0]
            geo = path.get('points')
            if geo and geo.get('type') == 'LineString':
                result = {
                    'provider': 'GraphHopper',
                    'route': path,
                    'geometry': geo,
                    'distance': path.get('distance'),
                    'duration': path.get('time')/1000.0 if path.get('time') else None,
                    'steps': path.get('instructions', [])
                }
                self._store_cache(cache_key, result)
                return copy.deepcopy(result)
        
        # 5. Fallback mejorado: trayectoria "grid" (tipo L + desvíos) en vez de línea recta
        distance = self.calculate_distance(start_coords[0], start_coords[1], end_coords[0], end_coords[1])
        estimated_duration = (distance / 1000) / 22 * 60 * 60  # velocidad urbana más conservadora
        grid_coords = self._generate_grid_path(start_coords, end_coords)
        logger.info(f"✓ Fallback GRID usado ({len(grid_coords)} pts) {distance/1000:.2f}km en {estimated_duration/60:.1f} min")
        result = {
            'provider': 'FallbackGrid',
            'route': None,
            'geometry': {
                'type': 'LineString',
                'coordinates': [[c[1], c[0]] for c in grid_coords]  # lon, lat
            },
            'distance': distance,
            'duration': estimated_duration,
            'steps': []
        }
        self._store_cache(cache_key, result)
        return copy.deepcopy(result)

    def _store_cache(self, key: str, value: Dict):
        self._route_cache[key] = copy.deepcopy(value)
        self._route_cache.move_to_end(key)
        while len(self._route_cache) > self._route_cache_size:
            self._route_cache.popitem(last=False)

    @staticmethod
    def _build_cache_key(start_coords: Tuple[float, float], end_coords: Tuple[float, float]) -> str:
        return f"{round(start_coords[0], 5)}:{round(start_coords[1], 5)}->{round(end_coords[0], 5)}:{round(end_coords[1], 5)}"

    def find_optimal_assignments(self, emergency_coords: Tuple[float, float], 
                               available_resources: List[Dict]) -> List[Dict]:
        """
        Encuentra las asignaciones óptimas de recursos a una emergencia
        """
        assignments = []
        
        for resource in available_resources:
            resource_coords = (resource['lat'], resource['lon'])
            route_info = self.get_best_route(resource_coords, emergency_coords)
            
            # Calcular prioridad basada en tiempo estimado y tipo de recurso
            priority_score = self._calculate_priority_score(
                resource, route_info['duration'], route_info['distance']
            )
            
            assignments.append({
                'resource': resource,
                'route_info': route_info,
                'priority_score': priority_score,
                'estimated_arrival': route_info['duration'] / 60,  # minutos
                'distance_km': route_info['distance'] / 1000
            })
        
        # Ordenar por prioridad (menor tiempo = mayor prioridad)
        return sorted(assignments, key=lambda x: x['priority_score'])

    def _calculate_priority_score(self, resource: Dict, duration: float, distance: float) -> float:
        """
        Calcula score de prioridad para un recurso
        Menor score = mayor prioridad
        """
        base_score = duration  # Tiempo base en segundos
        
        # Ajustes por tipo de recurso
        resource_type = resource.get('type', 'unknown')
        if resource_type == 'ambulancia':
            base_score *= 0.8  # Prioridad alta para ambulancias
        elif resource_type == 'bomberos':
            base_score *= 0.9  # Alta prioridad para bomberos
        elif resource_type == 'policia':
            base_score *= 1.0  # Prioridad normal
        
        # Penalización por distancia extrema
        if distance > 20000:  # Más de 20km
            base_score *= 1.5
            
        return base_score

    def _generate_intermediate_points(self, start_lat: float, start_lon: float, 
                                    end_lat: float, end_lon: float) -> List[Tuple[float, float]]:
        """
        Genera puntos intermedios para hacer la ruta más realista
        """
        points = []
        
        # Crear 2-3 puntos intermedios según la distancia
        distance = self.calculate_distance(start_lat, start_lon, end_lat, end_lon) / 1000  # km
        
        if distance > 1.0:  # Más de 1km, agregar puntos intermedios
            import random
            num_points = min(3, int(distance))  # Máximo 3 puntos intermedios
            
            for i in range(1, num_points + 1):
                # Interpolación con pequeña variación para simular calles
                ratio = i / (num_points + 1)
                
                mid_lat = start_lat + (end_lat - start_lat) * ratio
                mid_lon = start_lon + (end_lon - start_lon) * ratio
                
                # Agregar pequeña variación aleatoria para simular calles reales
                variation = 0.001  # ~100 metros
                mid_lat += (random.random() - 0.5) * variation
                mid_lon += (random.random() - 0.5) * variation
                
                points.append((mid_lat, mid_lon))
        
        return points

    def _generate_grid_path(self, start: Tuple[float,float], end: Tuple[float,float]) -> List[Tuple[float,float]]:
        """
        Genera un camino en forma de rejilla (tipo calles ortogonales) para simular desplazamiento urbano.
        1. Avanza primero latitud hasta un punto intermedio, luego longitud, con 1-2 desvíos pequeños.
        Devuelve lista de puntos en (lat, lon).
        """
        s_lat, s_lon = start
        e_lat, e_lon = end
        points: List[Tuple[float,float]] = [(s_lat, s_lon)]
        d_lat = e_lat - s_lat
        d_lon = e_lon - s_lon
        # Elegir fracciones para giros
        frac1 = 0.35
        frac2 = 0.65
        mid1_lat = s_lat + d_lat * frac1
        mid2_lat = s_lat + d_lat * frac2
        # Pequeño desvío lateral (simulate street offset ~50-120m) usando delta lon y lat escalado
        offset_lat = 0.0007 if abs(d_lat) > 0.002 else 0.0004
        offset_lon = 0.0007 if abs(d_lon) > 0.002 else 0.0004
        # Trayectoria: subir/bajar parte, luego mover lateral, luego continuar
        # Segmento 1: mover latitud
        points.append((mid1_lat, s_lon))
        # Desvío lateral 1
        points.append((mid1_lat, s_lon + offset_lon * (1 if d_lon>=0 else -1)))
        # Segmento 2: continuar latitud
        points.append((mid2_lat, s_lon + offset_lon * (1 if d_lon>=0 else -1)))
        # Desvío lateral 2 hacia longitud destino parcial
        half_lon = s_lon + d_lon * 0.5
        points.append((mid2_lat + offset_lat * (1 if d_lat>=0 else -1), half_lon))
        # Segmento final: llegar a destino
        points.append((e_lat, half_lon))
        points.append((e_lat, e_lon))
        # Filtrar duplicados consecutivos
        filtered = []
        for p in points:
            if not filtered or (abs(filtered[-1][0]-p[0])>1e-6 or abs(filtered[-1][1]-p[1])>1e-6):
                filtered.append(p)
        return filtered

def get_route_optimizer():
    """Factory function para obtener instancia del optimizador"""
    return RouteOptimizer()

# Funciones de utilidad para las vistas
def calculate_emergency_routes(emergency):
    """
    Calcula rutas optimizadas para una emergencia específica
    SOLO devuelve las mejores 3-5 rutas más relevantes
    """
    from .models import Vehicle, Agent  # Import aquí para evitar circular imports
    
    if not (emergency.location_lat and emergency.location_lon):
        return []
    
    optimizer = get_route_optimizer()
    emergency_coords = (emergency.location_lat, emergency.location_lon)
    
    # Obtener recursos disponibles FILTRADOS por tipo de emergencia Y fuerza asignada
    available_resources = []
    emergency_type = getattr(emergency, 'type', '').lower()
    emergency_code = getattr(emergency, 'code', '').lower()
    assigned_force = getattr(emergency, 'assigned_force', None)
    
    # PRIORIZAR la fuerza asignada por la IA, luego por tipo de emergencia
    resource_priority = {}
    
    if assigned_force:
        # Prioridad alta para la fuerza asignada por IA
        assigned_force_name = assigned_force.name.lower()
        print(f"🎯 Fuerza asignada por IA: {assigned_force.name}")
        resource_priority[assigned_force_name] = 5  # Prioridad máxima
        
        # Prioridades secundarias basadas en la fuerza asignada
        if assigned_force_name == 'same':
            resource_priority.update({'ambulancia': 4, 'policia': 1, 'bomberos': 1})
        elif assigned_force_name == 'policía':
            resource_priority.update({'patrulla': 4, 'policia': 4, 'same': 1, 'bomberos': 1})
        elif assigned_force_name == 'bomberos':
            resource_priority.update({'bomberos': 4, 'camion': 4, 'policia': 1, 'same': 1})
        else:
            resource_priority.update({'policia': 2, 'same': 2, 'bomberos': 2})
    else:
        # Fallback: priorizar por código de emergencia si no hay fuerza asignada
        if emergency_code == 'rojo':
            resource_priority = {'same': 4, 'ambulancia': 4, 'policia': 2, 'bomberos': 2}
        elif 'incendio' in emergency_type or 'fuego' in emergency_type:
            resource_priority = {'bomberos': 4, 'camion': 4, 'policia': 1, 'same': 1}
        elif 'robo' in emergency_type or 'violencia' in emergency_type:
            resource_priority = {'policia': 4, 'patrulla': 3, 'same': 1, 'bomberos': 1}
        else:
            resource_priority = {'policia': 2, 'same': 2, 'bomberos': 2}
    
    # Vehículos disponibles (limitados por relevancia) - priorizar fuerza asignada
    print(f"🚗 DEBUG: Buscando vehículos para fuerza asignada: {assigned_force.name if assigned_force else 'NINGUNA'}")

    status_list = ['disponible']
    if assigned_force and assigned_force.name.lower() == 'policía':
        status_list.extend(['en_ruta', 'ocupado'])
        print(f"🔍 DEBUG: Buscando Policía en status: {status_list}")

    vehicle_candidates_primary = []
    vehicle_candidates_secondary = []
    max_vehicle_candidates = getattr(settings, 'ROUTING_VEHICLE_CANDIDATES', 6)

    for vehicle in Vehicle.objects.filter(status__in=status_list).select_related('force'):
        if not (vehicle.current_lat and vehicle.current_lon and vehicle.force):
            continue

        vehicle_type = vehicle.type.lower()
        force_name = vehicle.force.name.lower()
        priority_multiplier = resource_priority.get(force_name, 0) + resource_priority.get(vehicle_type, 0)

        print(f"🔍 DEBUG: Vehículo {vehicle.type} - Fuerza: {force_name}, Status: {vehicle.status}, Prioridad acumulada: {priority_multiplier}")

        if priority_multiplier <= 0:
            print(f"❌ DESCARTADO: {vehicle.type} - {vehicle.force.name} (multiplier: {priority_multiplier})")
            continue

        candidate = {
            'id': f'vehicle_{vehicle.id}',
            'type': vehicle_type,
            'name': f"{vehicle.type} - {vehicle.force.name}",
            'lat': vehicle.current_lat,
            'lon': vehicle.current_lon,
            'resource_type': 'vehicle',
            'resource_obj': vehicle,
            'priority_multiplier': priority_multiplier
        }

        if assigned_force and vehicle.force_id == assigned_force.id:
            vehicle_candidates_primary.append(candidate)
            print(f"✅ AGREGADO (primaria): {vehicle.type} - {vehicle.force.name}")
        else:
            vehicle_candidates_secondary.append(candidate)
            print(f"➕ AGREGADO (secundaria): {vehicle.type} - {vehicle.force.name}")

    # Limitar cantidad manteniendo prioridad
    vehicle_candidates_secondary.sort(key=lambda c: c['priority_multiplier'], reverse=True)

    selected_vehicles = []
    selected_vehicles.extend(vehicle_candidates_primary[:max_vehicle_candidates])

    remaining_slots = max_vehicle_candidates - len(selected_vehicles)
    if remaining_slots > 0:
        selected_vehicles.extend(vehicle_candidates_secondary[:remaining_slots])

    available_resources.extend(selected_vehicles)

    # Agentes disponibles (limitados por relevancia) - priorizar fuerza asignada
    agent_candidates_primary = []
    agent_candidates_secondary = []
    max_agent_candidates = getattr(settings, 'ROUTING_AGENT_CANDIDATES', 4)

    for agent in Agent.objects.filter(status='disponible').select_related('force'):
        if not (agent.lat and agent.lon and agent.force):
            continue

        force_name = agent.force.name.lower()
        priority_multiplier = resource_priority.get(force_name, 0)

        if priority_multiplier <= 0:
            continue

        candidate = {
            'id': f'agent_{agent.id}',
            'type': force_name,
            'name': f"{agent.name} - {agent.force.name}",
            'lat': agent.lat,
            'lon': agent.lon,
            'resource_type': 'agent',
            'resource_obj': agent,
            'priority_multiplier': priority_multiplier
        }

        if assigned_force and agent.force_id == assigned_force.id:
            agent_candidates_primary.append(candidate)
        else:
            agent_candidates_secondary.append(candidate)

    agent_candidates_secondary.sort(key=lambda c: c['priority_multiplier'], reverse=True)

    selected_agents = []
    selected_agents.extend(agent_candidates_primary[:max_agent_candidates])
    remaining_agent_slots = max_agent_candidates - len(selected_agents)
    if remaining_agent_slots > 0:
        selected_agents.extend(agent_candidates_secondary[:remaining_agent_slots])

    available_resources.extend(selected_agents)
    
    # Calcular rutas optimizadas y devolver solo las mejores 5
    assignments = optimizer.find_optimal_assignments(emergency_coords, available_resources)
    
    # Aplicar prioridad adicional basada en el tipo de recurso y fuerza asignada
    for assignment in assignments:
        resource = assignment.get('resource', {})
        multiplier = resource.get('priority_multiplier', 1)
        
        # DEBUG: Agregar información de debug
        resource_obj = resource.get('resource_obj')
        resource_name = resource.get('name', 'Unknown')
        
        # Obtener la fuerza del recurso
        resource_force = None
        if resource_obj and hasattr(resource_obj, 'force') and resource_obj.force:
            resource_force = resource_obj.force.name.lower()
            print(f"🔍 DEBUG: Recurso {resource_name}, Fuerza: {resource_force}")
        elif resource.get('resource_type') == 'agent':
            # Para agentes, el type ya es la fuerza
            resource_force = resource.get('type', '').lower()
            print(f"🔍 DEBUG: Agente {resource_name}, Fuerza: {resource_force}")
        else:
            print(f"🔍 DEBUG: Recurso {resource_name}, SIN FUERZA detectada")
        
        # Si es la fuerza asignada, priorizar por distancia (menor es mejor)
        if assigned_force and resource_force == assigned_force.name.lower():
            assignment['priority_score'] = assignment.get('distance_km', 999)  # Priorizar por distancia
            assignment['is_assigned_force'] = True
            print(f"✅ MATCH: {resource_name} - Fuerza {resource_force} coincide con {assigned_force.name.lower()}")
        else:
            assignment['priority_score'] = assignment.get('priority_score', 999) / max(multiplier, 0.1)
            assignment['is_assigned_force'] = False
            if assigned_force:
                print(f"❌ NO MATCH: {resource_name} - Fuerza {resource_force} NO coincide con {assigned_force.name.lower()}")
            else:
                print(f"⚪ SIN FUERZA ASIGNADA: {resource_name}")
    
    # Reordenar: primero los de fuerza asignada por distancia, luego por score
    max_results = getattr(settings, 'ROUTING_MAX_RESULTS', 6)
    assignments = sorted(assignments, key=lambda x: (
        not x.get('is_assigned_force', False),  # Primero los de fuerza asignada
        x['priority_score']  # Luego por score/distancia
    ))[:max_results]
    
    # Agregar información adicional para debug
    for i, assignment in enumerate(assignments):
        assignment['ranking'] = i + 1
        assignment['selection_reason'] = (
            f"Posición #{i+1}: Tiempo {assignment['estimated_arrival']:.1f}min, "
            f"Distancia {assignment['distance_km']:.1f}km, "
            f"Score final {assignment['priority_score']:.1f}"
        )
    
    print(f"✓ FILTRADO: Devolviendo {len(assignments)} rutas optimizadas para emergencia tipo: {emergency_type}")
    print(f"   Fuerza asignada: {assigned_force.name if assigned_force else 'NINGUNA'}")
    for i, assignment in enumerate(assignments):
        resource = assignment['resource']
        force_match = "✅" if assignment.get('is_assigned_force') else "⚠️" 
        print(f"  #{i+1} {force_match} {resource['name']}: {assignment['estimated_arrival']:.1f}min, {assignment['distance_km']:.1f}km, score={assignment['priority_score']:.1f}")
    
    return assignments

def get_real_time_eta(start_coords: Tuple[float, float], 
                     end_coords: Tuple[float, float]) -> Dict:
    """
    Obtiene ETA en tiempo real para una ruta específica
    """
    optimizer = get_route_optimizer()
    route_info = optimizer.get_best_route(start_coords, end_coords)
    
    return {
        'eta_minutes': route_info['duration'] / 60,
        'distance_km': route_info['distance'] / 1000,
        'route_geometry': route_info['geometry'],
        'provider': route_info['provider']
    }
