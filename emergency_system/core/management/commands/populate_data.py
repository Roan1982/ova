"""
Django management command to populate initial data for the emergency system.

Usage:
    python manage.py populate_data
    python manage.py populate_data --reset  # Clear existing data first
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
import random
import sys
from pathlib import Path

# Import the population script logic
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from scripts.populate_real_data import (
    ensure_forces,
    create_hospitals,
    populate_hospitals,
    create_facilities,
    populate_police_stations,
    create_parking_spots,
    create_vehicles,
    create_agents,
    create_emergencies,
    reset_data,
    RANDOM_SEED,
)


class Command(BaseCommand):
    help = 'Populate the database with initial hospitals, facilities, vehicles, agents, and emergencies'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Delete existing data before populating',
        )
        parser.add_argument(
            '--seed',
            type=int,
            default=RANDOM_SEED,
            help=f'Random seed for reproducible data (default: {RANDOM_SEED})',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('Starting data population...'))
        
        random.seed(options['seed'])
        
        with transaction.atomic():
            forces = ensure_forces()
            self.stdout.write(self.style.SUCCESS(f'✓ Forces ensured: {", ".join(forces.keys())}'))
            
            if options['reset']:
                self.stdout.write(self.style.WARNING('Resetting existing data...'))
                reset_data()
                self.stdout.write(self.style.SUCCESS('✓ Data reset complete'))
            
            hospitals = create_hospitals()
            self.stdout.write(self.style.SUCCESS(f'✓ Created {len(hospitals)} hospitals'))
            
            facilities = create_facilities(forces)
            self.stdout.write(self.style.SUCCESS(f'✓ Created {len(facilities)} facilities'))
            
            populate_police_stations(forces)
            self.stdout.write(self.style.SUCCESS('✓ Created police stations'))
            
            parking_spots = create_parking_spots()
            self.stdout.write(self.style.SUCCESS(f'✓ Created {len(parking_spots)} parking spots'))
            
            vehicles = create_vehicles(forces, hospitals, facilities)
            self.stdout.write(self.style.SUCCESS(f'✓ Created {len(vehicles)} vehicles'))
            
            agents = create_agents(forces, hospitals, facilities, vehicles)
            self.stdout.write(self.style.SUCCESS(f'✓ Created {len(agents)} agents'))
            
            emergencies = create_emergencies(forces)
            self.stdout.write(self.style.SUCCESS(f'✓ Created {len(emergencies)} emergencies'))
        
        self.stdout.write(self.style.SUCCESS('\n✅ Data population completed successfully!'))
        self.stdout.write(self.style.HTTP_INFO('You can now access the admin panel or start using the system.'))
