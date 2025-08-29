from django.urls import path
from .views import (
    home, create_emergency, emergency_list,
    process_emergency, emergency_detail, resolve_emergency,
    agentes_list, unidades_por_fuerza, hospitales_list, facilities_list, dashboard,
    ai_status_view, calculate_routes_api, assign_optimal_resources, real_time_tracking,
    activate_green_wave_api, traffic_status_api, redistribute_resources_api,
    route_details_api
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
    path('ai-status/', ai_status_view, name='ai_status'),
    
    # APIs de ruteo
    path('api/routes/<int:emergency_id>/', calculate_routes_api, name='calculate_routes_api'),
    path('calculate-routes/<int:emergency_id>/', calculate_routes_api, name='recalculate_route'),
    path('route-details/<int:emergency_id>/', route_details_api, name='route_details_api'),
    path('api/assign/<int:emergency_id>/', assign_optimal_resources, name='assign_optimal_resources'),
    path('api/tracking/', real_time_tracking, name='real_time_tracking'),
    
    # APIs de onda verde y tráfico
    path('api/green-wave/<int:emergency_id>/', activate_green_wave_api, name='activate_green_wave_api'),
    path('api/traffic-status/', traffic_status_api, name='traffic_status_api'),
    path('api/redistribute/', redistribute_resources_api, name='redistribute_resources_api'),
]
