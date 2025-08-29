"""
Sistema de ruteo y optimización de rutas para emergencias
"""

import requests
import json
import math
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
            else:
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
        Obtiene ruta usando OSRM (Open Source Routing Machine) - servicio gratuito
        """
        url = f"http://router.project-osrm.org/route/v1/driving/{start_coords[1]},{start_coords[0]};{end_coords[1]},{end_coords[0]}"
        
        params = {
            'overview': 'full',
            'geometries': 'geojson',
            'steps': 'true'
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"OSRM API error: {response.status_code}")
                return None
        except requests.RequestException as e:
            logger.error(f"Error conectando con OSRM API: {e}")
            return None

    def get_best_route(self, start_coords: Tuple[float, float], 
                      end_coords: Tuple[float, float]) -> Dict:
        """
        Obtiene la mejor ruta disponible probando múltiples APIs
        """
        # Intentar OSRM primero (gratuito)
        route = self.get_route_osrm(start_coords, end_coords)
        if route and 'routes' in route and route['routes']:
            return {
                'provider': 'OSRM',
                'route': route['routes'][0],
                'geometry': route['routes'][0]['geometry'],
                'distance': route['routes'][0]['distance'],
                'duration': route['routes'][0]['duration'],
                'steps': route['routes'][0].get('legs', [{}])[0].get('steps', [])
            }
        
        # Intentar OpenRoute como backup
        route = self.get_route_openroute(start_coords, end_coords)
        if route and 'features' in route and route['features']:
            feature = route['features'][0]
            return {
                'provider': 'OpenRoute',
                'route': feature,
                'geometry': feature['geometry'],
                'distance': feature['properties']['segments'][0]['distance'],
                'duration': feature['properties']['segments'][0]['duration'],
                'steps': feature['properties']['segments'][0].get('steps', [])
            }
        
        # Si todo falla, calcular ruta directa
        distance = self.calculate_distance(start_coords[0], start_coords[1], 
                                         end_coords[0], end_coords[1])
        estimated_duration = distance / 50 * 3.6  # Asumiendo 50 km/h promedio
        
        return {
            'provider': 'Direct',
            'route': None,
            'geometry': {
                'type': 'LineString',
                'coordinates': [
                    [start_coords[1], start_coords[0]],
                    [end_coords[1], end_coords[0]]
                ]
            },
            'distance': distance,
            'duration': estimated_duration,
            'steps': []
        }

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

def get_route_optimizer():
    """Factory function para obtener instancia del optimizador"""
    return RouteOptimizer()

# Funciones de utilidad para las vistas
def calculate_emergency_routes(emergency):
    """
    Calcula rutas optimizadas para una emergencia específica
    """
    from .models import Vehicle, Agent  # Import aquí para evitar circular imports
    
    if not (emergency.location_lat and emergency.location_lon):
        return []
    
    optimizer = get_route_optimizer()
    emergency_coords = (emergency.location_lat, emergency.location_lon)
    
    # Obtener recursos disponibles
    available_resources = []
    
    # Vehículos disponibles
    for vehicle in Vehicle.objects.filter(status='disponible').select_related('force'):
        if vehicle.current_lat and vehicle.current_lon:
            available_resources.append({
                'id': f'vehicle_{vehicle.id}',
                'type': vehicle.type.lower(),
                'name': f"{vehicle.type} - {vehicle.force.name}",
                'lat': vehicle.current_lat,
                'lon': vehicle.current_lon,
                'resource_type': 'vehicle',
                'resource_obj': vehicle
            })
    
    # Agentes disponibles
    for agent in Agent.objects.filter(status='disponible').select_related('force'):
        if agent.lat and agent.lon:
            available_resources.append({
                'id': f'agent_{agent.id}',
                'type': agent.force.name.lower(),
                'name': f"{agent.name} - {agent.force.name}",
                'lat': agent.lat,
                'lon': agent.lon,
                'resource_type': 'agent',
                'resource_obj': agent
            })
    
    # Calcular rutas optimizadas
    return optimizer.find_optimal_assignments(emergency_coords, available_resources)

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
