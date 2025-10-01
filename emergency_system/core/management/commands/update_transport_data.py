from django.core.management.base import BaseCommand
from django.utils import timezone
from core.transport_client import BuenosAiresTransportClient
from core.models import StreetClosure, ParkingSpot, TrafficCount, TransportAlert
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Actualiza datos de transporte desde la API de Buenos Aires'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Forzar actualización completa de todos los datos',
        )
        parser.add_argument(
            '--only-traffic',
            action='store_true',
            help='Actualizar solo datos de tráfico',
        )
        parser.add_argument(
            '--only-closures',
            action='store_true',
            help='Actualizar solo cierres de calles',
        )
        parser.add_argument(
            '--only-parking',
            action='store_true',
            help='Actualizar solo datos de estacionamiento',
        )

    def handle(self, *args, **options):
        self.stdout.write('🚗 Iniciando actualización de datos de transporte...')

        client = BuenosAiresTransportClient()
        updated_counts = {
            'closures': 0,
            'parking': 0,
            'traffic': 0,
            'alerts': 0,
        }

        try:
            if options['only_closures'] or options['force'] or not any([
                options['only_traffic'], options['only_closures'], options['only_parking']
            ]):
                self.stdout.write('📍 Actualizando cierres de calles...')
                closures_data = client.get_street_closures()
                updated_counts['closures'] = self._update_closures(closures_data)
                self.stdout.write(f'✅ Actualizados {updated_counts["closures"]} cierres de calles')

            if options['only_parking'] or options['force'] or not any([
                options['only_traffic'], options['only_closures'], options['only_parking']
            ]):
                self.stdout.write('🏪 Actualizando datos de estacionamiento...')
                parking_data = client.get_parking_data()
                updated_counts['parking'] = self._update_parking(parking_data)
                self.stdout.write(f'✅ Actualizados {updated_counts["parking"]} lugares de estacionamiento')

            if options['only_traffic'] or options['force'] or not any([
                options['only_traffic'], options['only_closures'], options['only_parking']
            ]):
                self.stdout.write('🚦 Actualizando datos de tráfico...')
                traffic_data = client.get_traffic_counts()
                updated_counts['traffic'] = self._update_traffic(traffic_data)
                self.stdout.write(f'✅ Actualizados {updated_counts["traffic"]} puntos de tráfico')

                self.stdout.write('🚨 Actualizando alertas de transporte...')
                alerts_data = client.get_transport_alerts()
                updated_counts['alerts'] = self._update_alerts(alerts_data)
                self.stdout.write(f'✅ Actualizadas {updated_counts["alerts"]} alertas')

            # Limpiar datos antiguos
            self._cleanup_old_data()

            self.stdout.write(
                self.style.SUCCESS(
                    f'🎉 Actualización completada exitosamente!\n'
                    f'📊 Resumen:\n'
                    f'   • Cierres de calles: {updated_counts["closures"]}\n'
                    f'   • Estacionamientos: {updated_counts["parking"]}\n'
                    f'   • Puntos de tráfico: {updated_counts["traffic"]}\n'
                    f'   • Alertas: {updated_counts["alerts"]}'
                )
            )

        except Exception as e:
            self.stderr.write(
                self.style.ERROR(f'❌ Error durante la actualización: {str(e)}')
            )
            logger.error(f"Error updating transport data: {str(e)}", exc_info=True)
            raise

    def _update_closures(self, closures_data):
        """Actualiza los cierres de calles"""
        updated_count = 0
        current_time = timezone.now()

        for closure in closures_data:
            obj, created = StreetClosure.objects.update_or_create(
                external_id=closure['id'],
                defaults={
                    'name': closure.get('name', ''),
                    'description': closure.get('description', ''),
                    'closure_type': closure.get('type', 'unknown'),
                    'start_datetime': closure.get('start_time'),
                    'end_datetime': closure.get('end_time'),
                    'geometry': closure.get('geometry', {}),
                    'is_active': closure.get('is_active', True),
                    'severity': closure.get('severity', 'medium'),
                    'last_updated': current_time,
                }
            )
            if created or obj.last_updated != current_time:
                updated_count += 1

        # Marcar como inactivos los cierres que ya no están en la API
        active_ids = [c['id'] for c in closures_data]
        StreetClosure.objects.filter(
            is_active=True
        ).exclude(external_id__in=active_ids).update(
            is_active=False,
            last_updated=current_time
        )

        return updated_count

    def _update_parking(self, parking_data):
        """Actualiza los datos de estacionamiento"""
        updated_count = 0
        current_time = timezone.now()

        for spot in parking_data:
            obj, created = ParkingSpot.objects.update_or_create(
                external_id=spot['id'],
                defaults={
                    'name': spot.get('name', ''),
                    'address': spot.get('address', ''),
                    'lat': spot.get('lat'),
                    'lon': spot.get('lon'),
                    'total_spaces': spot.get('total_spaces', 0),
                    'available_spaces': spot.get('available_spaces', 0),
                    'spot_type': spot.get('type', 'unknown'),
                    'is_paid': spot.get('is_paid', False),
                    'max_duration_hours': spot.get('max_duration', 2),
                    'price_per_hour': spot.get('price_per_hour', 0.0),
                    'is_active': spot.get('is_active', True),
                    'last_updated': current_time,
                }
            )
            if created or obj.last_updated != current_time:
                updated_count += 1

        return updated_count

    def _update_traffic(self, traffic_data):
        """Actualiza los datos de tráfico"""
        updated_count = 0
        current_time = timezone.now()

        for traffic in traffic_data:
            obj, created = TrafficCount.objects.update_or_create(
                external_id=traffic['id'],
                timestamp=traffic.get('timestamp'),
                defaults={
                    'lat': traffic.get('lat'),
                    'lon': traffic.get('lon'),
                    'vehicle_count': traffic.get('vehicle_count', 0),
                    'average_speed': traffic.get('average_speed', 0.0),
                    'congestion_level': traffic.get('congestion_level', 'unknown'),
                    'road_type': traffic.get('road_type', 'unknown'),
                    'direction': traffic.get('direction', ''),
                    'last_updated': current_time,
                }
            )
            if created or obj.last_updated != current_time:
                updated_count += 1

        return updated_count

    def _update_alerts(self, alerts_data):
        """Actualiza las alertas de transporte"""
        updated_count = 0
        current_time = timezone.now()

        for alert in alerts_data:
            obj, created = TransportAlert.objects.update_or_create(
                external_id=alert['id'],
                defaults={
                    'title': alert.get('title', ''),
                    'description': alert.get('description', ''),
                    'alert_type': alert.get('type', 'info'),
                    'severity': alert.get('severity', 'low'),
                    'start_datetime': alert.get('start_time'),
                    'end_datetime': alert.get('end_time'),
                    'lat': alert.get('lat'),
                    'lon': alert.get('lon'),
                    'affected_area': alert.get('affected_area', {}),
                    'is_active': alert.get('is_active', True),
                    'last_updated': current_time,
                }
            )
            if created or obj.last_updated != current_time:
                updated_count += 1

        # Marcar como inactivas las alertas que ya no están activas
        active_ids = [a['id'] for a in alerts_data if a.get('is_active', True)]
        TransportAlert.objects.filter(
            is_active=True
        ).exclude(external_id__in=active_ids).update(
            is_active=False,
            last_updated=current_time
        )

        return updated_count

    def _cleanup_old_data(self):
        """Limpia datos antiguos para mantener la base de datos optimizada"""
        current_time = timezone.now()

        # Eliminar cierres antiguos (más de 30 días)
        old_closures = StreetClosure.objects.filter(
            end_datetime__lt=current_time - timezone.timedelta(days=30)
        )
        closures_deleted = old_closures.delete()[0]

        # Eliminar datos de tráfico antiguos (más de 7 días)
        old_traffic = TrafficCount.objects.filter(
            timestamp__lt=current_time - timezone.timedelta(days=7)
        )
        traffic_deleted = old_traffic.delete()[0]

        # Eliminar alertas antiguas (más de 7 días)
        old_alerts = TransportAlert.objects.filter(
            end_datetime__lt=current_time - timezone.timedelta(days=7)
        )
        alerts_deleted = old_alerts.delete()[0]

        if closures_deleted > 0 or traffic_deleted > 0 or alerts_deleted > 0:
            self.stdout.write(
                f'🧹 Datos antiguos eliminados: {closures_deleted} cierres, '
                f'{traffic_deleted} puntos de tráfico, {alerts_deleted} alertas'
            )