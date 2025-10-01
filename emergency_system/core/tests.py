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
from .models import Force, Vehicle, Emergency, EmergencyDispatch, CalculatedRoute, Agent
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


class EmergencyParkingTests(TestCase):
	"""Tests para el sistema de estacionamiento de emergencias"""

	def setUp(self):
		"""Configurar datos de prueba"""
		from .routing import RouteOptimizer
		from .models import ParkingSpot
		self.optimizer = RouteOptimizer()

		# Crear lugares de estacionamiento de prueba
		self.parking_spots = [
			ParkingSpot.objects.create(
				external_id='parking_001',
				name='Estacionamiento Centro',
				address='Av. Corrientes 1234',
				lat=-34.6037,
				lon=-58.3816,
				total_spaces=50,
				available_spaces=25,
				spot_type='street',
				is_paid=True,
				max_duration_hours=2,
				is_active=True,
				last_updated=timezone.now()
			),
			ParkingSpot.objects.create(
				external_id='parking_002',
				name='Estacionamiento Tribunales',
				address='Talcahuano 123',
				lat=-34.6018,
				lon=-58.3851,
				total_spaces=30,
				available_spaces=5,
				spot_type='garage',
				is_paid=False,
				max_duration_hours=8,
				is_active=True,
				last_updated=timezone.now()
			),
		]

	def test_find_emergency_parking_basic(self):
		"""Test básico de búsqueda de estacionamiento"""
		emergency_location = (-34.6030, -58.3820)  # Cerca del primer estacionamiento

		parking_options = self.optimizer.find_emergency_parking(
			emergency_location,
			max_distance_meters=1000,
			min_spaces_required=1
		)

		self.assertGreater(len(parking_options), 0)
		self.assertIn('parking_001', [p['id'] for p in parking_options])

		# Verificar que el más cercano aparezca primero
		closest_parking = parking_options[0]
		self.assertEqual(closest_parking['id'], 'parking_001')
		self.assertIn('distance_meters', closest_parking)
		self.assertIn('walking_time_minutes', closest_parking)

	def test_find_emergency_parking_no_available(self):
		"""Test cuando no hay estacionamiento disponible"""
		from .models import ParkingSpot
		# Marcar todos los estacionamientos como no disponibles
		ParkingSpot.objects.all().update(available_spaces=0)

		emergency_location = (-34.6030, -58.3820)
		parking_options = self.optimizer.find_emergency_parking(
			emergency_location,
			max_distance_meters=1000,
			min_spaces_required=1
		)

		self.assertEqual(len(parking_options), 0)

	def test_calculate_distance(self):
		"""Test del cálculo de distancia"""
		# Distancia conocida entre dos puntos en Buenos Aires
		lat1, lon1 = -34.6037, -58.3816  # Obelisco
		lat2, lon2 = -34.6018, -58.3851  # Cerca de Tribunales

		distance = self.optimizer.calculate_distance(lat1, lon1, lat2, lon2)

		# Debería ser aproximadamente 400-500 metros
		self.assertGreater(distance, 300)
		self.assertLess(distance, 600)

	def test_parking_occupancy_rate_calculation(self):
		"""Test del cálculo de tasa de ocupación"""
		spot = self.parking_spots[0]  # 25 disponibles de 50 totales

		# 25 disponibles de 50 totales = 25 ocupados = 50% ocupación
		expected_rate = 50.0
		self.assertEqual(spot.occupancy_rate, expected_rate)

		# Cambiar disponibilidad a 40 (10 ocupados)
		spot.available_spaces = 40
		spot.save()

		# 40 disponibles de 50 totales = 10 ocupados = 20% ocupación
		expected_rate = 20.0
		spot.refresh_from_db()
		self.assertEqual(spot.occupancy_rate, expected_rate)


class AgentAssignmentTests(TestCase):
	"""Tests para la asignación de agentes a emergencias"""

	def setUp(self):
		self.force_police = Force.objects.create(name='Policía')
		self.force_same = Force.objects.create(name='SAME')

		# Crear agentes disponibles
		self.agent_police_1 = Agent.objects.create(
			name='Juan Pérez',
			force=self.force_police,
			role='Oficial',
			status='disponible',
			lat=-34.6037,
			lon=-58.3816
		)

		self.agent_police_2 = Agent.objects.create(
			name='María García',
			force=self.force_police,
			role='Sargento',
			status='disponible',
			lat=-34.6050,
			lon=-58.3790
		)

		self.agent_same = Agent.objects.create(
			name='Carlos López',
			force=self.force_same,
			role='Paramédico',
			status='disponible',
			lat=-34.70,
			lon=-58.50
		)

		# Crear vehículos disponibles
		self.vehicle_police = Vehicle.objects.create(
			force=self.force_police,
			type='Patrulla',
			current_lat=-34.6037,
			current_lon=-58.3816,
			status='disponible'
		)

		self.vehicle_same = Vehicle.objects.create(
			force=self.force_same,
			type='Ambulancia',
			current_lat=-34.70,
			current_lon=-58.50,
			status='disponible'
		)

	def test_emergency_assigns_available_agent(self):
		"""Test que una emergencia asigna el mejor agente disponible (más cercano/rápido)"""
		emergency = Emergency.objects.create(
			description='Robo violento con arma blanca',
			location_lat=-34.6083,
			location_lon=-58.3712,
			status='pendiente'
		)

		# Forzar clasificación que requiere policía
		emergency.code = 'amarillo'
		emergency.save()

		# Procesar la emergencia (esto activa ensure_multi_dispatch)
		emergency.ensure_multi_dispatch()

		# Verificar que se creó un dispatch
		dispatches = EmergencyDispatch.objects.filter(emergency=emergency)
		self.assertEqual(dispatches.count(), 1)

		dispatch = dispatches.first()
		self.assertEqual(dispatch.force, self.force_police)

		# Verificar que se asignó un agente disponible
		self.assertIsNotNone(dispatch.agent)
		# Debería asignar el agente más cercano (agent_police_1 está más cerca que agent_police_2)
		self.assertEqual(dispatch.agent, self.agent_police_1)

		# Verificar que el agente cambió de status
		dispatch.agent.refresh_from_db()
		self.assertEqual(dispatch.agent.status, 'en_ruta')

		# Verificar que también se asignó un vehículo
		self.assertIsNotNone(dispatch.vehicle)
		dispatch.vehicle.refresh_from_db()
		self.assertEqual(dispatch.vehicle.status, 'en_ruta')

	def test_emergency_resolve_frees_agent(self):
		"""Test que resolver una emergencia libera al agente asignado"""
		emergency = Emergency.objects.create(
			description='Robo violento con arma blanca',
			location_lat=-34.6083,
			location_lon=-58.3712,
			status='pendiente'
		)

		# Asignar agente manualmente para simular
		dispatch = EmergencyDispatch.objects.create(
			emergency=emergency,
			force=self.force_police,
			agent=self.agent_police_1,
			vehicle=self.vehicle_police,
			status='en_ruta'
		)

		# Cambiar status del agente y vehículo
		self.agent_police_1.status = 'en_ruta'
		self.agent_police_1.save()
		self.vehicle_police.status = 'en_ruta'
		self.vehicle_police.save()

		# Resolver la emergencia
		emergency.resolve('Emergencia resuelta exitosamente')

		# Verificar que el agente fue liberado
		self.agent_police_1.refresh_from_db()
		self.assertEqual(self.agent_police_1.status, 'disponible')

		# Verificar que el vehículo fue liberado
		self.vehicle_police.refresh_from_db()
		self.assertEqual(self.vehicle_police.status, 'disponible')

		# Verificar que el dispatch fue finalizado
		dispatch.refresh_from_db()
		self.assertEqual(dispatch.status, 'finalizado')

	def test_emergency_no_agent_assigned_when_unavailable(self):
		"""Test que no se asigna agente si no hay disponibles"""
		# Marcar todos los agentes como no disponibles
		Agent.objects.filter(force=self.force_police).update(status='ocupado')

		emergency = Emergency.objects.create(
			description='Robo violento con arma blanca',
			location_lat=-34.6083,
			location_lon=-58.3712,
			status='pendiente'
		)

		emergency.code = 'amarillo'
		emergency.save()
		emergency.ensure_multi_dispatch()

		# Verificar que se creó el dispatch
		dispatches = EmergencyDispatch.objects.filter(emergency=emergency)
		self.assertEqual(dispatches.count(), 1)

		dispatch = dispatches.first()
		# El agente debería ser None si no hay disponibles
		self.assertIsNone(dispatch.agent)

		# Pero el vehículo sí debería asignarse
		self.assertIsNotNone(dispatch.vehicle)

	def test_emergency_assigns_closest_agent(self):
		"""Test que se asigna el agente más cercano cuando hay múltiples disponibles"""
		# Crear un agente más lejano
		far_agent = Agent.objects.create(
			name='Agente Lejano',
			force=self.force_police,
			role='Oficial',
			status='disponible',
			lat=-34.70,  # Mucho más lejos
			lon=-58.50
		)

		emergency = Emergency.objects.create(
			description='Robo violento con arma blanca',
			location_lat=-34.6083,
			location_lon=-58.3712,
			status='pendiente'
		)

		emergency.code = 'amarillo'
		emergency.save()
		emergency.ensure_multi_dispatch()

		dispatches = EmergencyDispatch.objects.filter(emergency=emergency)
		dispatch = dispatches.first()

		# Debería asignar el agente más cercano (agent_police_1)
		self.assertEqual(dispatch.agent, self.agent_police_1)
		self.assertNotEqual(dispatch.agent, far_agent)
