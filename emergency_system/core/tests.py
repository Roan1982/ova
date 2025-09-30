from django.test import TestCase, RequestFactory
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.utils import timezone
from datetime import timedelta, datetime
from unittest.mock import patch
from types import SimpleNamespace
import random

from .llm import classify_with_ai
from .models import Force, Vehicle, Emergency, EmergencyDispatch, CalculatedRoute
from .views import process_emergency, _interpolate_route_point, _determine_traffic_factor, _build_vehicle_tracking


class CloudAIFallbackTests(TestCase):
	def test_classify_with_ai_returns_fallback_structure_without_api_key(self):
		result = classify_with_ai("Robo en progreso con violencia")

		self.assertIn('tipo', result)
		self.assertIn('codigo', result)
		self.assertIn('recursos', result)
		self.assertGreaterEqual(len(result['recursos']), 1)
		self.assertEqual(result.get('fuente'), 'local')


class EmergencyRoutingAssignmentTests(TestCase):
	def setUp(self):
		self.factory = RequestFactory()

		self.force_police = Force.objects.create(name='Policía')
		self.force_same = Force.objects.create(name='SAME')

		# Vehículos policiales cercanos (deben ser priorizados)
		self.near_vehicle = Vehicle.objects.create(
			force=self.force_police,
			type='Patrulla',
			current_lat=-34.6037,
			current_lon=-58.3816,
			status='disponible'
		)

		self.second_police_vehicle = Vehicle.objects.create(
			force=self.force_police,
			type='Patrulla',
			current_lat=-34.6050,
			current_lon=-58.3790,
			status='disponible'
		)

		# Vehículo lejano para asegurar priorización por distancia
		self.far_vehicle = Vehicle.objects.create(
			force=self.force_same,
			type='Ambulancia',
			current_lat=-34.70,
			current_lon=-58.50,
			status='disponible'
		)

		self.emergency = Emergency.objects.create(
			description='Robo violento con arma blanca en el microcentro',
			location_lat=-34.6083,
			location_lon=-58.3712,
			status='pendiente',
			code='verde',
			priority=1
		)

	def _add_messages_storage(self, request):
		middleware = SessionMiddleware(lambda r: None)
		middleware.process_request(request)
		request.session.save()
		messages = FallbackStorage(request)
		setattr(request, '_messages', messages)

	def test_process_emergency_assigns_nearest_vehicle(self):
		request = self.factory.get('/')
		request.user = AnonymousUser()
		self._add_messages_storage(request)

		response = process_emergency(request, self.emergency.pk)
		self.assertEqual(response.status_code, 302)

		self.emergency.refresh_from_db()
		self.near_vehicle.refresh_from_db()
		self.second_police_vehicle.refresh_from_db()
		self.far_vehicle.refresh_from_db()

		self.assertIn(self.emergency.assigned_vehicle_id, {self.near_vehicle.id, self.second_police_vehicle.id})
		self.assertEqual(self.emergency.status, 'asignada')
		self.assertEqual(self.near_vehicle.status, 'en_ruta')
		self.assertEqual(self.second_police_vehicle.status, 'en_ruta')
		self.assertEqual(self.far_vehicle.status, 'disponible')

		dispatches = EmergencyDispatch.objects.filter(emergency=self.emergency)
		self.assertEqual(dispatches.count(), 1)
		dispatch = dispatches.first()
		self.assertEqual(dispatch.vehicle.force, self.force_police)
		self.assertEqual(dispatch.status, 'en_ruta')
		self.assertIn('Clasificación IA', self.emergency.resolution_notes)

		dispatched_routes = CalculatedRoute.objects.filter(emergency=self.emergency)
		self.assertGreaterEqual(dispatched_routes.count(), dispatches.count())
		self.assertTrue(
			dispatched_routes.filter(resource_id=f"vehicle_{dispatch.vehicle_id}").exists()
		)


class RouteSimulationHelpersTests(TestCase):
	def setUp(self):
		self.force = Force.objects.create(name='Policía')
		self.vehicle = Vehicle.objects.create(
			force=self.force,
			type='Patrulla',
			current_lat=-34.6037,
			current_lon=-58.3816,
			status='en_ruta'
		)
		self.emergency = Emergency.objects.create(
			description='Emergencia código rojo en microcentro',
			location_lat=-34.6100,
			location_lon=-58.3770,
			status='asignada',
			code='rojo',
			priority=10,
			onda_verde=True
		)
		self.emergency.assigned_force = self.force
		self.emergency.assigned_vehicle = self.vehicle
		self.emergency.save(update_fields=['assigned_force', 'assigned_vehicle'])
		self.vehicle.target_lat = self.emergency.location_lat
		self.vehicle.target_lon = self.emergency.location_lon
		self.vehicle.save(update_fields=['target_lat', 'target_lon'])
		self.dispatch = EmergencyDispatch.objects.create(
			emergency=self.emergency,
			force=self.force,
			vehicle=self.vehicle,
			status='en_ruta'
		)
		self.route = CalculatedRoute.objects.create(
			emergency=self.emergency,
			resource_id=f'vehicle_{self.vehicle.id}',
			resource_type='Patrulla - Policía',
			distance_km=2.0,
			estimated_time_minutes=6.0,
			priority_score=1.0,
			route_geometry={
				'type': 'LineString',
				'coordinates': [
					[self.vehicle.current_lon, self.vehicle.current_lat],
					[self.emergency.location_lon, self.emergency.location_lat]
				]
			},
			status='activa'
		)

	def test_interpolate_route_point_midway(self):
		geometry = {
			'type': 'LineString',
			'coordinates': [
				[-58.3816, -34.6037],
				[-58.3770, -34.6100]
			]
		}
		point = _interpolate_route_point(geometry, 0.5)
		self.assertIsNotNone(point)
		self.assertTrue(-34.6100 <= point[0] <= -34.6037)
		self.assertTrue(-58.3816 <= point[1] <= -58.3770)

	def test_determine_traffic_factor_green_wave(self):
		route_stub = SimpleNamespace(resource_id='vehicle_test', emergency_id=self.emergency.id)
		fixed_now = timezone.make_aware(datetime(2025, 9, 30, 8, 0))
		with patch('core.views.timezone.now', return_value=fixed_now):
			factor = _determine_traffic_factor(route_stub, self.emergency)
		rng = random.Random(f"vehicle_test-{self.emergency.id}")
		base = rng.uniform(0.85, 1.35)
		peak = rng.uniform(1.05, 1.25)
		expected = max(0.45, min(base * peak * 0.6, 1.75))
		self.assertAlmostEqual(factor, expected)
		self.assertLessEqual(factor, 1.1)

	def test_build_vehicle_tracking_halfway(self):
		fixed_now = timezone.make_aware(datetime(2025, 9, 30, 8, 0))
		with patch('core.views.timezone.now', return_value=fixed_now):
			traffic_factor = _determine_traffic_factor(self.route, self.emergency)
		total_seconds = max(self.route.estimated_time_minutes * 60, 60) * traffic_factor
		elapsed = total_seconds / 2
		self.route.calculated_at = fixed_now - timedelta(seconds=elapsed)
		self.route.save(update_fields=['calculated_at'])
		with patch('core.views.timezone.now', return_value=fixed_now):
			payload = _build_vehicle_tracking(self.dispatch, self.route)
		self.assertIsNotNone(payload)
		self.assertEqual(payload['id'], f'vehicle_{self.vehicle.id}')
		self.assertAlmostEqual(payload['progress'], 0.5, delta=0.05)
		self.assertIn(payload['traffic_level'], {'libre', 'moderado', 'congestionado'})
		lat_bounds = sorted([self.vehicle.current_lat, self.emergency.location_lat])
		lon_bounds = sorted([self.vehicle.current_lon, self.emergency.location_lon])
		self.assertTrue(lat_bounds[0] <= payload['current_position'][0] <= lat_bounds[1])
		self.assertTrue(lon_bounds[0] <= payload['current_position'][1] <= lon_bounds[1])
