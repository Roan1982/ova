from django.contrib import admin
from .models import Force, Vehicle, Emergency

admin.site.register(Force)
admin.site.register(Vehicle)
admin.site.register(Emergency)
