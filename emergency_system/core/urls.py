from django.urls import path
from .views import (
    home, create_emergency, emergency_list,
    process_emergency, emergency_detail, resolve_emergency,
    agentes_list, unidades_por_fuerza, hospitales_list, facilities_list, dashboard
)

urlpatterns = [
    path('', home, name='home'),
    path('create/', create_emergency, name='create_emergency'),
    path('list/', emergency_list, name='emergency_list'),
    path('process/<int:pk>/', process_emergency, name='process_emergency'),
    path('detalle/<int:pk>/', emergency_detail, name='emergency_detail'),
    path('resolver/<int:pk>/', resolve_emergency, name='resolve_emergency'),

    path('agentes/', agentes_list, name='agentes_list'),
    path('unidades/', unidades_por_fuerza, name='unidades_por_fuerza'),
    path('hospitales/', hospitales_list, name='hospitales_list'),
    path('instalaciones/', facilities_list, name='facilities_list'),
    path('dashboard/', dashboard, name='dashboard'),
]
