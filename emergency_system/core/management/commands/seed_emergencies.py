from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from core.models import Emergency, Force, Vehicle

EMERGENCY_SCENARIOS = [
    {
        "description": "Robo a mano armada en banco con rehenes",
        "address": "Av. de Mayo 701, CABA",
        "location_lat": -34.6084,
        "location_lon": -58.3732,
    },
    {
        "description": "Choque múltiple con derrame de combustible en Autopista 25 de Mayo",
        "address": "Autopista 25 de Mayo y Perú, CABA",
        "location_lat": -34.6250,
        "location_lon": -58.3810,
    },
    {
        "description": "Explosiones y humo denso en depósito químico",
        "address": "Av. Vélez Sarsfield 450, Barracas",
        "location_lat": -34.6385,
        "location_lon": -58.3632,
    },
    {
        "description": "Paciente inconsciente por posible paro cardíaco en shopping",
        "address": "Av. Santa Fe 3253, Alto Palermo",
        "location_lat": -34.5886,
        "location_lon": -58.4104,
    },
    {
        "description": "Amenaza de bomba en estación de subte Catedral",
        "address": "San Martín 100, CABA",
        "location_lat": -34.6080,
        "location_lon": -58.3736,
    },
    {
        "description": "Fuga de gas reportada en edificio residencial con vecinos adentro",
        "address": "Av. Callao 1500, Recoleta",
        "location_lat": -34.5921,
        "location_lon": -58.3976,
    },
    {
        "description": "Peatón atropellado por moto con conductor que se dio a la fuga",
        "address": "Scalabrini Ortiz y Honduras, Palermo",
        "location_lat": -34.5805,
        "location_lon": -58.4242,
    },
    {
        "description": "Disturbios y enfrentamientos masivos a la salida de un partido",
        "address": "Brandsen 805, La Boca",
        "location_lat": -34.6356,
        "location_lon": -58.3649,
    },
    {
        "description": "Incendio en clínica privada con pacientes en terapia intensiva",
        "address": "Av. Córdoba 2351, CABA",
        "location_lat": -34.6030,
        "location_lon": -58.4010,
    },
]

DEFAULT_VEHICLES = [
    {
        "force": "Bomberos",
        "type": "Camión de Bomberos",
        "current_lat": -34.6037,
        "current_lon": -58.3816,
    },
    {
        "force": "Bomberos",
        "type": "Unidad Escalera",
        "current_lat": -34.6280,
        "current_lon": -58.3770,
    },
    {
        "force": "SAME",
        "type": "Ambulancia",
        "current_lat": -34.6097,
        "current_lon": -58.3916,
    },
    {
        "force": "SAME",
        "type": "Unidad de Terapia Intensiva",
        "current_lat": -34.5940,
        "current_lon": -58.4045,
    },
    {
        "force": "Policía",
        "type": "Patrulla",
        "current_lat": -34.6035,
        "current_lon": -58.3852,
    },
    {
        "force": "Policía",
        "type": "Moto",
        "current_lat": -34.6165,
        "current_lon": -58.3680,
    },
    {
        "force": "Tránsito",
        "type": "Móvil de Tránsito",
        "current_lat": -34.6010,
        "current_lon": -58.4125,
    },
]


class Command(BaseCommand):
    help = "Genera emergencias de ejemplo para probar el flujo con IA."

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Elimina emergencias existentes antes de generar las nuevas.",
        )
        parser.add_argument(
            "--with-vehicles",
            action="store_true",
            help="Asegura que existan vehículos base para todas las fuerzas.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        flush = options["flush"]
        ensure_vehicles = options["with_vehicles"]

        if flush:
            count = Emergency.objects.count()
            Emergency.objects.all().delete()
            self.stdout.write(self.style.WARNING(f"Se eliminaron {count} emergencias previas."))

        # Asegurar fuerzas básicas
        force_names = ["Bomberos", "SAME", "Policía", "Tránsito"]
        forces = {}
        for name in force_names:
            force, _ = Force.objects.get_or_create(name=name)
            forces[name] = force

        if ensure_vehicles:
            created_vehicles = 0
            for spec in DEFAULT_VEHICLES:
                force = forces[spec["force"]]
                vehicle = Vehicle.objects.filter(force=force, type=spec["type"]).first()
                if not vehicle:
                    Vehicle.objects.create(
                        force=force,
                        type=spec["type"],
                        current_lat=spec["current_lat"],
                        current_lon=spec["current_lon"],
                        status="disponible",
                    )
                    created_vehicles += 1
            if created_vehicles:
                self.stdout.write(self.style.SUCCESS(f"Vehículos asegurados: {created_vehicles} nuevos."))

        created_count = 0
        for payload in EMERGENCY_SCENARIOS:
            description = payload["description"]
            defaults = {
                "address": payload.get("address", ""),
                "location_lat": payload.get("location_lat"),
                "location_lon": payload.get("location_lon"),
                "status": "pendiente",
                "reported_at": timezone.now(),
            }
            emergency, created = Emergency.objects.get_or_create(
                description=description,
                defaults=defaults,
            )
            if created:
                created_count += 1

        total = Emergency.objects.count()
        self.stdout.write(
            self.style.SUCCESS(
                f"Emergencias nuevas: {created_count}. Total registradas: {total}."
            )
        )

        self.stdout.write(
            "Ingresá al panel web para procesar cada emergencia con la IA o dispara el flujo desde /ai-status/."
        )
