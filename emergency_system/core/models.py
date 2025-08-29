from django.db import models
from django.utils import timezone
from django.conf import settings
from .ai import classify_emergency
from .llm import classify_with_ollama

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
        # Intentar clasificar con Ollama si está disponible
        result = classify_with_ollama(self.description) if getattr(settings, 'OLLAMA_BASE_URL', None) else None
        if result:
            code = result['codigo']
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
            tipo_val = result.get('tipo') or ''
            razones = reasons or []
            informe = (
                "Clasificación IA (Ollama)\n"
                f"- Tipo: {tipo_val}\n"
                f"- Código: {code}\n"
                f"- Puntaje: {score}\n"
                "- Razones:\n  - " + "\n  - ".join(razones)
            )
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
                # Intentar asignar vehículo disponible
                vehicle = Vehicle.objects.filter(force=force, status='disponible').first()
                if vehicle:
                    dispatch.vehicle = vehicle
                    vehicle.status = 'en_ruta'
                    vehicle.save()
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

    def process_ia(self):
        # Mantener compatibilidad: generar multi-despacho
        self.ensure_multi_dispatch()

    def resolve(self, notes=''):
        self.status = 'resuelta'
        self.resolved_at = timezone.now()
        # Liberar vehículos despachados
        for d in EmergencyDispatch.objects.filter(emergency=self):
            if d.vehicle:
                d.vehicle.status = 'disponible'
                d.vehicle.save()
            d.status = 'finalizado'
            d.save()
        # Agregar notas de resolución al informe
        if notes:
            self.resolution_notes = (self.resolution_notes or '') + f"\nResolución: {notes}"
        self.save(update_fields=['status', 'resolved_at', 'resolution_notes'])

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
