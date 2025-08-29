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
        Obtiene ruta usando OSRM - DESHABILITADO para evitar timeouts
        """
        # DESHABILITADO TEMPORALMENTE - causaba timeouts
        logger.info("OSRM deshabilitado para evitar timeouts - usando cálculo directo")
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
        
        # Si todo falla, calcular ruta directa MEJORADA
        distance = self.calculate_distance(start_coords[0], start_coords[1], 
                                         end_coords[0], end_coords[1])
        estimated_duration = (distance / 1000) / 25 * 60 * 60  # 25 km/h promedio en ciudad, resultado en segundos
        
        # Generar ruta con puntos intermedios para mayor realismo
        intermediate_points = self._generate_intermediate_points(
            start_coords[0], start_coords[1], end_coords[0], end_coords[1]
        )
        
        coordinates = [[start_coords[1], start_coords[0]]]  # [lon, lat]
        for point in intermediate_points:
            coordinates.append([point[1], point[0]])  # [lon, lat]
        coordinates.append([end_coords[1], end_coords[0]])
        
        logger.info(f"✓ Ruta directa calculada: {distance/1000:.1f}km en {estimated_duration/60:.1f} min con {len(coordinates)} puntos")
        
        return {
            'provider': 'Direct',
            'route': None,
            'geometry': {
                'type': 'LineString',
                'coordinates': coordinates
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
    
    # Vehículos disponibles (limitados por relevancia) - MÁXIMO 5 para optimizar
    vehicle_count = 0
    print(f"🚗 DEBUG: Buscando vehículos para fuerza asignada: {assigned_force.name if assigned_force else 'NINGUNA'}")
    
    # IMPORTANTE: También buscar vehículos con status 'en_ruta' para emergencias de Policía
    status_list = ['disponible']
    if assigned_force and assigned_force.name.lower() == 'policía':
        status_list.extend(['en_ruta', 'ocupado'])  # Incluir todos los estados para Policía
        print(f"🔍 DEBUG: Buscando Policía en status: {status_list}")
    
    for vehicle in Vehicle.objects.filter(status__in=status_list).select_related('force'):
        if vehicle_count >= 10:  # Aumentar límite para encontrar Policía
            break
            
        if vehicle.current_lat and vehicle.current_lon:
            vehicle_type = vehicle.type.lower()
            force_name = vehicle.force.name.lower() if hasattr(vehicle, 'force') and vehicle.force else 'general'
            
            print(f"🔍 DEBUG: Vehículo {vehicle.type} - Fuerza: {force_name}, Status: {vehicle.status}, Prioridad: {resource_priority.get(force_name, 0)}")
            
            # Solo incluir si es relevante para esta emergencia
            priority_multiplier = resource_priority.get(force_name, 0) + resource_priority.get(vehicle_type, 0)
            if priority_multiplier > 0:
                available_resources.append({
                    'id': f'vehicle_{vehicle.id}',
                    'type': vehicle_type,
                    'name': f"{vehicle.type} - {vehicle.force.name}",
                    'lat': vehicle.current_lat,
                    'lon': vehicle.current_lon,
                    'resource_type': 'vehicle',
                    'resource_obj': vehicle,
                    'priority_multiplier': priority_multiplier
                })
                vehicle_count += 1
                print(f"✅ AGREGADO: {vehicle.type} - {vehicle.force.name} (multiplier: {priority_multiplier})")
            else:
                print(f"❌ DESCARTADO: {vehicle.type} - {vehicle.force.name} (multiplier: {priority_multiplier})")
    
    # Agentes disponibles (limitados por relevancia) - MÁXIMO 5 para optimizar  
    agent_count = 0
    for agent in Agent.objects.filter(status='disponible').select_related('force'):
        if agent_count >= 5:  # Máximo 5 agentes para evitar sobrecarga
            break
            
        if agent.lat and agent.lon:
            force_name = agent.force.name.lower() if hasattr(agent, 'force') and agent.force else 'general'
            
            # Solo incluir si es relevante para esta emergencia
            priority_multiplier = resource_priority.get(force_name, 0)
            if priority_multiplier > 0:
                available_resources.append({
                    'id': f'agent_{agent.id}',
                    'type': force_name,
                    'name': f"{agent.name} - {agent.force.name}",
                    'lat': agent.lat,
                    'lon': agent.lon,
                    'resource_type': 'agent',
                    'resource_obj': agent,
                    'priority_multiplier': priority_multiplier
                })
                agent_count += 1
    
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
    assignments = sorted(assignments, key=lambda x: (
        not x.get('is_assigned_force', False),  # Primero los de fuerza asignada
        x['priority_score']  # Luego por score/distancia
    ))[:3]
    
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
