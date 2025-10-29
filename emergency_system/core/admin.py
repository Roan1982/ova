from django.contrib import admin
from .models import Force, Vehicle, Emergency, Agent, Hospital, EmergencyDispatch, Facility

# Customize admin site headers
admin.site.site_header = "Sistema de Emergencias CABA"
admin.site.site_title = "Admin OVA"
admin.site.index_title = "Administración del Sistema"

admin.site.register(Force)
admin.site.register(Vehicle)
admin.site.register(Emergency)
admin.site.register(Agent)
admin.site.register(Hospital)
admin.site.register(EmergencyDispatch)
admin.site.register(Facility)
