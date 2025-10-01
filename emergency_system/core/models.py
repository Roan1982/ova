from django.db import models
from django.utils import timezone
from django.conf import settings
from .ai import classify_emergency
from .llm import classify_with_ai

class Force(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name='Nombre')  # e.g., 'Bomberos', 'SAME', 'Policía', 'Tránsito'
    contact_info = models.TextField(blank=True, verbose_name='Información de Contacto')
    created_at = models.DateTimeField(default=timezone.now, verbose_name='Creado en')

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = 'Fuerza'
        verbose_name_plural = 'Fuerzas'

class Vehicle(models.Model):
    force = models.ForeignKey(Force, on_delete=models.CASCADE, verbose_name='Fuerza')
    type = models.CharField(max_length=100, verbose_name='Tipo')  # e.g., 'Ambulancia', 'Camión de Bomberos', 'Patrulla', 'Moto de Tránsito'
    current_lat = models.FloatField(null=True, blank=True, verbose_name='Latitud Actual')
    current_lon = models.FloatField(null=True, blank=True, verbose_name='Longitud Actual')
    # Objetivo para simulación o IA
    target_lat = models.FloatField(null=True, blank=True, verbose_name='Latitud Objetivo')
    target_lon = models.FloatField(null=True, blank=True, verbose_name='Longitud Objetivo')
    # Base de origen (instalación)
    home_facility = models.ForeignKey('Facility', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Base')
    status = models.CharField(max_length=50, choices=[('disponible', 'Disponible'), ('en_ruta', 'En Ruta'), ('ocupado', 'Ocupado') ], default='disponible', verbose_name='Estado')

    def __str__(self):
        return f"{self.type} - {self.force.name}"

    class Meta:
        verbose_name = 'Vehículo'
        verbose_name_plural = 'Vehículos'

class Emergency(models.Model):
    CODE_CHOICES = [
        ('rojo', 'Rojo - Crítica'),
        ('amarillo', 'Amarillo - Urgente'),
        ('verde', 'Verde - Leve'),
    ]

    STATUS_CHOICES = [
        ('pendiente', 'Pendiente'),
        ('asignada', 'Asignada'),
        ('resuelta', 'Resuelta'),
    ]

    code = models.CharField(max_length=50, choices=CODE_CHOICES, blank=True, verbose_name='Código')
    priority = models.IntegerField(default=0, verbose_name='Prioridad')
    description = models.TextField(verbose_name='Descripción')
    address = models.CharField(max_length=255, blank=True, verbose_name='Dirección')
    location_lat = models.FloatField(null=True, blank=True, verbose_name='Latitud')
    location_lon = models.FloatField(null=True, blank=True, verbose_name='Longitud')
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='pendiente', verbose_name='Estado')
    # Campos de compatibilidad (resumen primario)
    assigned_force = models.ForeignKey('Force', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Fuerza Asignada')
    assigned_vehicle = models.ForeignKey('Vehicle', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Vehículo Asignado')
    onda_verde = models.BooleanField(default=False, verbose_name='Onda Verde')
    reported_at = models.DateTimeField(default=timezone.now, verbose_name='Reportado en')
    resolved_at = models.DateTimeField(null=True, blank=True, verbose_name='Resuelto en')
    resolution_notes = models.TextField(blank=True, verbose_name='Notas de Resolución')
    ai_response = models.TextField(blank=True, verbose_name='Respuesta IA')

    def __str__(self):
        return f"Emergencia {self.id} - {self.code}"

    class Meta:
        verbose_name = 'Emergencia'
        verbose_name_plural = 'Emergencias'

    def save(self, *args, **kwargs):
        new_instance = self.pk is None
        if not self.code:
            self.code = self.classify_code()
        if self.code == 'rojo':
            self.onda_verde = True
            self.priority = 10
        elif self.code == 'amarillo':
            self.priority = 5
        else:
            self.priority = 1
        super().save(*args, **kwargs)
        if new_instance and self.code in ['rojo', 'amarillo']:
            self.process_ia()

    def classify_code(self):
    # Intentar clasificar con IA en la nube si está disponible
        try:
            result = classify_with_ai(self.description)
        except Exception:
            result = None

        if result:
            code = result.get('codigo') or 'verde'
            score = result.get('score') or (60 if code == 'rojo' else 30 if code == 'amarillo' else 5)
            reasons = result.get('razones', [])
            # Sugerencia de fuerza primaria desde la IA
            tipo = result.get('tipo')
            if tipo == 'bomberos':
                self.assigned_force = Force.objects.filter(name='Bomberos').first()
            elif tipo == 'medico':
                self.assigned_force = Force.objects.filter(name='SAME').first()
            elif tipo == 'policial':
                self.assigned_force = Force.objects.filter(name='Policía').first()
        else:
            code, score, reasons = classify_emergency(self.description)
        self.priority = 10 if code == 'rojo' else 5 if code == 'amarillo' else 1
        # Si hay IA, dejar sólo el reporte de IA
        if result:
            fuente = result.get('fuente', 'ia').upper()
            tipo_val = result.get('tipo') or ''
            razones = reasons or []
            informe = (
                f"Clasificación IA ({fuente})\n"
                f"- Tipo: {tipo_val}\n"
                f"- Código: {code}\n"
                f"- Puntaje: {score}\n"
                "- Razones:\n  - " + "\n  - ".join(razones)
            )
            recursos = result.get('recursos') or []
            if recursos:
                recursos_txt = "\n  - ".join(
                    f"{r.get('cantidad', 1)} x {r.get('tipo')}" for r in recursos
                )
                informe += f"\n- Recursos sugeridos:\n  - {recursos_txt}"
            self.resolution_notes = informe
        return code

    def _infer_required_forces(self):
        desc_lower = self.description.lower()
        required = set()
        # Fuego
        if any(k in desc_lower for k in ['incendio','fuego','humo','llamas','se quema','se está quemando','se esta quemando']):
            required.add('Bomberos')
        # Accidentes de tránsito
        if any(k in desc_lower for k in ['choque','accidente','colisión','colision']):
            required.update(['Policía','Tránsito','SAME'])
        # Médicas
        if any(k in desc_lower for k in ['herido','médico','medico','salud','infarto','inconsciente','convulsión','convulsion','asfixia','ahogo','hemorragia','atragant','atragantamiento','atragantado','obstrucción de vía aérea','obstruccion de via aerea']):
            required.add('SAME')
        # Seguridad
        if any(k in desc_lower for k in ['robo','robando','roban','crimen','disturbio','corte','bloqueo','manifestación','manifestacion','asalto','atraco','rehen']):
            required.add('Policía')
        # Si nada detectado, por defecto Policía
        if not required:
            required.add('Policía')
        return list(required)

    def ensure_multi_dispatch(self):
        """Crea registros de despacho para todas las fuerzas requeridas."""
        required_names = self._infer_required_forces()
        created_any = False
        for name in required_names:
            force, _ = Force.objects.get_or_create(name=name)
            dispatch, created = EmergencyDispatch.objects.get_or_create(
                emergency=self, force=force,
                defaults={'status': 'despachado'}
            )
            if created:
                # Asignar el mejor vehículo disponible (más cercano/rápido)
                best_vehicle = self._find_best_available_vehicle(force)
                if best_vehicle:
                    dispatch.vehicle = best_vehicle
                    best_vehicle.status = 'en_ruta'
                    best_vehicle.target_lat = self.location_lat
                    best_vehicle.target_lon = self.location_lon
                    best_vehicle.save()
                
                # Asignar el mejor agente disponible (más cercano/rápido)
                best_agent = self._find_best_available_agent(force)
                if best_agent:
                    dispatch.agent = best_agent
                    best_agent.status = 'en_ruta'
                    best_agent.target_lat = self.location_lat
                    best_agent.target_lon = self.location_lon
                    best_agent.save()
                
                dispatch.save()
                created_any = True
        if created_any and self.status == 'pendiente':
            self.status = 'asignada'
            self.save(update_fields=['status'])
        # Establecer resumen primario si no lo hay
        if not self.assigned_force:
            # Prioridad de resumen: Bomberos > SAME > Policía > Tránsito
            priority_order = ['Bomberos','SAME','Policía','Tránsito']
            for n in priority_order:
                d = EmergencyDispatch.objects.filter(emergency=self, force__name=n).first()
                if d:
                    self.assigned_force = d.force
                    self.assigned_vehicle = d.vehicle
                    self.save(update_fields=['assigned_force','assigned_vehicle'])
                    break

    def _find_best_available_vehicle(self, force):
        """Encuentra el mejor vehículo disponible de una fuerza basado en distancia y tiempo estimado."""
        if not (self.location_lat and self.location_lon):
            # Si no hay coordenadas, usar el primer disponible
            return Vehicle.objects.filter(force=force, status='disponible').first()
        
        from .routing import get_route_optimizer
        optimizer = get_route_optimizer()
        emergency_coords = (self.location_lat, self.location_lon)
        
        # Obtener todos los vehículos disponibles de la fuerza
        available_vehicles = Vehicle.objects.filter(
            force=force, 
            status='disponible',
            current_lat__isnull=False,
            current_lon__isnull=False
        )
        
        if not available_vehicles:
            return None
        
        best_vehicle = None
        best_eta = float('inf')
        
        for vehicle in available_vehicles:
            vehicle_coords = (vehicle.current_lat, vehicle.current_lon)
            
            # Calcular ruta óptima
            route_info = optimizer.get_best_route(vehicle_coords, emergency_coords)
            
            # Usar tiempo estimado como criterio principal
            eta_seconds = route_info.get('duration', 0)
            
            # Si es mejor ETA, seleccionar este vehículo
            if eta_seconds < best_eta:
                best_eta = eta_seconds
                best_vehicle = vehicle
        
        return best_vehicle

    def _find_best_available_agent(self, force):
        """Encuentra el mejor agente disponible de una fuerza basado en distancia y tiempo estimado."""
        if not (self.location_lat and self.location_lon):
            # Si no hay coordenadas, usar el primer disponible
            return Agent.objects.filter(force=force, status='disponible').first()
        
        from .routing import get_route_optimizer
        optimizer = get_route_optimizer()
        emergency_coords = (self.location_lat, self.location_lon)
        
        # Obtener todos los agentes disponibles de la fuerza
        available_agents = Agent.objects.filter(
            force=force, 
            status='disponible',
            lat__isnull=False,
            lon__isnull=False
        )
        
        if not available_agents:
            return None
        
        best_agent = None
        best_eta = float('inf')
        
        for agent in available_agents:
            agent_coords = (agent.lat, agent.lon)
            
            # Calcular ruta óptima (asumiendo que los agentes van en vehículo o transporte público)
            route_info = optimizer.get_best_route(agent_coords, emergency_coords)
            
            # Usar tiempo estimado como criterio principal
            eta_seconds = route_info.get('duration', 0)
            
            # Si es mejor ETA, seleccionar este agente
            if eta_seconds < best_eta:
                best_eta = eta_seconds
                best_agent = agent
        
        return best_agent

    def process_ia(self):
        # Mantener compatibilidad: generar multi-despacho
        self.ensure_multi_dispatch()

    def resolve(self, notes=''):
        self.status = 'resuelta'
        self.resolved_at = timezone.now()
        
        # Liberar vehículos y agentes despachados
        for d in EmergencyDispatch.objects.filter(emergency=self):
            if d.vehicle:
                d.vehicle.status = 'disponible'
                d.vehicle.save()
            if d.agent:
                d.agent.status = 'disponible'
                d.agent.save()
            d.status = 'finalizado'
            d.save()
        
        # Marcar todas las rutas calculadas como completadas
        from django.utils import timezone as django_timezone
        updated_routes = CalculatedRoute.objects.filter(emergency=self, status='activa').update(
            status='completada',
            completed_at=django_timezone.now()
        )
        
        if updated_routes > 0:
            print(f"✅ Marcadas {updated_routes} rutas como completadas para emergencia {self.id}")
        
        # Agregar notas de resolución al informe
        if notes:
            self.resolution_notes = (self.resolution_notes or '') + f"\nResolución: {notes}"
        self.save(update_fields=['status', 'resolved_at', 'resolution_notes'])


class CalculatedRoute(models.Model):
    """
    Modelo para guardar las rutas calculadas para cada emergencia
    """
    ROUTE_STATUS_CHOICES = [
        ('activa', 'Activa'),
        ('completada', 'Completada'),
        ('cancelada', 'Cancelada'),
    ]
    
    emergency = models.ForeignKey(Emergency, on_delete=models.CASCADE, related_name='calculated_routes', verbose_name='Emergencia')
    resource_id = models.CharField(max_length=50, verbose_name='ID del Recurso')  # vehicle_123 o agent_456
    resource_type = models.CharField(max_length=100, verbose_name='Tipo de Recurso')  # "Ambulancia - SAME"
    distance_km = models.FloatField(verbose_name='Distancia (km)')
    estimated_time_minutes = models.FloatField(verbose_name='Tiempo Estimado (min)')
    priority_score = models.FloatField(verbose_name='Puntuación de Prioridad')
    route_geometry = models.JSONField(verbose_name='Geometría de la Ruta')  # GeoJSON de la ruta
    status = models.CharField(max_length=20, choices=ROUTE_STATUS_CHOICES, default='activa', verbose_name='Estado')
    calculated_at = models.DateTimeField(default=timezone.now, verbose_name='Calculado en')
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name='Completado en')
    
    class Meta:
        verbose_name = 'Ruta Calculada'
        verbose_name_plural = 'Rutas Calculadas'
        ordering = ['priority_score', 'distance_km']  # Ordenar por mejor ruta primero
    
    def __str__(self):
        return f"Ruta {self.resource_type} → Emergencia {self.emergency_id} ({self.distance_km:.1f}km, {self.estimated_time_minutes:.1f}min)"


class EmergencyDispatch(models.Model):
    STATUS_CHOICES = [
        ('despachado','Despachado'),
        ('en_ruta','En ruta'),
        ('en_escena','En escena'),
        ('finalizado','Finalizado'),
    ]
    emergency = models.ForeignKey(Emergency, on_delete=models.CASCADE, related_name='dispatches', verbose_name='Emergencia')
    force = models.ForeignKey(Force, on_delete=models.CASCADE, verbose_name='Fuerza')
    vehicle = models.ForeignKey(Vehicle, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Vehículo')
    agent = models.ForeignKey('Agent', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Agente')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='despachado', verbose_name='Estado')
    created_at = models.DateTimeField(default=timezone.now, verbose_name='Creado en')

    class Meta:
        verbose_name = 'Despacho'
        verbose_name_plural = 'Despachos'

    def __str__(self):
        return f"{self.force.name} -> Emergencia {self.emergency_id} ({self.status})"

class Agent(models.Model):
    STATUS_CHOICES = [
        ('disponible', 'Disponible'),
        ('en_ruta', 'En Ruta'),
        ('en_escena', 'En Escena'),
        ('ocupado', 'Ocupado'),
        ('fuera_servicio', 'Fuera de Servicio'),
    ]
    name = models.CharField(max_length=120, verbose_name='Nombre y Apellido')
    force = models.ForeignKey(Force, on_delete=models.CASCADE, verbose_name='Fuerza')
    role = models.CharField(max_length=100, verbose_name='Rol/Cargo', blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='disponible', verbose_name='Estado')
    assigned_vehicle = models.ForeignKey(Vehicle, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Vehículo Asignado')
    # Posición actual
    lat = models.FloatField(null=True, blank=True, verbose_name='Latitud')
    lon = models.FloatField(null=True, blank=True, verbose_name='Longitud')
    # Objetivo para simulación o IA
    target_lat = models.FloatField(null=True, blank=True, verbose_name='Latitud Objetivo')
    target_lon = models.FloatField(null=True, blank=True, verbose_name='Longitud Objetivo')
    # Base de origen
    home_facility = models.ForeignKey('Facility', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Base')
    created_at = models.DateTimeField(default=timezone.now, verbose_name='Creado en')

    class Meta:
        verbose_name = 'Agente'
        verbose_name_plural = 'Agentes'

    def __str__(self):
        return f"{self.name} - {self.force.name} ({self.status})"

class Hospital(models.Model):
    name = models.CharField(max_length=150, verbose_name='Nombre')
    address = models.CharField(max_length=255, verbose_name='Dirección', blank=True)
    total_beds = models.PositiveIntegerField(verbose_name='Camas Totales', default=0)
    occupied_beds = models.PositiveIntegerField(verbose_name='Camas Ocupadas', default=0)
    lat = models.FloatField(null=True, blank=True, verbose_name='Latitud')
    lon = models.FloatField(null=True, blank=True, verbose_name='Longitud')
    created_at = models.DateTimeField(default=timezone.now, verbose_name='Creado en')

    class Meta:
        verbose_name = 'Hospital'
        verbose_name_plural = 'Hospitales'

    def __str__(self):
        return f"{self.name} ({self.available_beds}/{self.total_beds} disponibles)"

    @property
    def available_beds(self):
        if self.occupied_beds > self.total_beds:
            return 0
        return self.total_beds - self.occupied_beds

class Facility(models.Model):
    KIND_CHOICES = [
        ('comisaria', 'Comisaría'),
        ('cuartel', 'Cuartel de Bomberos'),
        ('base_transito', 'Base de Tránsito'),
    ]
    name = models.CharField(max_length=200, verbose_name='Nombre')
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, verbose_name='Tipo')
    force = models.ForeignKey(Force, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Fuerza')
    address = models.CharField(max_length=255, verbose_name='Dirección', blank=True)
    lat = models.FloatField(null=True, blank=True, verbose_name='Latitud')
    lon = models.FloatField(null=True, blank=True, verbose_name='Longitud')
    created_at = models.DateTimeField(default=timezone.now, verbose_name='Creado en')

    class Meta:
        verbose_name = 'Instalación'
        verbose_name_plural = 'Instalaciones'

    def __str__(self):
        return f"{self.name} ({self.get_kind_display()})"

    # Utilidades
    def vehicles(self):
        return Vehicle.objects.filter(home_facility=self)

    def vehicles_count(self):
        return self.vehicles().count()

    def vehicles_by_type(self):
        return self.vehicles().values('type').annotate(total=models.Count('id')).order_by('type')


# -------------------------------------------------------------------
# Modelos para integración con API de Transporte de Buenos Aires
# -------------------------------------------------------------------

class StreetClosure(models.Model):
    """
    Modelo para almacenar cortes de calles desde la API de Transporte
    """
    CLOSURE_TYPE_CHOICES = [
        ('total', 'Corte Total'),
        ('parcial', 'Corte Parcial'),
        ('alternado', 'Tránsito Alternado'),
        ('restringido', 'Tránsito Restringido'),
    ]

    external_id = models.CharField(max_length=100, unique=True, verbose_name='ID Externo')
    name = models.CharField(max_length=255, verbose_name='Nombre del Corte')
    description = models.TextField(blank=True, verbose_name='Descripción')
    closure_type = models.CharField(max_length=20, choices=CLOSURE_TYPE_CHOICES, default='total', verbose_name='Tipo de Corte')

    # Ubicación geográfica
    lat = models.FloatField(verbose_name='Latitud')
    lon = models.FloatField(verbose_name='Longitud')
    address = models.CharField(max_length=255, blank=True, verbose_name='Dirección')

    # Geometría del corte (para cortes que afectan áreas)
    geometry = models.JSONField(null=True, blank=True, verbose_name='Geometría GeoJSON')

    # Fechas del corte
    start_date = models.DateTimeField(verbose_name='Fecha de Inicio')
    end_date = models.DateTimeField(null=True, blank=True, verbose_name='Fecha de Fin')

    # Información adicional
    cause = models.CharField(max_length=100, blank=True, verbose_name='Causa')
    affected_streets = models.JSONField(null=True, blank=True, verbose_name='Calles Afectadas')

    # Metadata
    is_active = models.BooleanField(default=True, verbose_name='Activo')
    last_updated = models.DateTimeField(auto_now=True, verbose_name='Última Actualización')
    created_at = models.DateTimeField(default=timezone.now, verbose_name='Creado en')

    class Meta:
        verbose_name = 'Corte de Calle'
        verbose_name_plural = 'Cortes de Calles'
        ordering = ['-start_date']
        indexes = [
            models.Index(fields=['is_active', 'lat', 'lon']),
            models.Index(fields=['start_date', 'end_date']),
        ]

    def __str__(self):
        return f"{self.name} - {self.closure_type}"

    def is_currently_active(self):
        """Verifica si el corte está actualmente activo"""
        now = timezone.now()
        return self.is_active and self.start_date <= now and (self.end_date is None or self.end_date >= now)


class ParkingSpot(models.Model):
    """
    Modelo para almacenar lugares de estacionamiento desde la API de Transporte
    """
    SPOT_TYPE_CHOICES = [
        ('street', 'Estacionamiento en Calle'),
        ('garage', 'Estacionamiento Cubierto'),
        ('lot', 'Playón de Estacionamiento'),
        ('emergency', 'Reservado para Emergencias'),
    ]

    external_id = models.CharField(max_length=100, unique=True, verbose_name='ID Externo')
    name = models.CharField(max_length=255, verbose_name='Nombre')
    spot_type = models.CharField(max_length=20, choices=SPOT_TYPE_CHOICES, default='street', verbose_name='Tipo')

    # Ubicación
    lat = models.FloatField(verbose_name='Latitud')
    lon = models.FloatField(verbose_name='Longitud')
    address = models.CharField(max_length=255, blank=True, verbose_name='Dirección')

    # Capacidad y disponibilidad
    total_spaces = models.PositiveIntegerField(default=1, verbose_name='Espacios Totales')
    available_spaces = models.PositiveIntegerField(default=0, verbose_name='Espacios Disponibles')

    # Información adicional
    is_paid = models.BooleanField(default=False, verbose_name='Pago Requerido')
    max_duration_hours = models.PositiveIntegerField(null=True, blank=True, verbose_name='Duración Máxima (horas)')
    restrictions = models.JSONField(null=True, blank=True, verbose_name='Restricciones')

    # Estado
    is_active = models.BooleanField(default=True, verbose_name='Activo')
    last_updated = models.DateTimeField(auto_now=True, verbose_name='Última Actualización')
    created_at = models.DateTimeField(default=timezone.now, verbose_name='Creado en')

    class Meta:
        verbose_name = 'Lugar de Estacionamiento'
        verbose_name_plural = 'Lugares de Estacionamiento'
        indexes = [
            models.Index(fields=['is_active', 'lat', 'lon']),
            models.Index(fields=['available_spaces']),
        ]

    def __str__(self):
        return f"{self.name} ({self.available_spaces}/{self.total_spaces} disponibles)"

    @property
    def occupancy_rate(self):
        """Calcula la tasa de ocupación"""
        if self.total_spaces == 0:
            return 0
        return ((self.total_spaces - self.available_spaces) / self.total_spaces) * 100


class TrafficCount(models.Model):
    """
    Modelo para almacenar conteos de tránsito desde la API de Transporte
    """
    COUNT_TYPE_CHOICES = [
        ('vehicle', 'Conteo de Vehículos'),
        ('speed', 'Velocidad Promedio'),
        ('occupancy', 'Ocupación de Vía'),
    ]

    external_id = models.CharField(max_length=100, unique=True, verbose_name='ID Externo')
    location_name = models.CharField(max_length=255, verbose_name='Ubicación')
    count_type = models.CharField(max_length=20, choices=COUNT_TYPE_CHOICES, default='vehicle', verbose_name='Tipo de Conteo')

    # Ubicación
    lat = models.FloatField(verbose_name='Latitud')
    lon = models.FloatField(verbose_name='Longitud')
    street_name = models.CharField(max_length=255, blank=True, verbose_name='Nombre de Calle')

    # Datos del conteo
    count_value = models.PositiveIntegerField(verbose_name='Valor del Conteo')
    unit = models.CharField(max_length=50, default='vehicles', verbose_name='Unidad')  # vehicles, km/h, percentage

    # Periodo del conteo
    timestamp = models.DateTimeField(verbose_name='Timestamp del Conteo')
    period_minutes = models.PositiveIntegerField(default=60, verbose_name='Periodo en Minutos')

    # Metadata
    data_source = models.CharField(max_length=100, blank=True, verbose_name='Fuente de Datos')
    last_updated = models.DateTimeField(auto_now=True, verbose_name='Última Actualización')
    created_at = models.DateTimeField(default=timezone.now, verbose_name='Creado en')

    class Meta:
        verbose_name = 'Conteo de Tránsito'
        verbose_name_plural = 'Conteos de Tránsito'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['timestamp', 'lat', 'lon']),
            models.Index(fields=['count_type', 'timestamp']),
        ]

    def __str__(self):
        return f"{self.location_name} - {self.count_value} {self.unit} ({self.timestamp})"


class TransportAlert(models.Model):
    """
    Modelo para almacenar alertas de transporte desde la API de Transporte
    """
    ALERT_TYPE_CHOICES = [
        ('closure', 'Corte de Calle'),
        ('accident', 'Accidente'),
        ('construction', 'Obra'),
        ('event', 'Evento'),
        ('weather', 'Clima'),
        ('other', 'Otro'),
    ]

    SEVERITY_CHOICES = [
        ('low', 'Baja'),
        ('medium', 'Media'),
        ('high', 'Alta'),
        ('critical', 'Crítica'),
    ]

    external_id = models.CharField(max_length=100, unique=True, verbose_name='ID Externo')
    title = models.CharField(max_length=255, verbose_name='Título')
    description = models.TextField(blank=True, verbose_name='Descripción')
    alert_type = models.CharField(max_length=20, choices=ALERT_TYPE_CHOICES, default='other', verbose_name='Tipo de Alerta')
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='medium', verbose_name='Severidad')

    # Ubicación
    lat = models.FloatField(null=True, blank=True, verbose_name='Latitud')
    lon = models.FloatField(null=True, blank=True, verbose_name='Longitud')
    address = models.CharField(max_length=255, blank=True, verbose_name='Dirección')

    # Fechas
    start_date = models.DateTimeField(verbose_name='Fecha de Inicio')
    end_date = models.DateTimeField(null=True, blank=True, verbose_name='Fecha de Fin')

    # Información adicional
    affected_routes = models.JSONField(null=True, blank=True, verbose_name='Rutas Afectadas')
    recommended_actions = models.JSONField(null=True, blank=True, verbose_name='Acciones Recomendadas')

    # Estado
    is_active = models.BooleanField(default=True, verbose_name='Activa')
    last_updated = models.DateTimeField(auto_now=True, verbose_name='Última Actualización')
    created_at = models.DateTimeField(default=timezone.now, verbose_name='Creado en')

    class Meta:
        verbose_name = 'Alerta de Transporte'
        verbose_name_plural = 'Alertas de Transporte'
        ordering = ['-start_date']
        indexes = [
            models.Index(fields=['is_active', 'severity']),
            models.Index(fields=['alert_type', 'start_date']),
        ]

    def __str__(self):
        return f"{self.title} ({self.severity})"

    def is_currently_active(self):
        """Verifica si la alerta está actualmente activa"""
        now = timezone.now()
        return self.is_active and self.start_date <= now and (self.end_date is None or self.end_date >= now)
