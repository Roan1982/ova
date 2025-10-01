"""
Cliente para consumir la API de Transporte de Buenos Aires
https://api-transporte.buenosaires.gob.ar/console
"""

import requests
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from django.conf import settings
from django.utils import timezone
from .models import StreetClosure, ParkingSpot, TrafficCount, TransportAlert

logger = logging.getLogger(__name__)

class BuenosAiresTransportClient:
    """
    Cliente para consumir la API de Transporte de Buenos Aires
    """

    BASE_URL = "https://api-transporte.buenosaires.gob.ar"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'EmergencySystem/1.0',
            'Accept': 'application/json'
        })

    def _make_request(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """
        Realiza una petición HTTP a la API
        """
        url = f"{self.BASE_URL}{endpoint}"

        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()

            # La API parece devolver datos en diferentes formatos
            # Intentamos parsear como JSON primero
            try:
                return response.json()
            except json.JSONDecodeError:
                logger.warning(f"Respuesta no es JSON válido para {endpoint}")
                return None

        except requests.RequestException as e:
            logger.error(f"Error al consumir API de Transporte: {e}")
            return None

    def get_street_closures(self) -> List[Dict]:
        """
        Obtiene cortes de calles desde /transito endpoint
        """
        logger.info("Obteniendo cortes de calles...")

        # La API tiene un endpoint /transito que incluye cortes
        data = self._make_request("/transito")

        if not data:
            return []

        closures = []

        # Procesar la respuesta - asumiendo que viene en formato GeoJSON o similar
        # Esto puede necesitar ajustes basados en la estructura real de la API
        features = data.get('features', [])

        for feature in features:
            properties = feature.get('properties', {})
            geometry = feature.get('geometry', {})

            # Solo procesar si es un corte de calle
            if properties.get('tipo') == 'corte_calle' or 'corte' in str(properties).lower():
                closure_data = {
                    'external_id': properties.get('id', f"corte_{len(closures)}"),
                    'name': properties.get('nombre', properties.get('descripcion', 'Corte sin nombre')),
                    'description': properties.get('descripcion', ''),
                    'closure_type': self._map_closure_type(properties.get('tipo_corte', 'total')),
                    'lat': geometry.get('coordinates', [None, None])[1] if geometry.get('coordinates') else None,
                    'lon': geometry.get('coordinates', [None, None])[0] if geometry.get('coordinates') else None,
                    'address': properties.get('direccion', ''),
                    'geometry': geometry,
                    'start_date': self._parse_datetime(properties.get('fecha_inicio')),
                    'end_date': self._parse_datetime(properties.get('fecha_fin')),
                    'cause': properties.get('causa', ''),
                    'affected_streets': properties.get('calles_afectadas', []),
                }

                if closure_data['lat'] and closure_data['lon']:
                    closures.append(closure_data)

        logger.info(f"Obtenidos {len(closures)} cortes de calles")
        return closures

    def get_parking_data(self) -> List[Dict]:
        """
        Obtiene datos de estacionamiento desde /estacionamiento endpoint
        """
        logger.info("Obteniendo datos de estacionamiento...")

        data = self._make_request("/estacionamiento")

        if not data:
            return []

        parking_spots = []

        # Procesar respuesta de estacionamiento
        features = data.get('features', [])

        for feature in features:
            properties = feature.get('properties', {})
            geometry = feature.get('geometry', {})

            parking_data = {
                'external_id': properties.get('id', f"parking_{len(parking_spots)}"),
                'name': properties.get('nombre', properties.get('direccion', 'Estacionamiento sin nombre')),
                'spot_type': self._map_parking_type(properties.get('tipo', 'street')),
                'lat': geometry.get('coordinates', [None, None])[1] if geometry.get('coordinates') else None,
                'lon': geometry.get('coordinates', [None, None])[0] if geometry.get('coordinates') else None,
                'address': properties.get('direccion', ''),
                'total_spaces': properties.get('capacidad', 1),
                'available_spaces': properties.get('disponibles', 0),
                'is_paid': properties.get('pago', False),
                'max_duration_hours': properties.get('duracion_maxima'),
                'restrictions': properties.get('restricciones', {}),
            }

            if parking_data['lat'] and parking_data['lon']:
                parking_spots.append(parking_data)

        logger.info(f"Obtenidos {len(parking_spots)} lugares de estacionamiento")
        return parking_spots

    def get_traffic_counts(self) -> List[Dict]:
        """
        Obtiene conteos de tránsito desde /transito endpoint
        """
        logger.info("Obteniendo conteos de tránsito...")

        # Los conteos pueden venir del endpoint /transito o específico
        data = self._make_request("/transito")

        if not data:
            return []

        traffic_counts = []

        # Procesar datos de tránsito
        features = data.get('features', [])

        for feature in features:
            properties = feature.get('properties', {})
            geometry = feature.get('geometry', {})

            # Buscar datos de conteo
            if 'conteo' in str(properties).lower() or 'transito' in str(properties).lower():
                count_data = {
                    'external_id': properties.get('id', f"traffic_{len(traffic_counts)}"),
                    'location_name': properties.get('ubicacion', properties.get('nombre', 'Sin ubicación')),
                    'count_type': self._map_count_type(properties.get('tipo_conteo', 'vehicle')),
                    'lat': geometry.get('coordinates', [None, None])[1] if geometry.get('coordinates') else None,
                    'lon': geometry.get('coordinates', [None, None])[0] if geometry.get('coordinates') else None,
                    'street_name': properties.get('calle', ''),
                    'count_value': properties.get('valor', properties.get('conteo', 0)),
                    'unit': properties.get('unidad', 'vehicles'),
                    'timestamp': self._parse_datetime(properties.get('timestamp', properties.get('fecha'))),
                    'period_minutes': properties.get('periodo_minutos', 60),
                    'data_source': 'api-transporte-bsas',
                }

                if count_data['lat'] and count_data['lon'] and count_data['timestamp']:
                    traffic_counts.append(count_data)

        logger.info(f"Obtenidos {len(traffic_counts)} conteos de tránsito")
        return traffic_counts

    def get_transport_alerts(self) -> List[Dict]:
        """
        Obtiene alertas de transporte
        """
        logger.info("Obteniendo alertas de transporte...")

        # Las alertas pueden venir del endpoint /transito
        data = self._make_request("/transito")

        if not data:
            return []

        alerts = []

        features = data.get('features', [])

        for feature in features:
            properties = feature.get('properties', {})

            # Buscar alertas
            if properties.get('tipo') == 'alerta' or 'alerta' in str(properties).lower():
                alert_data = {
                    'external_id': properties.get('id', f"alert_{len(alerts)}"),
                    'title': properties.get('titulo', properties.get('nombre', 'Alerta sin título')),
                    'description': properties.get('descripcion', ''),
                    'alert_type': self._map_alert_type(properties.get('tipo_alerta', 'other')),
                    'severity': self._map_severity(properties.get('severidad', 'medium')),
                    'lat': None,  # Se extraerá de geometry si existe
                    'lon': None,
                    'address': properties.get('direccion', ''),
                    'start_date': self._parse_datetime(properties.get('fecha_inicio')),
                    'end_date': self._parse_datetime(properties.get('fecha_fin')),
                    'affected_routes': properties.get('rutas_afectadas', []),
                    'recommended_actions': properties.get('acciones_recomendadas', []),
                }

                # Extraer coordenadas si existe geometry
                geometry = feature.get('geometry', {})
                if geometry.get('coordinates'):
                    alert_data['lon'] = geometry['coordinates'][0]
                    alert_data['lat'] = geometry['coordinates'][1]

                if alert_data['start_date']:
                    alerts.append(alert_data)

        logger.info(f"Obtenidas {len(alerts)} alertas de transporte")
        return alerts

    def update_street_closures(self) -> int:
        """
        Actualiza la base de datos con cortes de calles
        Retorna el número de registros actualizados/creados
        """
        closures_data = self.get_street_closures()
        updated_count = 0

        for closure_data in closures_data:
            closure, created = StreetClosure.objects.update_or_create(
                external_id=closure_data['external_id'],
                defaults=closure_data
            )
            if created:
                updated_count += 1

        # Marcar como inactivos los cortes que ya no están en la API
        active_ids = [c['external_id'] for c in closures_data]
        StreetClosure.objects.exclude(external_id__in=active_ids).update(is_active=False)

        logger.info(f"Actualizados {updated_count} cortes de calles")
        return updated_count

    def update_parking_data(self) -> int:
        """
        Actualiza la base de datos con datos de estacionamiento
        """
        parking_data = self.get_parking_data()
        updated_count = 0

        for spot_data in parking_data:
            spot, created = ParkingSpot.objects.update_or_create(
                external_id=spot_data['external_id'],
                defaults=spot_data
            )
            if created:
                updated_count += 1

        logger.info(f"Actualizados {updated_count} lugares de estacionamiento")
        return updated_count

    def update_traffic_counts(self) -> int:
        """
        Actualiza la base de datos con conteos de tránsito
        """
        counts_data = self.get_traffic_counts()
        updated_count = 0

        for count_data in counts_data:
            # Crear registro único por timestamp y ubicación
            count, created = TrafficCount.objects.update_or_create(
                external_id=f"{count_data['external_id']}_{count_data['timestamp'].isoformat()}",
                defaults=count_data
            )
            if created:
                updated_count += 1

        logger.info(f"Actualizados {updated_count} conteos de tránsito")
        return updated_count

    def update_transport_alerts(self) -> int:
        """
        Actualiza la base de datos con alertas de transporte
        """
        alerts_data = self.get_transport_alerts()
        updated_count = 0

        for alert_data in alerts_data:
            alert, created = TransportAlert.objects.update_or_create(
                external_id=alert_data['external_id'],
                defaults=alert_data
            )
            if created:
                updated_count += 1

        # Marcar como inactivas las alertas que ya no están activas
        active_ids = [a['external_id'] for a in alerts_data]
        TransportAlert.objects.exclude(external_id__in=active_ids).update(is_active=False)

        logger.info(f"Actualizadas {updated_count} alertas de transporte")
        return updated_count

    def update_all_data(self) -> Dict[str, int]:
        """
        Actualiza todos los datos de transporte
        """
        logger.info("Iniciando actualización completa de datos de transporte...")

        results = {
            'street_closures': self.update_street_closures(),
            'parking_spots': self.update_parking_data(),
            'traffic_counts': self.update_traffic_counts(),
            'transport_alerts': self.update_transport_alerts(),
        }

        logger.info(f"Actualización completa finalizada: {results}")
        return results

    # Métodos auxiliares para mapear tipos

    def _map_closure_type(self, api_type: str) -> str:
        """Mapea tipos de corte de la API a nuestros choices"""
        mapping = {
            'total': 'total',
            'parcial': 'parcial',
            'alternado': 'alternado',
            'restringido': 'restringido',
        }
        return mapping.get(api_type.lower(), 'total')

    def _map_parking_type(self, api_type: str) -> str:
        """Mapea tipos de estacionamiento de la API"""
        mapping = {
            'calle': 'street',
            'cubierto': 'garage',
            'playon': 'lot',
            'emergencia': 'emergency',
        }
        return mapping.get(api_type.lower(), 'street')

    def _map_count_type(self, api_type: str) -> str:
        """Mapea tipos de conteo de tránsito"""
        mapping = {
            'vehiculos': 'vehicle',
            'velocidad': 'speed',
            'ocupacion': 'occupancy',
        }
        return mapping.get(api_type.lower(), 'vehicle')

    def _map_alert_type(self, api_type: str) -> str:
        """Mapea tipos de alerta"""
        mapping = {
            'corte_calle': 'closure',
            'accidente': 'accident',
            'obra': 'construction',
            'evento': 'event',
            'clima': 'weather',
        }
        return mapping.get(api_type.lower(), 'other')

    def _map_severity(self, api_severity: str) -> str:
        """Mapea severidad de alertas"""
        mapping = {
            'baja': 'low',
            'media': 'medium',
            'alta': 'high',
            'critica': 'critical',
        }
        return mapping.get(api_severity.lower(), 'medium')

    def _parse_datetime(self, date_str: Optional[str]) -> Optional[datetime]:
        """
        Parsea una fecha/hora de la API
        """
        if not date_str:
            return None

        # Intentar diferentes formatos comunes
        formats = [
            '%Y-%m-%dT%H:%M:%S%z',  # ISO con timezone
            '%Y-%m-%dT%H:%M:%S',    # ISO sin timezone
            '%Y-%m-%d %H:%M:%S',    # Formato MySQL
            '%Y-%m-%d',             # Solo fecha
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                # Si no tiene timezone, asumir UTC
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                continue

        logger.warning(f"No se pudo parsear fecha: {date_str}")
        return None


# Función de conveniencia para obtener instancia del cliente
def get_transport_client() -> BuenosAiresTransportClient:
    """Factory function para obtener instancia del cliente de transporte"""
    return BuenosAiresTransportClient()