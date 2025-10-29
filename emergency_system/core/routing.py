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
import os
from typing import List, Dict, Tuple, Optional
import logging
from django.utils import timezone
from django.db import models

from .models import StreetClosure  # Importar modelo de cierres de calles

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
        # modo offline: evita llamadas externas (útil para populate / tests sin API keys)
        setting_offline = bool(getattr(settings, 'ROUTING_OFFLINE', False)) or bool(getattr(settings, 'FORCE_ROUTING_OFFLINE', False))
        # Leer variable de entorno como respaldo (permitir que run_system.bat active el modo offline)
        env_val = os.environ.get('ROUTING_OFFLINE') or os.environ.get('FORCE_ROUTING_OFFLINE')
        env_offline = False
        if isinstance(env_val, str) and env_val.strip() != '':
            env_offline = env_val.strip().lower() in ('1', 'true', 'yes', 'on')
        elif isinstance(env_val, (int, bool)):
            env_offline = bool(env_val)

        self.offline_mode = setting_offline or env_offline
        if self.offline_mode:
            logger.info("ROUTING_OFFLINE habilitado (setting or env) — llamadas a proveedores externos evitadas")

    def get_active_street_closures(self) -> List[Dict]:
        """
        Obtiene cortes de calles activos desde la base de datos
        """
        from .models import StreetClosure  # Import aquí para evitar circular imports

        active_closures = StreetClosure.objects.filter(
            is_active=True,
            start_date__lte=timezone.now()
        ).filter(
            models.Q(end_date__isnull=True) | models.Q(end_date__gte=timezone.now())
        ).values('id', 'name', 'lat', 'lon', 'closure_type', 'geometry', 'affected_streets')

        return list(active_closures)

    def route_intersects_closure(self, route_geometry: Dict, closure: Dict) -> bool:
        """
        Verifica si una ruta intersecta con un corte de calle
        """
        if not route_geometry or route_geometry.get('type') != 'LineString':
            return False

        route_coords = route_geometry.get('coordinates', [])

        # Si el corte tiene geometría compleja, verificar intersección
        if closure.get('geometry'):
            return self._geometries_intersect(route_geometry, closure['geometry'])

        # Si solo tiene punto central, verificar proximidad
        closure_lat = closure.get('lat')
        closure_lon = closure.get('lon')

        if not (closure_lat and closure_lon):
            return False

        # Verificar si algún punto de la ruta está cerca del corte (dentro de 50m)
        for coord in route_coords:
            if len(coord) >= 2:
                route_lon, route_lat = coord[0], coord[1]
                distance = self.calculate_distance(route_lat, route_lon, closure_lat, closure_lon)
                if distance <= 50:  # 50 metros de proximidad
                    return True

        return False

    def _geometries_intersect(self, geom1: Dict, geom2: Dict) -> bool:
        """
        Verifica si dos geometrías GeoJSON se intersectan
        Implementación simplificada para casos básicos
        """
        # Para una implementación completa necesitaríamos una librería como Shapely
        # Por ahora, verificamos proximidad de puntos
        if geom1.get('type') == 'LineString' and geom2.get('type') == 'Point':
            point_coords = geom2.get('coordinates', [])
            if len(point_coords) >= 2:
                point_lon, point_lat = point_coords[0], point_coords[1]

                for coord in geom1.get('coordinates', []):
                    if len(coord) >= 2:
                        line_lon, line_lat = coord[0], coord[1]
                        distance = self.calculate_distance(line_lat, line_lon, point_lat, point_lon)
                        if distance <= 50:  # 50 metros
                            return True

        elif geom1.get('type') == 'LineString' and geom2.get('type') == 'LineString':
            # Verificar si las líneas están cerca
            for coord1 in geom1.get('coordinates', []):
                if len(coord1) >= 2:
                    for coord2 in geom2.get('coordinates', []):
                        if len(coord2) >= 2:
                            distance = self.calculate_distance(
                                coord1[1], coord1[0], coord2[1], coord2[0]
                            )
                            if distance <= 50:  # 50 metros
                                return True

        return False

    def adjust_route_for_closures(self, route_info: Dict, start_coords: Tuple[float, float],
                                end_coords: Tuple[float, float]) -> Dict:
        """
        Ajusta una ruta para evitar cortes de calles activos
        """
        active_closures = self.get_active_street_closures()

        if not active_closures:
            return route_info

        # Verificar si la ruta intersecta con algún corte
        intersects_any = False
        intersecting_closures = []

        for closure in active_closures:
            if self.route_intersects_closure(route_info.get('geometry'), closure):
                intersects_any = True
                intersecting_closures.append(closure)
                logger.warning(f"🚫 Ruta intersecta con corte de calle: {closure['name']}")

        if not intersects_any:
            return route_info

        # Si intersecta, intentar encontrar ruta alternativa
        logger.info(f"🔄 Intentando recalcular ruta para evitar {len(intersecting_closures)} cortes de calle")

        # Intentar con diferentes proveedores o configuraciones
        alternative_routes = []

        # 1. Intentar con OSRM si no se usó antes
        if route_info.get('provider') != 'OSRM':
            alt_route = self.get_route_osrm(start_coords, end_coords)
            if alt_route and alt_route.get('routes'):
                alt_route_info = {
                    'provider': 'OSRM',
                    'route': alt_route['routes'][0],
                    'geometry': alt_route['routes'][0].get('geometry'),
                    'distance': alt_route['routes'][0].get('distance'),
                    'duration': alt_route['routes'][0].get('duration'),
                    'steps': alt_route['routes'][0].get('legs', [{}])[0].get('steps', [])
                }
                if alt_route_info['geometry']:
                    alternative_routes.append(alt_route_info)

        # 2. Intentar con GraphHopper si está disponible
        if self.graphhopper_key and route_info.get('provider') != 'GraphHopper':
            alt_route = self.get_route_graphhopper(start_coords, end_coords)
            if alt_route and alt_route.get('paths'):
                path = alt_route['paths'][0]
                geo = path.get('points')
                if geo and geo.get('type') == 'LineString':
                    alt_route_info = {
                        'provider': 'GraphHopper',
                        'route': path,
                        'geometry': geo,
                        'distance': path.get('distance'),
                        'duration': path.get('time')/1000.0 if path.get('time') else None,
                        'steps': path.get('instructions', [])
                    }
                    alternative_routes.append(alt_route_info)

        # 3. Generar ruta alternativa con grid path modificado
        alt_grid_coords = self._generate_alternative_grid_path(start_coords, end_coords, intersecting_closures)
        alt_distance = self.calculate_distance(start_coords[0], start_coords[1], end_coords[0], end_coords[1])
        alt_duration = (alt_distance / 1000) / 20 * 60 * 60  # Velocidad más conservadora para ruta alternativa

        alt_route_info = {
            'provider': 'AlternativeGrid',
            'route': None,
            'geometry': {
                'type': 'LineString',
                'coordinates': [[c[1], c[0]] for c in alt_grid_coords]  # lon, lat
            },
            'distance': alt_distance,
            'duration': alt_duration,
            'steps': [],
            'avoided_closures': len(intersecting_closures)
        }
        alternative_routes.append(alt_route_info)

        # Encontrar la mejor ruta alternativa que no intersecte con cortes
        for alt_route in alternative_routes:
            intersects_alt = False
            for closure in intersecting_closures:
                if self.route_intersects_closure(alt_route.get('geometry'), closure):
                    intersects_alt = True
                    break

            if not intersects_alt:
                logger.info(f"✅ Ruta alternativa encontrada con {alt_route['provider']} - evita {len(intersecting_closures)} cortes")
                alt_route['closures_avoided'] = intersecting_closures
                return alt_route

        # Si ninguna ruta alternativa funciona, devolver la original con advertencia
        logger.warning(f"⚠️ No se pudo encontrar ruta alternativa que evite todos los cortes. Usando ruta original.")
        route_info['closures_warning'] = intersecting_closures
        route_info['intersects_closures'] = True
        return route_info

    def get_traffic_congestion_factor(self, route_geometry: Dict, timestamp: Optional[float] = None) -> float:
        """
        Calcula un factor de congestión para una ruta basado en datos de tránsito
        Retorna un multiplicador para el tiempo de viaje (1.0 = normal, >1.0 = más lento)
        """
        from .models import TrafficCount  # Import aquí para evitar circular imports

        if not route_geometry or route_geometry.get('type') != 'LineString':
            return 1.0

        route_coords = route_geometry.get('coordinates', [])
        if len(route_coords) < 2:
            return 1.0

        # Usar timestamp actual si no se proporciona
        if timestamp is None:
            timestamp = time.time()

        # Convertir a datetime aware
        query_time = timezone.now()

        # Buscar datos de tránsito en las últimas 2 horas
        time_window_start = query_time - timezone.timedelta(hours=2)

        # Obtener puntos de muestreo a lo largo de la ruta (cada 500m aproximadamente)
        sample_points = self._get_route_sample_points(route_coords, interval_meters=500)

        congestion_factors = []

        for point in sample_points:
            lat, lon = point

            # Buscar conteos de tránsito cercanos (dentro de 200m)
            # En PostgreSQL, no podemos usar la columna calculada en WHERE, así que calculamos distancia completa en WHERE
            nearby_counts = TrafficCount.objects.filter(
                timestamp__gte=time_window_start,
                timestamp__lte=query_time
            ).extra(
                select={'distance': '6371000 * 2 * ASIN(SQRT(POWER(SIN((%s - lat) * PI() / 360), 2) + COS(%s * PI() / 180) * COS(lat * PI() / 180) * POWER(SIN((%s - lon) * PI() / 360), 2)))'},
                select_params=[lat, lat, lon],
                where=['6371000 * 2 * ASIN(SQRT(POWER(SIN((%s - lat) * PI() / 360), 2) + COS(%s * PI() / 180) * COS(lat * PI() / 180) * POWER(SIN((%s - lon) * PI() / 360), 2))) <= 200'],
                params=[lat, lat, lon]
            ).order_by('distance', '-timestamp')[:5]  # Top 5 más cercanos y recientes

            if nearby_counts:
                # Calcular factor de congestión basado en los conteos
                total_weight = 0
                weighted_factor = 0

                for count in nearby_counts:
                    # Peso basado en proximidad (inversamente proporcional a la distancia)
                    distance = getattr(count, 'distance', 100)
                    weight = max(0.1, 1.0 / (1.0 + distance/100))  # Peso entre 0.1 y 1.0

                    # Factor basado en el tipo de conteo
                    factor = self._traffic_count_to_congestion_factor(count)
                    if factor > 1.0:
                        weighted_factor += factor * weight
                        total_weight += weight

                if total_weight > 0:
                    avg_factor = weighted_factor / total_weight
                    congestion_factors.append(avg_factor)

        if congestion_factors:
            # Usar el factor de congestión más alto encontrado en la ruta
            max_congestion = max(congestion_factors)
            logger.debug(f"🚦 Factor de congestión detectado: {max_congestion:.2f}")
            return max_congestion

        return 1.0  # Sin datos de congestión = factor normal

    def _get_route_sample_points(self, route_coords: List[List[float]], interval_meters: float = 500) -> List[Tuple[float, float]]:
        """
        Obtiene puntos de muestreo a lo largo de la ruta para consultar congestión
        """
        if len(route_coords) < 2:
            return []

        sample_points = []
        total_distance = 0
        current_point = (route_coords[0][1], route_coords[0][0])  # lat, lon

        for i in range(1, len(route_coords)):
            next_point = (route_coords[i][1], route_coords[i][0])  # lat, lon
            segment_distance = self.calculate_distance(
                current_point[0], current_point[1],
                next_point[0], next_point[1]
            )

            # Agregar puntos de muestreo a lo largo del segmento
            while total_distance + segment_distance >= interval_meters:
                # Calcular punto intermedio
                ratio = (interval_meters - total_distance) / segment_distance
                mid_lat = current_point[0] + (next_point[0] - current_point[0]) * ratio
                mid_lon = current_point[1] + (next_point[1] - current_point[1]) * ratio

                sample_points.append((mid_lat, mid_lon))

                total_distance = 0
                current_point = (mid_lat, mid_lon)
                segment_distance = self.calculate_distance(
                    current_point[0], current_point[1],
                    next_point[0], next_point[1]
                )

            total_distance += segment_distance
            current_point = next_point

        # Agregar punto final si no se agregó
        if route_coords:
            final_coord = route_coords[-1]
            if final_coord and len(final_coord) >= 2:
                sample_points.append((final_coord[1], final_coord[0]))

        return sample_points

    def _traffic_count_to_congestion_factor(self, traffic_count) -> float:
        """
        Convierte un conteo de tránsito en un factor de congestión
        """
        count_value = traffic_count.count_value
        count_type = traffic_count.count_type
        unit = traffic_count.unit

        if count_type == 'vehicle':
            # Para conteos de vehículos, asumir que > 1000 veh/h = congestión alta
            if unit == 'vehicles' and count_value > 1000:
                # Factor basado en intensidad del tráfico
                if count_value > 2000:
                    return 1.8  # Muy congestionado
                elif count_value > 1500:
                    return 1.5  # Congestionado
                else:
                    return 1.2  # Moderadamente congestionado

        elif count_type == 'speed':
            # Para mediciones de velocidad, velocidades bajas = más congestión
            if unit == 'km/h' or unit == 'kph':
                if count_value < 10:
                    return 2.0  # Casi parado
                elif count_value < 20:
                    return 1.6  # Muy lento
                elif count_value < 30:
                    return 1.3  # Lento
                elif count_value < 40:
                    return 1.1  # Moderadamente lento

        elif count_type == 'occupancy':
            # Para ocupación de vía (porcentaje)
            if unit == 'percentage' or '%' in unit:
                if count_value > 90:
                    return 2.0  # Vía casi llena
                elif count_value > 70:
                    return 1.5  # Muy ocupada
                elif count_value > 50:
                    return 1.2  # Moderadamente ocupada

        return 1.0  # Sin congestión significativa

    def adjust_duration_for_traffic(self, route_info: Dict) -> Dict:
        """
        Ajusta la duración estimada de una ruta basado en datos de tránsito
        """
        if not route_info.get('geometry') or not route_info.get('duration'):
            return route_info

        congestion_factor = self.get_traffic_congestion_factor(route_info['geometry'])

        if congestion_factor > 1.0:
            original_duration = route_info['duration']
            adjusted_duration = original_duration * congestion_factor

            logger.info(f"🚦 Ajustando duración por congestión: {original_duration/60:.1f}min → {adjusted_duration/60:.1f}min (factor: {congestion_factor:.2f})")

            route_info['original_duration'] = original_duration
            route_info['duration'] = adjusted_duration
            route_info['congestion_factor'] = congestion_factor
            route_info['traffic_adjusted'] = True

        return route_info

    def calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Calcula la distancia en metros entre dos puntos usando la fórmula de Haversine
        """
        from math import radians, sin, cos, sqrt, atan2

        # Convertir a radianes
        lat1_rad, lon1_rad = radians(lat1), radians(lon1)
        lat2_rad, lon2_rad = radians(lat2), radians(lon2)

        # Diferencias
        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad

        # Fórmula de Haversine
        a = sin(dlat/2)**2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))

        # Radio de la Tierra en metros
        R = 6371000

        return R * c

    def get_route_openroute(self, start_coords: Tuple[float, float], 
                           end_coords: Tuple[float, float], 
                           profile: str = 'driving-car') -> Optional[Dict]:
        """
        Obtiene ruta usando OpenRouteService API
        """
        # Si estamos en modo offline no llamamos a la API
        if self.offline_mode:
            logger.info("ROUTING_OFFLINE activo: evitando llamada a OpenRouteService")
            return None

        if not self.openroute_key:
            # No advertir si estamos en modo offline: es esperado no tener keys
            if not getattr(self, 'offline_mode', False):
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
        if self.offline_mode:
            logger.info("ROUTING_OFFLINE activo: evitando llamada a Mapbox")
            return None

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
        # Si estamos en modo offline, no intentamos hosts externos
        if self.offline_mode:
            logger.info("ROUTING_OFFLINE activo: evitando llamadas a hosts OSRM públicos")
            return None

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
        if self.offline_mode:
            logger.info("ROUTING_OFFLINE activo: evitando llamada a GraphHopper")
            return None

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
                    # Verificar y ajustar por cortes de calles
                    result = self.adjust_route_for_closures(result, start_coords, end_coords)
                    # Ajustar por condiciones de tránsito
                    result = self.adjust_duration_for_traffic(result)
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
            # Verificar y ajustar por cortes de calles
            result = self.adjust_route_for_closures(result, start_coords, end_coords)
            # Ajustar por condiciones de tránsito
            result = self.adjust_duration_for_traffic(result)
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
                # Verificar y ajustar por cortes de calles
                result = self.adjust_route_for_closures(result, start_coords, end_coords)
                # Ajustar por condiciones de tránsito
                result = self.adjust_duration_for_traffic(result)
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
                # Verificar y ajustar por cortes de calles
                result = self.adjust_route_for_closures(result, start_coords, end_coords)
                # Ajustar por condiciones de tránsito
                result = self.adjust_duration_for_traffic(result)
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
        # Verificar y ajustar por cortes de calles incluso en fallback
        result = self.adjust_route_for_closures(result, start_coords, end_coords)
        # Ajustar por condiciones de tránsito
        result = self.adjust_duration_for_traffic(result)
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

    def find_emergency_parking(self, location_coords: Tuple[float, float], 
                             max_distance_meters: float = 500,
                             min_spaces_required: int = 1) -> List[Dict]:
        """
        Encuentra lugares de estacionamiento disponibles para emergencias cerca de una ubicación
        """
        from .models import ParkingSpot  # Import aquí para evitar circular imports

        lat, lon = location_coords

        # Buscar estacionamientos disponibles dentro del radio especificado
        available_parking = ParkingSpot.objects.filter(
            is_active=True,
            available_spaces__gte=min_spaces_required
        ).extra(
            select={'distance': '6371000 * 2 * ASIN(SQRT(POWER(SIN((%s - lat) * PI() / 360), 2) + COS(%s * PI() / 180) * COS(lat * PI() / 180) * POWER(SIN((%s - lon) * PI() / 360), 2)))'},
            select_params=[lat, lat, lon],
            where=[f'distance <= {max_distance_meters}']
        ).order_by('distance')[:10]  # Top 10 más cercanos

        parking_options = []
        for spot in available_parking:
            distance = getattr(spot, 'distance', 0)
            walking_time_minutes = (distance / 1000) / 5 * 60  # Asumiendo 5 km/h de caminata

            parking_options.append({
                'id': spot.external_id,
                'name': spot.name,
                'address': spot.address,
                'lat': spot.lat,
                'lon': spot.lon,
                'distance_meters': distance,
                'walking_time_minutes': walking_time_minutes,
                'total_spaces': spot.total_spaces,
                'available_spaces': spot.available_spaces,
                'spot_type': spot.spot_type,
                'is_paid': spot.is_paid,
                'max_duration_hours': spot.max_duration_hours,
                'occupancy_rate': spot.occupancy_rate,
            })

        logger.info(f"🏪 Encontrados {len(parking_options)} lugares de estacionamiento disponibles dentro de {max_distance_meters}m")
        return parking_options

    def find_parking_route(self, vehicle_coords: Tuple[float, float], 
                          parking_coords: Tuple[float, float],
                          emergency_coords: Tuple[float, float]) -> Dict:
        """
        Calcula ruta desde vehículo hasta estacionamiento y luego a la emergencia
        """
        # Ruta vehículo -> estacionamiento
        parking_route = self.get_best_route(vehicle_coords, parking_coords)

        # Ruta estacionamiento -> emergencia (a pie)
        walking_distance = self.calculate_distance(
            parking_coords[0], parking_coords[1],
            emergency_coords[0], emergency_coords[1]
        )
        walking_time = (walking_distance / 1000) / 5 * 60 * 60  # 5 km/h = tiempo en segundos

        return {
            'driving_route': parking_route,
            'walking_distance_meters': walking_distance,
            'walking_time_seconds': walking_time,
            'total_eta_seconds': parking_route['duration'] + walking_time,
            'parking_coords': parking_coords,
            'emergency_coords': emergency_coords,
        }

    def get_emergency_parking_plan(self, vehicle_coords: Tuple[float, float],
                                 emergency_coords: Tuple[float, float],
                                 max_parking_distance: float = 300) -> Dict:
        """
        Crea un plan completo de estacionamiento para una emergencia
        """
        # Encontrar opciones de estacionamiento
        parking_options = self.find_emergency_parking(
            emergency_coords, 
            max_distance_meters=max_parking_distance
        )

        if not parking_options:
            return {
                'success': False,
                'message': f'No se encontraron lugares de estacionamiento disponibles dentro de {max_parking_distance}m',
                'parking_options': [],
                'recommended_plan': None
            }

        # Evaluar cada opción de estacionamiento
        evaluated_options = []
        for parking in parking_options:
            parking_coords = (parking['lat'], parking['lon'])

            # Calcular ruta completa
            route_plan = self.find_parking_route(vehicle_coords, parking_coords, emergency_coords)

            # Calcular score (menor tiempo total = mejor)
            total_time = route_plan['total_eta_seconds']
            distance_penalty = parking['distance_meters'] / 100  # Penalización por distancia
            score = total_time + distance_penalty

            evaluated_options.append({
                'parking_info': parking,
                'route_plan': route_plan,
                'total_eta_minutes': total_time / 60,
                'score': score,
            })

        # Ordenar por score (menor = mejor)
        evaluated_options.sort(key=lambda x: x['score'])

        best_option = evaluated_options[0] if evaluated_options else None

        return {
            'success': True,
            'parking_options': evaluated_options,
            'recommended_plan': best_option,
            'total_options': len(evaluated_options)
        }
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
        'provider': route_info['provider'],
        'closures_warning': route_info.get('closures_warning'),
        'intersects_closures': route_info.get('intersects_closures', False),
        'congestion_factor': route_info.get('congestion_factor', 1.0),
        'traffic_adjusted': route_info.get('traffic_adjusted', False),
        'closures_avoided': route_info.get('closures_avoided', 0),
    }
