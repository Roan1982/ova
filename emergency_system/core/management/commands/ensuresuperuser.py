"""
Django management command to create a superuser if it doesn't exist.

Usage:
    python manage.py ensuresuperuser
"""

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model


class Command(BaseCommand):
    help = 'Create a superuser if it does not exist'

    def handle(self, *args, **options):
        User = get_user_model()
        
        username = 'Admin'
        email = 'roaniamusic@gmail.com'
        password = 'Coordinacion2031'
        
        if User.objects.filter(username=username).exists():
            self.stdout.write(self.style.WARNING(f'Superuser "{username}" already exists.'))
        else:
            User.objects.create_superuser(username=username, email=email, password=password)
            self.stdout.write(self.style.SUCCESS(f'✅ Superuser "{username}" created successfully!'))
