from django.contrib import admin
from .models import Force, Vehicle, Emergency, Agent, Hospital, EmergencyDispatch, Facility

admin.site.register(Force)
admin.site.register(Vehicle)
admin.site.register(Emergency)
admin.site.register(Agent)
admin.site.register(Hospital)
admin.site.register(EmergencyDispatch)
admin.site.register(Facility)
