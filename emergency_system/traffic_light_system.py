#!/usr/bin/env python3
"""
Sistema de Onda Verde para Semáforos - Emergencias Código Rojo
"""

import os
import sys
import django
import math
from datetime import datetime, timedelta

# Configurar Django
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'emergency_app.settings')
django.setup()

from core.models import Emergency, Vehicle, Agent
from django.db import models

class TrafficLightManager:
    """
    Gestor de semáforos para implementar Onda Verde
    """
    
    # Semáforos principales de CABA (coordenadas aproximadas)
    MAJOR_INTERSECTIONS = [
        # Av. 9 de Julio
        {"id": "9julio_corrientes", "name": "9 de Julio y Corrientes", "lat": -34.6037, "lon": -58.3816, "type": "major"},
        {"id": "9julio_santafe", "name": "9 de Julio y Santa Fe", "lat": -34.5945, "lon": -58.3816, "type": "major"},
        {"id": "9julio_rivadavia", "name": "9 de Julio y Rivadavia", "lat": -34.6092, "lon": -58.3816, "type": "major"},
        
        # Av. Corrientes
        {"id": "corrientes_callao", "name": "Corrientes y Callao", "lat": -34.6037, "lon": -58.3915, "type": "major"},
        {"id": "corrientes_pueyrredon", "name": "Corrientes y Pueyrredón", "lat": -34.6037, "lon": -58.4015, "type": "major"},
        {"id": "corrientes_scalabrini", "name": "Corrientes y Scalabrini Ortiz", "lat": -34.6037, "lon": -58.4210, "type": "major"},
        
        # Av. Santa Fe
        {"id": "santafe_callao", "name": "Santa Fe y Callao", "lat": -34.5945, "lon": -58.3915, "type": "major"},
        {"id": "santafe_pueyrredon", "name": "Santa Fe y Pueyrredón", "lat": -34.5945, "lon": -58.4015, "type": "major"},
        {"id": "santafe_scalabrini", "name": "Santa Fe y Scalabrini Ortiz", "lat": -34.5945, "lon": -58.4210, "type": "major"},
        
        # Av. Rivadavia
        {"id": "rivadavia_callao", "name": "Rivadavia y Callao", "lat": -34.6092, "lon": -58.3915, "type": "major"},
        {"id": "rivadavia_pueyrredon", "name": "Rivadavia y Pueyrredón", "lat": -34.6092, "lon": -58.4015, "type": "major"},
        
        # Av. Cabildo
        {"id": "cabildo_juramento", "name": "Cabildo y Juramento", "lat": -34.5632, "lon": -58.4561, "type": "major"},
        {"id": "cabildo_lacroze", "name": "Cabildo y Lacroze", "lat": -34.5589, "lon": -58.4502, "type": "major"},
        
        # Av. Las Heras
        {"id": "lasheras_pueyrredon", "name": "Las Heras y Pueyrredón", "lat": -34.5895, "lon": -58.4015, "type": "major"},
        {"id": "lasheras_scalabrini", "name": "Las Heras y Scalabrini Ortiz", "lat": -34.5895, "lon": -58.4210, "type": "major"},
        
        # Intersecciones secundarias importantes
        {"id": "florida_corrientes", "name": "Florida y Corrientes", "lat": -34.6020, "lon": -58.3748, "type": "secondary"},
        {"id": "defensa_independencia", "name": "Defensa y Independencia", "lat": -34.6178, "lon": -58.3730, "type": "secondary"},
        {"id": "paseo_colon_independencia", "name": "Paseo Colón y Independencia", "lat": -34.6178, "lon": -58.3645, "type": "secondary"}
    ]
    
    def __init__(self):
        self.active_green_waves = {}  # emergency_id -> green_wave_data
        
    def calculate_distance(self, lat1, lon1, lat2, lon2):
        """Calcula distancia entre dos puntos en metros"""
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
    
    def find_intersections_on_route(self, start_lat, start_lon, end_lat, end_lon, max_distance=500):
        """
        Encuentra intersecciones en la ruta entre dos puntos
        max_distance: distancia máxima en metros para considerar una intersección en la ruta
        """
        route_intersections = []
        
        for intersection in self.MAJOR_INTERSECTIONS:
            # Calcular distancia desde el punto de partida a la intersección
            dist_from_start = self.calculate_distance(
                start_lat, start_lon,
                intersection['lat'], intersection['lon']
            )
            
            # Calcular distancia desde la intersección al destino
            dist_to_end = self.calculate_distance(
                intersection['lat'], intersection['lon'],
                end_lat, end_lon
            )
            
            # Distancia directa entre inicio y fin
            direct_distance = self.calculate_distance(start_lat, start_lon, end_lat, end_lon)
            
            # Si la suma de distancias es aproximadamente igual a la distancia directa,
            # la intersección está en la ruta
            route_distance = dist_from_start + dist_to_end
            if abs(route_distance - direct_distance) < max_distance:
                route_intersections.append({
                    'intersection': intersection,
                    'distance_from_start': dist_from_start,
                    'distance_to_end': dist_to_end,
                    'priority': 1 if intersection['type'] == 'major' else 2
                })
        
        # Ordenar por distancia desde el inicio
        return sorted(route_intersections, key=lambda x: x['distance_from_start'])
    
    def calculate_green_wave_timing(self, route_intersections, avg_speed_kmh=50):
        """
        Calcula los tiempos de sincronización para onda verde
        """
        speed_ms = avg_speed_kmh * 1000 / 3600  # Convertir km/h a m/s
        green_wave_timing = []
        
        start_time = datetime.now()
        
        for intersection_data in route_intersections:
            # Tiempo estimado de llegada a la intersección
            distance_m = intersection_data['distance_from_start']
            travel_time_seconds = distance_m / speed_ms
            arrival_time = start_time + timedelta(seconds=travel_time_seconds)
            
            # Duración del verde (más tiempo para intersecciones principales)
            green_duration = 45 if intersection_data['priority'] == 1 else 30
            
            green_wave_timing.append({
                'intersection': intersection_data['intersection'],
                'arrival_time': arrival_time,
                'green_start': arrival_time - timedelta(seconds=5),  # Verde 5s antes
                'green_end': arrival_time + timedelta(seconds=green_duration),
                'priority': intersection_data['priority']
            })
        
        return green_wave_timing
    
    def activate_green_wave(self, emergency_id, vehicle_lat, vehicle_lon, target_lat, target_lon):
        """
        Activa onda verde para una emergencia específica
        """
        # Encontrar intersecciones en la ruta
        route_intersections = self.find_intersections_on_route(
            vehicle_lat, vehicle_lon, target_lat, target_lon
        )
        
        if not route_intersections:
            return {
                'success': False,
                'message': 'No se encontraron intersecciones en la ruta',
                'intersections': []
            }
        
        # Calcular tiempos de onda verde
        green_wave_timing = self.calculate_green_wave_timing(route_intersections)
        
        # Guardar la onda verde activa
        self.active_green_waves[emergency_id] = {
            'created_at': datetime.now(),
            'vehicle_position': (vehicle_lat, vehicle_lon),
            'target_position': (target_lat, target_lon),
            'timing': green_wave_timing,
            'status': 'active'
        }
        
        return {
            'success': True,
            'message': f'Onda Verde activada para {len(green_wave_timing)} intersecciones',
            'intersections': [timing['intersection']['name'] for timing in green_wave_timing],
            'estimated_travel_time': self._calculate_total_travel_time(green_wave_timing),
            'timing': green_wave_timing
        }
    
    def _calculate_total_travel_time(self, green_wave_timing):
        """Calcula tiempo total estimado de viaje"""
        if not green_wave_timing:
            return 0
        
        start_time = green_wave_timing[0]['green_start']
        end_time = green_wave_timing[-1]['green_end']
        return (end_time - start_time).total_seconds()
    
    def get_active_green_waves(self):
        """Retorna todas las ondas verdes activas"""
        current_time = datetime.now()
        active_waves = {}
        
        for emergency_id, wave_data in self.active_green_waves.items():
            # Verificar si la onda verde sigue activa (máximo 30 minutos)
            if (current_time - wave_data['created_at']).total_seconds() < 1800:
                active_waves[emergency_id] = wave_data
            
        # Actualizar diccionario eliminando ondas expiradas
        self.active_green_waves = active_waves
        return active_waves
    
    def deactivate_green_wave(self, emergency_id):
        """Desactiva onda verde para una emergencia específica"""
        if emergency_id in self.active_green_waves:
            del self.active_green_waves[emergency_id]
            return True
        return False
    
    def get_intersection_status(self, intersection_id):
        """Obtiene el estado actual de una intersección"""
        current_time = datetime.now()
        status = {
            'intersection_id': intersection_id,
            'current_time': current_time,
            'is_green': False,
            'emergency_active': False,
            'next_green': None,
            'active_emergencies': []
        }
        
        # Revisar todas las ondas verdes activas
        for emergency_id, wave_data in self.get_active_green_waves().items():
            for timing in wave_data['timing']:
                if timing['intersection']['id'] == intersection_id:
                    status['emergency_active'] = True
                    status['active_emergencies'].append(emergency_id)
                    
                    # Verificar si el semáforo debería estar en verde ahora
                    if timing['green_start'] <= current_time <= timing['green_end']:
                        status['is_green'] = True
                    elif current_time < timing['green_start']:
                        status['next_green'] = timing['green_start']
        
        return status

# Instancia global del gestor
traffic_manager = TrafficLightManager()

def activate_emergency_green_wave(emergency):
    """
    Función para activar onda verde para una emergencia código rojo
    """
    if emergency.code != 'rojo':
        return {
            'success': False,
            'message': 'Onda Verde solo disponible para emergencias código ROJO'
        }
    
    if not (emergency.location_lat and emergency.location_lon):
        return {
            'success': False,
            'message': 'Emergencia sin coordenadas válidas'
        }
    
    results = []
    
    # Activar onda verde para todos los vehículos asignados
    if emergency.assigned_vehicle:
        vehicle = emergency.assigned_vehicle
        if vehicle.current_lat and vehicle.current_lon:
            result = traffic_manager.activate_green_wave(
                f"emergency_{emergency.id}_vehicle_{vehicle.id}",
                vehicle.current_lat,
                vehicle.current_lon,
                emergency.location_lat,
                emergency.location_lon
            )
            results.append({
                'resource': f"Vehículo: {vehicle.type}",
                'result': result
            })
    
    # Activar para vehículos en despachos múltiples
    for dispatch in emergency.dispatches.all():
        if dispatch.vehicle and dispatch.vehicle.current_lat and dispatch.vehicle.current_lon:
            vehicle = dispatch.vehicle
            result = traffic_manager.activate_green_wave(
                f"emergency_{emergency.id}_dispatch_{dispatch.id}",
                vehicle.current_lat,
                vehicle.current_lon,
                emergency.location_lat,
                emergency.location_lon
            )
            results.append({
                'resource': f"Despacho: {vehicle.type} ({dispatch.force.name})",
                'result': result
            })
    
    return {
        'success': len(results) > 0,
        'message': f'Onda Verde procesada para {len(results)} recursos',
        'results': results,
        'total_intersections': sum(len(r['result'].get('intersections', [])) for r in results if r['result']['success'])
    }

if __name__ == '__main__':
    print("🚦 SISTEMA DE ONDA VERDE - SEMÁFOROS CABA")
    print("=" * 60)
    
    # Buscar emergencias código rojo activas
    red_emergencies = Emergency.objects.filter(
        code='rojo',
        status__in=['pendiente', 'asignada']
    )
    
    print(f"🚨 Emergencias código ROJO activas: {red_emergencies.count()}")
    
    for emergency in red_emergencies:
        print(f"\n📍 Procesando Emergencia #{emergency.id}:")
        print(f"   Descripción: {emergency.description[:50]}...")
        
        result = activate_emergency_green_wave(emergency)
        
        if result['success']:
            print(f"   ✅ {result['message']}")
            print(f"   🚦 Total intersecciones: {result['total_intersections']}")
            
            for resource_result in result['results']:
                if resource_result['result']['success']:
                    print(f"      - {resource_result['resource']}: {len(resource_result['result']['intersections'])} intersecciones")
                else:
                    print(f"      - {resource_result['resource']}: {resource_result['result']['message']}")
        else:
            print(f"   ❌ {result['message']}")
    
    # Mostrar estado actual del sistema
    active_waves = traffic_manager.get_active_green_waves()
    print(f"\n🟢 Ondas verdes activas: {len(active_waves)}")
    
    for wave_id, wave_data in active_waves.items():
        intersections_count = len(wave_data['timing'])
        print(f"   - {wave_id}: {intersections_count} intersecciones sincronizadas")
    
    print("\n=" * 60)
    print("✅ Sistema de Onda Verde configurado!")
    print("🚦 Los semáforos se sincronizarán automáticamente para emergencias código ROJO")
