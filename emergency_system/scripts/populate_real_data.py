"""Fast offline data population for the emergency system.

This script seeds hospitals, facilities, vehicles, agents and emergencies using
fully offline static datasets so the environment is ready within seconds. It
is invoked automatically from ``run_system.bat`` right after running Django
migrations.  The goal is to provide a rich realistic dataset without relying on
slow external geocoding services.
"""

from __future__ import annotations

import os
import random
import sys
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import django
from django.db import transaction
from django.utils import timezone

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "emergency_app.settings")
django.setup()

from core.models import (  # noqa: E402  (import after django.setup)
    Agent,
    CalculatedRoute,
    Emergency,
    EmergencyDispatch,
    Facility,
    Force,
    Hospital,
    ParkingSpot,
    Vehicle,
)

# ---------------------------------------------------------------------------
# Configuration flags
# ---------------------------------------------------------------------------
RESET = os.environ.get("EMERGENCY_RESET", "1") != "0"
RANDOM_SEED = int(os.environ.get("EMERGENCY_RANDOM_SEED", "20240602"))

# ---------------------------------------------------------------------------
# Static datasets
# ---------------------------------------------------------------------------
HOSPITAL_DATA: Sequence[Dict[str, object]] = [
    {
        "name": "Hospital Pedro de Elizalde",
        "address": "Manuel A. Montes de Oca 40",
        "lat": -34.6257,
        "lon": -58.3831,
        "total_beds": 292,
        "occupied_beds": 234,
    },
    {
        "name": "Hospital Braulio A. Moyano",
        "address": "Brandsen 2570",
        "lat": -34.6315,
        "lon": -58.3694,
        "total_beds": 1500,
        "occupied_beds": 1275,
    },
    {
        "name": "Hospital Borda (H. Enrique A. Borda)",
        "address": "Av. Caseros 3245",
        "lat": -34.6244,
        "lon": -58.3838,
        "total_beds": 800,
        "occupied_beds": 680,
    },
    {
        "name": "Hospital Ramos Mejía",
        "address": "Gral. Urquiza 609",
        "lat": -34.6080,
        "lon": -58.4047,
        "total_beds": 600,
        "occupied_beds": 510,
    },
    {
        "name": "Hospital Ricardo Gutiérrez",
        "address": "Gallo 1330",
        "lat": -34.5989,
        "lon": -58.4103,
        "total_beds": 300,
        "occupied_beds": 255,
    },
    {
        "name": "Hospital de Clínicas \"José de San Martín\" (UBA)",
        "address": "Av. Córdoba 2351 / Junín 956",
        "lat": -34.5996,
        "lon": -58.3931,
        "total_beds": 400,
        "occupied_beds": 340,
    },
    {
        "name": "Hospital Muñiz",
        "address": "Uspallata 2272",
        "lat": -34.6469,
        "lon": -58.3912,
        "total_beds": 200,
        "occupied_beds": 170,
    },
    {
        "name": "Hospital Rivadavia",
        "address": "Av. General Las Heras 2670",
        "lat": -34.5867,
        "lon": -58.3989,
        "total_beds": 400,
        "occupied_beds": 340,
    },
    {
        "name": "Hospital Fernández",
        "address": "Av. Cerviño 3356",
        "lat": -34.5864,
        "lon": -58.4092,
        "total_beds": 300,
        "occupied_beds": 255,
    },
    {
        "name": "Hospital Pirovano",
        "address": "Monroe 3555",
        "lat": -34.5632,
        "lon": -58.4701,
        "total_beds": 250,
        "occupied_beds": 213,
    },
    {
        "name": "Hospital Argerich",
        "address": "Pi y Margall 750",
        "lat": -34.6286,
        "lon": -58.3644,
        "total_beds": 430,
        "occupied_beds": 366,
    },
    {
        "name": "Hospital Álvarez",
        "address": "Dr. Juan Felipe Aranguren 2701",
        "lat": -34.6204,
        "lon": -58.4622,
        "total_beds": 350,
        "occupied_beds": 298,
    },
    {
        "name": "Hospital Tornú",
        "address": "Combatientes de Malvinas 3002",
        "lat": -34.5769,
        "lon": -58.4438,
        "total_beds": 200,
        "occupied_beds": 170,
    },
    {
        "name": "Hospital Penna",
        "address": "Pedro Chutro 3380",
        "lat": -34.6416,
        "lon": -58.4049,
        "total_beds": 210,
        "occupied_beds": 179,
    },
    {
        "name": "Hospital Alvear (Hospital de Emergencias Psiquiátricas 'Marcelo T. Alvear')",
        "address": "Nueva York 3952 (zona)",
        "lat": -34.6065,
        "lon": -58.4801,
        "total_beds": 150,
        "occupied_beds": 128,
    },
    {
        "name": "Hospital Durand",
        "address": "Díaz Vélez 5044",
        "lat": -34.6107,
        "lon": -58.4358,
        "total_beds": 338,
        "occupied_beds": 287,
    },
    {
        "name": "Hospital Piñero",
        "address": "Av. Varela 1301",
        "lat": -34.6389,
        "lon": -58.4547,
        "total_beds": 400,
        "occupied_beds": 340,
    },
    {
        "name": "Hospital Santa Lucía (Oftalmología)",
        "address": "Av. Monserrat / San Cristóbal (sede)",
        "lat": -34.6170,
        "lon": -58.3836,
        "total_beds": 50,
        "occupied_beds": 43,
    },
    {
        "name": "Maternidad Sardá",
        "address": "Av. Belgrano y Combate de los Pozos (sede)",
        "lat": -34.6332,
        "lon": -58.4057,
        "total_beds": 100,
        "occupied_beds": 85,
    },
    {
        "name": "Hospital Zubizarreta",
        "address": "Nueva York 3952",
        "lat": -34.6001,
        "lon": -58.5140,
        "total_beds": 200,
        "occupied_beds": 170,
    },
    {
        "name": "Hospital Udaondo (Gastroenterología)",
        "address": "Combate de los Pozos / Parque Patricios (sede)",
        "lat": -34.6280,
        "lon": -58.4025,
        "total_beds": 80,
        "occupied_beds": 68,
    },
    {
        "name": "Hospital Militar Central",
        "address": "Av. del Libertador / zona Palermo",
        "lat": -34.5878,
        "lon": -58.3899,
        "total_beds": 200,
        "occupied_beds": 170,
    },
    {
        "name": "Hospital Santojanni",
        "address": "Pilar 950",
        "lat": -34.6370,
        "lon": -58.5092,
        "total_beds": 400,
        "occupied_beds": 340,
    },
    {
        "name": "Hospital Pedro Lagleyze (Oftalmológico)",
        "address": "Av. San Martín / Villa Gral. Mitre (sede)",
        "lat": -34.5950,
        "lon": -58.4720,
        "total_beds": 60,
        "occupied_beds": 51,
    },
    {
        "name": "Hospital Churruca-Visca",
        "address": "Av. Caseros y zona Parque Patricios",
        "lat": -34.6292,
        "lon": -58.3850,
        "total_beds": 150,
        "occupied_beds": 128,
    },
    {
        "name": "Hospital Naval Central",
        "address": "Av. Díaz Vélez / Parque Centenario (sede)",
        "lat": -34.6160,
        "lon": -58.4210,
        "total_beds": 200,
        "occupied_beds": 170,
    },
    {
        "name": "Hospital Vélez Sarsfield",
        "address": "Av. Lope de Vega 1485",
        "lat": -34.6123,
        "lon": -58.5081,
        "total_beds": 120,
        "occupied_beds": 102,
    },
    {
        "name": "Hospital Aeronáutico Central",
        "address": "Nueva Pompeya (sede)",
        "lat": -34.6480,
        "lon": -58.3980,
        "total_beds": 100,
        "occupied_beds": 85,
    },
    {
        "name": "Hospital Tobar García (Neuropsiquiatría infantil)",
        "address": "Brandsen / Barracas (sede)",
        "lat": -34.6320,
        "lon": -58.3720,
        "total_beds": 64,
        "occupied_beds": 54,
    },
    {
        "name": "Hospital Garrahan (pediatría nacional)",
        "address": "Combate de los Pozos 1881",
        "lat": -34.6286,
        "lon": -58.4011,
        "total_beds": 619,
        "occupied_beds": 526,
    },
    {
        "name": "Hospital Cecilia Grierson",
        "address": "Av. Fernández de la Cruz 4402",
        "lat": -34.7073,
        "lon": -58.4531,
        "total_beds": 20,
        "occupied_beds": 17,
    },
    {
        "name": "Hospital Municipal de Oncología Marie Curie",
        "address": "(sede)",
        "lat": -34.6270,
        "lon": -58.4040,
        "total_beds": 100,
        "occupied_beds": 85,
    },
]

# Static dataset for hospitals in Buenos Aires
HOSPITALS = [
    {"name": "Hospital Pedro de Elizalde", "address": "Manuel A. Montes de Oca 40", "lat": -34.6257, "lon": -58.3831, "capacity": 292, "occupied_beds": None},
    {"name": "Hospital Braulio A. Moyano", "address": "Brandsen 2570", "lat": -34.6315, "lon": -58.3694, "capacity": 1500, "occupied_beds": None},
    {"name": "Hospital Borda (H. Enrique A. Borda)", "address": "Av. Caseros 3245", "lat": -34.6244, "lon": -58.3838, "capacity": None, "occupied_beds": None},
    {"name": "Hospital Ramos Mejía", "address": "Gral. Urquiza 609", "lat": -34.6080, "lon": -58.4047, "capacity": None, "occupied_beds": None},
    {"name": "Hospital Ricardo Gutiérrez", "address": "Gallo 1330", "lat": -34.5989, "lon": -58.4103, "capacity": None, "occupied_beds": None},
    {"name": "Hospital de Clínicas \"José de San Martín\" (UBA)", "address": "Av. Córdoba 2351 / Junín 956", "lat": -34.5996, "lon": -58.3931, "capacity": 400, "occupied_beds": None},
    {"name": "Hospital Muñiz", "address": "Uspallata 2272", "lat": -34.6469, "lon": -58.3912, "capacity": None, "occupied_beds": None},
    {"name": "Hospital Rivadavia", "address": "Av. General Las Heras 2670", "lat": -34.5867, "lon": -58.3989, "capacity": None, "occupied_beds": None},
    {"name": "Hospital Fernández", "address": "Av. Cerviño 3356", "lat": -34.5864, "lon": -58.4092, "capacity": 300, "occupied_beds": None},
    {"name": "Hospital Pirovano", "address": "Monroe 3555", "lat": -34.5632, "lon": -58.4701, "capacity": None, "occupied_beds": None},
    {"name": "Hospital Argerich", "address": "Pi y Margall 750", "lat": -34.6286, "lon": -58.3644, "capacity": 430, "occupied_beds": None},
    {"name": "Hospital Álvarez", "address": "Dr. Juan Felipe Aranguren 2701", "lat": -34.6204, "lon": -58.4622, "capacity": None, "occupied_beds": None},
    {"name": "Hospital Tornú", "address": "Combatientes de Malvinas 3002", "lat": -34.5769, "lon": -58.4438, "capacity": None, "occupied_beds": None},
    {"name": "Hospital Penna", "address": "Pedro Chutro 3380", "lat": -34.6416, "lon": -58.4049, "capacity": 210, "occupied_beds": None},
    {"name": "Hospital Alvear (Hospital de Emergencias Psiquiátricas 'Marcelo T. Alvear')", "address": "Nueva York 3952 (zona)", "lat": -34.6065, "lon": -58.4801, "capacity": None, "occupied_beds": None},
    {"name": "Hospital Durand", "address": "Díaz Vélez 5044", "lat": -34.6107, "lon": -58.4358, "capacity": 338, "occupied_beds": None},
    {"name": "Hospital Piñero", "address": "Av. Varela 1301", "lat": -34.6389, "lon": -58.4547, "capacity": 400, "occupied_beds": None},
    {"name": "Hospital Santa Lucía (Oftalmología)", "address": "Av. Monserrat / San Cristóbal (sede)", "lat": -34.6170, "lon": -58.3836, "capacity": None, "occupied_beds": None},
    {"name": "Maternidad Sardá", "address": "Av. Belgrano y Combate de los Pozos (sede)", "lat": -34.6332, "lon": -58.4057, "capacity": None, "occupied_beds": None},
    {"name": "Hospital Zubizarreta", "address": "Nueva York 3952", "lat": -34.6001, "lon": -58.5140, "capacity": None, "occupied_beds": None},
    {"name": "Hospital Udaondo (Gastroenterología)", "address": "Combate de los Pozos / Parque Patricios (sede)", "lat": -34.6280, "lon": -58.4025, "capacity": None, "occupied_beds": None},
    {"name": "Hospital Militar Central", "address": "Av. del Libertador / zona Palermo", "lat": -34.5878, "lon": -58.3899, "capacity": None, "occupied_beds": None},
    {"name": "Hospital Santojanni", "address": "Pilar 950", "lat": -34.6370, "lon": -58.5092, "capacity": 400, "occupied_beds": None},
    {"name": "Hospital Pedro Lagleyze (Oftalmológico)", "address": "Av. San Martín / Villa Gral. Mitre (sede)", "lat": -34.5950, "lon": -58.4720, "capacity": None, "occupied_beds": None},
    {"name": "Hospital Churruca-Visca", "address": "Av. Caseros y zona Parque Patricios", "lat": -34.6292, "lon": -58.3850, "capacity": None, "occupied_beds": None},
    {"name": "Hospital Naval Central", "address": "Av. Díaz Vélez / Parque Centenario (sede)", "lat": -34.6160, "lon": -58.4210, "capacity": 400, "occupied_beds": None},
    {"name": "Hospital Vélez Sarsfield", "address": "Av. Lope de Vega 1485", "lat": -34.6123, "lon": -58.5081, "capacity": 120, "occupied_beds": None},
    {"name": "Hospital Aeronáutico Central", "address": "Nueva Pompeya (sede)", "lat": -34.6480, "lon": -58.3980, "capacity": None, "occupied_beds": None},
    {"name": "Hospital Tobar García (Neuropsiquiatría infantil)", "address": "Brandsen / Barracas (sede)", "lat": -34.6320, "lon": -58.3720, "capacity": 64, "occupied_beds": None},
    {"name": "Hospital Garrahan (pediatría nacional)", "address": "Combate de los Pozos 1881", "lat": -34.6286, "lon": -58.4011, "capacity": 619, "occupied_beds": None},
    {"name": "Hospital Cecilia Grierson", "address": "Av. Fernández de la Cruz 4402", "lat": -34.7073, "lon": -58.4531, "capacity": 20, "occupied_beds": None},
    {"name": "Hospital Municipal de Oncología Marie Curie", "address": "(sede)", "lat": -34.6270, "lon": -58.4040, "capacity": None, "occupied_beds": None},
]

FACILITY_DATA: Dict[str, Sequence[Dict[str, object]]] = {
    "Bomberos": [
        {
            "name": "Cuartel Recoleta",
            "kind": "cuartel",
            "address": "Av. Callao 1240, Recoleta",
            "lat": -34.5962,
            "lon": -58.3948,
        },
        {
            "name": "Cuartel Chacarita",
            "kind": "cuartel",
            "address": "Av. Corrientes 6270, Chacarita",
            "lat": -34.5968,
            "lon": -58.4497,
        },
        {
            "name": "Cuartel Barracas",
            "kind": "cuartel",
            "address": "Av. Montes de Oca 151, Barracas",
            "lat": -34.6385,
            "lon": -58.3682,
        },
        {
            "name": "Cuartel Parque Patricios",
            "kind": "cuartel",
            "address": "Av. Caseros 2500, Parque Patricios",
            "lat": -34.6347,
            "lon": -58.3964,
        },
        {
            "name": "Cuartel Mataderos",
            "kind": "cuartel",
            "address": "Av. Directorio 6200, Mataderos",
            "lat": -34.6541,
            "lon": -58.5069,
        },
    ],
    "Policía": [
        {
            "name": "Comisaría 1 Retiro",
            "kind": "comisaria",
            "address": "Av. Antártida Argentina 1211, Retiro",
            "lat": -34.5935,
            "lon": -58.3704,
        },
        {
            "name": "Comisaría 5 Almagro",
            "kind": "comisaria",
            "address": "Av. Medrano 473, Almagro",
            "lat": -34.6049,
            "lon": -58.4202,
        },
        {
            "name": "Comisaría 7 Flores",
            "kind": "comisaria",
            "address": "Av. Rivadavia 7600, Flores",
            "lat": -34.6337,
            "lon": -58.4638,
        },
        {
            "name": "Comisaría 13 Belgrano",
            "kind": "comisaria",
            "address": "Echeverría 4746, Belgrano",
            "lat": -34.5676,
            "lon": -58.4574,
        },
        {
            "name": "Comisaría 14 Palermo",
            "kind": "comisaria",
            "address": "Av. Coronel Díaz 2160, Palermo",
            "lat": -34.5889,
            "lon": -58.4058,
        },
        {
            "name": "Comisaría 35 Lugano",
            "kind": "comisaria",
            "address": "Av. Fernández de la Cruz 5600, Villa Lugano",
            "lat": -34.6693,
            "lon": -58.4566,
        },
    ],
    "Tránsito": [
        {
            "name": "Base Tránsito Parque Rivadavia",
            "kind": "base_transito",
            "address": "Av. Rivadavia 4900, Caballito",
            "lat": -34.6096,
            "lon": -58.4335,
        },
        {
            "name": "Base Tránsito 9 de Julio",
            "kind": "base_transito",
            "address": "Av. 9 de Julio y Av. de Mayo",
            "lat": -34.6070,
            "lon": -58.3786,
        },
        {
            "name": "Base Tránsito General Paz",
            "kind": "base_transito",
            "address": "Av. Gral. Paz 14000, Saavedra",
            "lat": -34.5360,
            "lon": -58.4948,
        },
        {
            "name": "Base Tránsito Pompeya",
            "kind": "base_transito",
            "address": "Av. Sáenz 1000, Nueva Pompeya",
            "lat": -34.6536,
            "lon": -58.4109,
        },
    ],
}

PARKING_DATA: Sequence[Dict[str, object]] = [
    {
        "external_id": "parking_001",
        "name": "Estacionamiento Plaza de Mayo",
        "spot_type": "lot",
        "address": "Av. Hipólito Yrigoyen 200, Monserrat",
        "lat": -34.6083,
        "lon": -58.3712,
        "total_spaces": 50,
        "available_spaces": 35,
        "is_paid": True,
        "max_duration_hours": 2,
    },
    {
        "external_id": "parking_002",
        "name": "Parking Recoleta",
        "spot_type": "garage",
        "address": "Av. Alvear 1800, Recoleta",
        "lat": -34.5896,
        "lon": -58.3931,
        "total_spaces": 80,
        "available_spaces": 60,
        "is_paid": True,
        "max_duration_hours": 4,
    },
    {
        "external_id": "parking_003",
        "name": "Estacionamiento Palermo Soho",
        "spot_type": "street",
        "address": "Av. Córdoba 4300, Palermo",
        "lat": -34.5857,
        "lon": -58.4301,
        "total_spaces": 40,
        "available_spaces": 25,
        "is_paid": False,
        "max_duration_hours": 1,
    },
    {
        "external_id": "parking_004",
        "name": "Parking Caballito",
        "spot_type": "lot",
        "address": "Av. Rivadavia 5000, Caballito",
        "lat": -34.6153,
        "lon": -58.4335,
        "total_spaces": 60,
        "available_spaces": 45,
        "is_paid": True,
        "max_duration_hours": 3,
    },
    {
        "external_id": "parking_005",
        "name": "Estacionamiento Belgrano",
        "spot_type": "street",
        "address": "Av. Cabildo 2000, Belgrano",
        "lat": -34.5619,
        "lon": -58.4503,
        "total_spaces": 45,
        "available_spaces": 30,
        "is_paid": False,
        "max_duration_hours": 2,
    },
    {
        "external_id": "parking_006",
        "name": "Parking Flores",
        "spot_type": "lot",
        "address": "Av. Rivadavia 7000, Flores",
        "lat": -34.6337,
        "lon": -58.4638,
        "total_spaces": 55,
        "available_spaces": 40,
        "is_paid": True,
        "max_duration_hours": 2,
    },
    {
        "external_id": "parking_007",
        "name": "Estacionamiento Villa Urquiza",
        "spot_type": "street",
        "address": "Av. Triunvirato 4000, Villa Urquiza",
        "lat": -34.5734,
        "lon": -58.4933,
        "total_spaces": 35,
        "available_spaces": 20,
        "is_paid": False,
        "max_duration_hours": 1,
    },
    {
        "external_id": "parking_008",
        "name": "Parking Boedo",
        "spot_type": "street",
        "address": "Av. San Juan 3000, Boedo",
        "lat": -34.6243,
        "lon": -58.4028,
        "total_spaces": 40,
        "available_spaces": 28,
        "is_paid": True,
        "max_duration_hours": 2,
    },
    {
        "external_id": "parking_009",
        "name": "Estacionamiento Almagro",
        "spot_type": "lot",
        "address": "Av. Medrano 500, Almagro",
        "lat": -34.6049,
        "lon": -58.4202,
        "total_spaces": 50,
        "available_spaces": 38,
        "is_paid": False,
        "max_duration_hours": 3,
    },
    {
        "external_id": "parking_010",
        "name": "Parking Parque Patricios",
        "spot_type": "lot",
        "address": "Av. Caseros 2500, Parque Patricios",
        "lat": -34.6347,
        "lon": -58.3964,
        "total_spaces": 65,
        "available_spaces": 50,
        "is_paid": True,
        "max_duration_hours": 4,
    },
    # Additional parking spots closer to demo emergency location
    {
        "external_id": "parking_demo_001",
        "name": "Estacionamiento Obelisco",
        "spot_type": "street",
        "address": "Av. 9 de Julio 1234",
        "lat": -34.6037,
        "lon": -58.3816,
        "total_spaces": 100,
        "available_spaces": 45,
        "is_paid": True,
        "max_duration_hours": 2,
    },
    {
        "external_id": "parking_demo_002",
        "name": "Estacionamiento Tribunales",
        "spot_type": "garage",
        "address": "Talcahuano 550",
        "lat": -34.6018,
        "lon": -58.3851,
        "total_spaces": 50,
        "available_spaces": 20,
        "is_paid": False,
        "max_duration_hours": 8,
    },
]

EMERGENCY_DATA: Sequence[Dict[str, object]] = [
    {
        "description": "Incendio estructural con personas atrapadas en edificio residencial",
        "address": "Guatemala 4500, Palermo",
        "lat": -34.5869,
        "lon": -58.4251,
        "code": "rojo",
        "force": "Bomberos",
        "minutes_ago": 25,
    },
    {
        "description": "Accidente múltiple con lesionados sobre Av. 9 de Julio",
        "address": "Av. 9 de Julio y Lima",
        "lat": -34.6117,
        "lon": -58.3816,
        "code": "rojo",
        "force": "SAME",
        "minutes_ago": 15,
    },
    {
        "description": "Manifestación con corte parcial de tránsito en Plaza de Mayo",
        "address": "Plaza de Mayo, Microcentro",
        "lat": -34.6083,
        "lon": -58.3712,
        "code": "amarillo",
        "force": "Tránsito",
        "minutes_ago": 50,
    },
    {
        "description": "Robo a mano armada en local comercial, sospechosos armados",
        "address": "Av. Cabildo 2200, Belgrano",
        "lat": -34.5619,
        "lon": -58.4503,
        "code": "rojo",
        "force": "Policía",
        "minutes_ago": 40,
    },
    {
        "description": "Fuga de gas reportada por vecinos, olor intenso en la zona",
        "address": "Virrey Arredondo 2500, Colegiales",
        "lat": -34.5714,
        "lon": -58.4512,
        "code": "amarillo",
        "force": "Bomberos",
        "minutes_ago": 60,
    },
    {
        "description": "Emergencia médica: adulto inconsciente en la vía pública",
        "address": "Av. Rivadavia 6500, Flores",
        "lat": -34.6216,
        "lon": -58.4451,
        "code": "amarillo",
        "force": "SAME",
        "minutes_ago": 18,
    },
    {
        "description": "Choque entre colectivo y automóvil con derrame de combustible",
        "address": "Av. San Juan 3200, Boedo",
        "lat": -34.6243,
        "lon": -58.4028,
        "code": "rojo",
        "force": "Bomberos",
        "minutes_ago": 12,
    },
    {
        "description": "Corte total de la autopista por vuelco de camión",
        "address": "Acceso Oeste km 12, Liniers",
        "lat": -34.6412,
        "lon": -58.5051,
        "code": "amarillo",
        "force": "Tránsito",
        "minutes_ago": 75,
    },
    {
        "description": "Ruidos de disparos y pelea entre bandas en espacio público",
        "address": "Plaza Martín Fierro, San Cristóbal",
        "lat": -34.6234,
        "lon": -58.3987,
        "code": "rojo",
        "force": "Policía",
        "minutes_ago": 90,
    },
    {
        "description": "Incendio de vehículo estacionado sin personas atrapadas",
        "address": "Av. Triunvirato 4400, Villa Urquiza",
        "lat": -34.5734,
        "lon": -58.4933,
        "code": "verde",
        "force": "Bomberos",
        "minutes_ago": 35,
    },
    {
        "description": "Persona desorientada necesita asistencia para regresar a su hogar",
        "address": "Parque Centenario, Caballito",
        "lat": -34.6053,
        "lon": -58.4366,
        "code": "verde",
        "force": "Policía",
        "minutes_ago": 20,
    },
    {
        "description": "Colapso de árbol afecta tendido eléctrico sin heridos",
        "address": "Av. Libertador 7500, Núñez",
        "lat": -34.5450,
        "lon": -58.4621,
        "code": "amarillo",
        "force": "Tránsito",
        "minutes_ago": 55,
    },
]

FIRST_NAMES: Sequence[str] = [
    "Juan",
    "María",
    "Carlos",
    "Lucía",
    "Pedro",
    "Ana",
    "Diego",
    "Sofía",
    "Martín",
    "Laura",
    "Pablo",
    "Valentina",
    "Florencia",
    "Santiago",
    "Julieta",
    "Agustín",
    "Carolina",
    "Federico",
    "Camila",
    "Nicolás",
]

LAST_NAMES: Sequence[str] = [
    "Gómez",
    "Fernández",
    "Pérez",
    "Rodríguez",
    "López",
    "Martínez",
    "Sánchez",
    "Díaz",
    "Álvarez",
    "Romero",
    "Torres",
    "Flores",
    "Acosta",
    "Herrera",
    "Silva",
    "Castro",
    "Molina",
    "Arias",
    "Vega",
    "Suárez",
]

ROLES: Dict[str, Sequence[str]] = {
    "SAME": [
        "Médico de guardia",
        "Paramédico",
        "Chofer",
        "Coordinador prehospitalario",
    ],
    "Bomberos": [
        "Jefe de dotación",
        "Rescatista",
        "Operador de escalera",
        "Especialista en materiales peligrosos",
    ],
    "Policía": [
        "Oficial de patrulla",
        "Investigador",
        "Jefe de turno",
        "Operador de comunicaciones",
    ],
    "Tránsito": [
        "Inspector",
        "Agente de control",
        "Coordinador de operativo",
        "Motociclista",
    ],
}

# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def jitter(value: float, meters: float) -> float:
    """Return ``value`` offset by roughly ``meters`` metres."""

    # 1 degree of latitude ~= 111km. We keep it simple for this seed dataset.
    delta = (meters / 111_000.0) * (random.random() - 0.5) * 2
    return value + delta


def pick_name() -> str:
    return f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"


def random_status(force_name: str) -> str:
    base = ["disponible", "disponible", "en_ruta", "ocupado"]
    if force_name == "Tránsito":
        base.append("fuera_servicio")
    elif force_name == "Bomberos":
        base.append("en_ruta")
    return random.choice(base)


# ---------------------------------------------------------------------------
# Core creation helpers
# ---------------------------------------------------------------------------

def ensure_forces() -> Dict[str, Force]:
    names = ["SAME", "Bomberos", "Policía", "Tránsito"]
    forces: Dict[str, Force] = {}
    for name in names:
        force, _ = Force.objects.get_or_create(name=name)
        forces[name] = force
    return forces


def reset_data() -> None:
    if not RESET:
        return

    print("Limpiando datos previos…")
    EmergencyDispatch.objects.all().delete()
    CalculatedRoute.objects.all().delete()
    Emergency.objects.all().delete()
    Agent.objects.all().delete()
    Vehicle.objects.all().delete()
    Facility.objects.all().delete()
    Hospital.objects.all().delete()
    ParkingSpot.objects.all().delete()


def create_hospitals() -> List[Hospital]:
    hospitals_data = []
    for data in HOSPITAL_DATA:
        hospital_data = data.copy()
        if hospital_data["occupied_beds"] is None:
            hospital_data["occupied_beds"] = 0
        if hospital_data["total_beds"] is None:
            hospital_data["total_beds"] = 0
        hospitals_data.append(hospital_data)
    Hospital.objects.bulk_create([Hospital(**data) for data in hospitals_data])
    hospitals = list(Hospital.objects.order_by("name"))
    print(f"Hospitales creados: {len(hospitals)}")
    return hospitals


def populate_hospitals():
    hospitals = [
        Hospital(
            name=hospital["name"],
            address=hospital["address"],
            lat=hospital["lat"],
            lon=hospital["lon"],
            capacity=hospital["capacity"],
            occupied_beds=hospital["occupied_beds"],
        )
        for hospital in HOSPITALS
    ]
    Hospital.objects.bulk_create(hospitals)
    print(f"Created {len(hospitals)} hospitals.")


def create_facilities(forces: Dict[str, Force]) -> List[Facility]:
    facilities: List[Facility] = []
    for force_name, entries in FACILITY_DATA.items():
        force = forces[force_name]
        for data in entries:
            facilities.append(
                Facility(
                    name=data["name"],
                    kind=data["kind"],
                    force=force,
                    address=data["address"],
                    lat=data["lat"],
                    lon=data["lon"],
                )
            )
    Facility.objects.bulk_create(facilities)
    persisted = list(Facility.objects.order_by("name"))
    print(f"Instalaciones creadas: {len(persisted)}")
    return persisted


def create_parking_spots() -> List[ParkingSpot]:
    parking_spots: List[ParkingSpot] = []
    for data in PARKING_DATA:
        parking_spots.append(
            ParkingSpot(
                external_id=data["external_id"],
                name=data["name"],
                spot_type=data["spot_type"],
                address=data["address"],
                lat=data["lat"],
                lon=data["lon"],
                total_spaces=data["total_spaces"],
                available_spaces=data["available_spaces"],
                is_paid=data["is_paid"],
                max_duration_hours=data["max_duration_hours"],
            )
        )
    ParkingSpot.objects.bulk_create(parking_spots)
    persisted = list(ParkingSpot.objects.order_by("name"))
    print(f"Estacionamientos creados: {len(persisted)}")
    return persisted


def create_vehicles(
    forces: Dict[str, Force],
    hospitals: Sequence[Hospital],
    facilities: Sequence[Facility],
) -> List[Vehicle]:
    vehicles: List[Vehicle] = []

    same = forces["SAME"]
    for hospital in hospitals:
        count = random.randint(4, 7)
        for _ in range(count):
            vehicles.append(
                Vehicle(
                    force=same,
                    type="Ambulancia",
                    status=random.choice(["disponible", "en_ruta"]),
                    current_lat=jitter(hospital.lat or -34.6, 80),
                    current_lon=jitter(hospital.lon or -58.4, 80),
                    home_facility=None,
                )
            )

    facilities_by_kind: Dict[str, List[Facility]] = {}
    for facility in facilities:
        facilities_by_kind.setdefault(facility.kind, []).append(facility)

    for facility in facilities_by_kind.get("cuartel", []):
        for _ in range(random.randint(3, 6)):
            vehicles.append(
                Vehicle(
                    force=forces["Bomberos"],
                    type="Camión de Bomberos",
                    status=random.choice(["disponible", "en_ruta", "ocupado"]),
                    current_lat=jitter(facility.lat or -34.6, 60),
                    current_lon=jitter(facility.lon or -58.4, 60),
                    home_facility=facility,
                )
            )

    for facility in facilities_by_kind.get("comisaria", []):
        for _ in range(random.randint(4, 8)):
            vehicles.append(
                Vehicle(
                    force=forces["Policía"],
                    type="Patrulla",
                    status=random.choice(["disponible", "en_ruta", "ocupado"]),
                    current_lat=jitter(facility.lat or -34.6, 60),
                    current_lon=jitter(facility.lon or -58.4, 60),
                    home_facility=facility,
                )
            )

    for facility in facilities_by_kind.get("base_transito", []):
        for _ in range(random.randint(4, 7)):
            vehicles.append(
                Vehicle(
                    force=forces["Tránsito"],
                    type="Moto de Tránsito",
                    status=random.choice(["disponible", "en_ruta", "ocupado"]),
                    current_lat=jitter(facility.lat or -34.6, 60),
                    current_lon=jitter(facility.lon or -58.4, 60),
                    home_facility=facility,
                )
            )

    Vehicle.objects.bulk_create(vehicles)
    persisted = list(Vehicle.objects.select_related("force", "home_facility"))
    print(f"Vehículos creados: {len(persisted)}")
    return persisted


def create_agents(
    forces: Dict[str, Force],
    hospitals: Sequence[Hospital],
    facilities: Sequence[Facility],
    vehicles: Sequence[Vehicle],
) -> List[Agent]:
    anchors: Dict[str, List[Tuple[float, float]]] = {name: [] for name in forces}

    for hospital in hospitals:
        anchors["SAME"].append((hospital.lat or -34.6, hospital.lon or -58.4))

    for facility in facilities:
        if facility.force:
            anchors[facility.force.name].append((facility.lat or -34.6, facility.lon or -58.4))

    for vehicle in vehicles:
        if vehicle.current_lat is not None and vehicle.current_lon is not None:
            anchors[vehicle.force.name].append((vehicle.current_lat, vehicle.current_lon))

    vehicles_by_force: Dict[str, List[Vehicle]] = {name: [] for name in forces}
    for vehicle in vehicles:
        vehicles_by_force[vehicle.force.name].append(vehicle)

    agents: List[Agent] = []

    def jitter_location(lat: float, lon: float) -> Tuple[float, float]:
        return jitter(lat, 90), jitter(lon, 90)

    for force_name, force in forces.items():
        available_vehicles = vehicles_by_force.get(force_name, [])
        roles = ROLES[force_name]
        target_count = max(12, len(available_vehicles) * 2)
        for _ in range(target_count):
            vehicle = random.choice(available_vehicles) if available_vehicles and random.random() < 0.65 else None
            home_facility = vehicle.home_facility if vehicle else None

            if anchors[force_name]:
                base_lat, base_lon = random.choice(anchors[force_name])
                lat, lon = jitter_location(base_lat, base_lon)
            else:
                lat = -34.62 + random.random() * 0.12
                lon = -58.52 + random.random() * 0.18

            agents.append(
                Agent(
                    name=pick_name(),
                    force=force,
                    role=random.choice(roles),
                    status=random_status(force_name),
                    assigned_vehicle=vehicle,
                    lat=lat,
                    lon=lon,
                    home_facility=home_facility,
                )
            )

    Agent.objects.bulk_create(agents)
    persisted = list(Agent.objects.select_related("force", "assigned_vehicle"))
    print(f"Agentes creados: {len(persisted)}")
    return persisted


def create_emergencies(forces: Dict[str, Force]) -> List[Emergency]:
    emergencies: List[Emergency] = []

    for data in EMERGENCY_DATA:
        reported_at = timezone.now() - timezone.timedelta(minutes=data["minutes_ago"])
        emergencies.append(
            Emergency(
                description=data["description"],
                address=data["address"],
                location_lat=data["lat"],
                location_lon=data["lon"],
                status="pendiente" if data["code"] != "verde" else "asignada",
                code=data["code"],
                assigned_force=forces.get(data["force"]),
                reported_at=reported_at,
            )
        )

    Emergency.objects.bulk_create(emergencies)

    persisted = list(Emergency.objects.order_by("reported_at"))
    for emergency in persisted:
        if emergency.code in {"rojo", "amarillo"}:
            emergency.ensure_multi_dispatch()

    print(f"Emergencias creadas: {len(persisted)}")
    return persisted


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def populate() -> None:
    random.seed(RANDOM_SEED)

    with transaction.atomic():
        forces = ensure_forces()
        reset_data()

        hospitals = create_hospitals()
        facilities = create_facilities(forces)
        populate_police_stations(forces)
        parking_spots = create_parking_spots()
        vehicles = create_vehicles(forces, hospitals, facilities)
        create_agents(forces, hospitals, facilities, vehicles)
        create_emergencies(forces)

    print("Población offline completada en pocos segundos.")


def main() -> None:
    print("=== Poblando datos de ejemplo (modo offline rápido) ===")
    populate()


# Static dataset for police stations in Buenos Aires
POLICE_STATIONS = [
    {'name': 'Comisaría Vecinal12-A (edificio anexo)', 'address': 'RAMALLO 4398', 'lat': -34.550990102464745, 'lon': -58.49101503190442},
    {'name': 'Comisaría Vecinal 7-A', 'address': 'BONORINO, ESTEBAN, CNEL. AV. 258', 'lat': -34.6310563022503, 'lon': -58.458307591055934},
    {'name': 'Comisaría Vecinal 6-B', 'address': 'AVELLANEDA AV. 1548', 'lat': -34.62038139407484, 'lon': -58.45322168166576},
    {'name': 'Comisaría Vecinal 5-A', 'address': 'BILLINGHURST 471', 'lat': -34.604406411773645, 'lon': -58.415664541274616},
    {'name': 'Comisaría Vecinal 4-A', 'address': 'ZAVALETA 425', 'lat': -34.64194792387007, 'lon': -58.40283281867738},
    {'name': 'Comisaría Vecinal 3-C', 'address': 'REPUBLICA BOLIVARIANA DE VENEZUELA 1931', 'lat': -34.614970908070276, 'lon': -58.39367895264552},
    {'name': 'Comisaría Vecinal 2-A', 'address': 'LAS HERAS GENERAL AV. 1861', 'lat': -34.591136443178065, 'lon': -58.39236199141657},
    {'name': 'Comisaría Vecinal 15-A', 'address': 'GUZMAN 396', 'lat': -34.590546220097984, 'lon': -58.451074877939185},
    {'name': 'Comisaría Vecinal 14-C', 'address': 'REPUBLICA ARABE SIRIA 2961', 'lat': -34.58126954919628, 'lon': -58.41366150581631},
    {'name': 'Comisaría Vecinal 11-A', 'address': 'BUFANO, ALFREDO R. 1800', 'lat': -34.61102295837465, 'lon': -58.47293895840077},
    {'name': 'Comisaría Vecinal 10-C', 'address': 'RAFAELA 4751', 'lat': -34.63918663321706, 'lon': -58.494099442703885},
    {'name': 'Comisaría Vecinal 1-A (edificio anexo I)', 'address': 'DE LOS INMIGRANTES AV. 2250', 'lat': -34.58429865140957, 'lon': -58.36958049572027},
    {'name': 'Comisaría Comunal 13', 'address': 'JURAMENTO 4367', 'lat': -34.5731972491801, 'lon': -58.47578919089627},
    {'name': 'Comisaría Vecinal 3-B', 'address': 'CATAMARCA 1345', 'lat': -34.62604808781184, 'lon': -58.40311991984066},
    {'name': 'Comisaría Vecinal 14-A', 'address': 'ALVAREZ, JULIAN 2373', 'lat': -34.58776786078862, 'lon': -58.41610387118705},
    {'name': 'Comisaría Vecinal 1-E', 'address': 'HUERGO, ING. AV. 1500', 'lat': -34.623676756052674, 'lon': -58.36540954049011},
    {'name': 'Comisaría Vecinal 4-C', 'address': 'PINZON 456', 'lat': -34.63410104469192, 'lon': -58.36069524664056},
    {'name': 'Comisaría Vecinal 1-F', 'address': 'PERU 1050', 'lat': -34.620236707869864, 'lon': -58.37408849620005},
    {'name': 'Comisaría Vecinal 9-A', 'address': 'DE LA TORRE, LISANDRO AV. 2343', 'lat': -34.661924211825074, 'lon': -58.50118618349343},
    {'name': 'Comisaria Comunal 7', 'address': 'BONORINO, ESTEBAN, CNEL. AV. 258', 'lat': -34.6310563022503, 'lon': -58.458307591055934},
    {'name': 'Comisaria Vecinal 4-A (edificio anexo)', 'address': 'CASEROS AV. 2724', 'lat': -34.63640427680307, 'lon': -58.40086114781002},
    {'name': 'Comisaría Vecinal 15-C', 'address': 'GUZMAN 396', 'lat': -34.59047448311428, 'lon': -58.45132792000443},
    {'name': 'Comisaría Vecinal 9-B', 'address': 'JUSTO, JUAN B. AV. 9752', 'lat': -34.63489634508499, 'lon': -58.52755284084778},
    {'name': 'Comisaría Comunal 12', 'address': 'RAMALLO 4398', 'lat': -34.550990102464745, 'lon': -58.49101503190442},
    {'name': 'Comisaría Comunal 15', 'address': 'GUZMAN 396', 'lat': -34.590546220097984, 'lon': -58.451074877939185},
    {'name': 'Comisaría Comunal 4', 'address': 'ZAVALETA 425', 'lat': -34.64194792387007, 'lon': -58.40283281867738},
    {'name': 'Comisaría Comunal 10', 'address': 'RAFAELA 4751', 'lat': -34.63918663321706, 'lon': -58.494099442703885},
    {'name': 'Comisaria Comunal 9', 'address': 'JUSTO, JUAN B. AV. 9752', 'lat': -34.63487596001541, 'lon': -58.52751592037157},
    {'name': 'Comisaría Vecinal 8-B (edificio anexo I)', 'address': 'PEDERNERA 3405', 'lat': -34.66041800036428, 'lon': -58.431835553573045},
    {'name': 'Comisaría Vecinal 1-C', 'address': 'SAN JUAN AV. 1757', 'lat': -34.62254103571925, 'lon': -58.39072173330163},
    {'name': 'Comisaría Vecinal 1-C (edificio anexo)', 'address': 'SAN JOSE 1224', 'lat': -34.62292577857168, 'lon': -58.38572834729359},
    {'name': 'Comisaría Comunal 6', 'address': 'AVELLANEDA AV. 1548', 'lat': -34.62038139407484, 'lon': -58.45322168166576},
    {'name': 'Comisaría Comunal 1', 'address': 'DE LOS INMIGRANTES AV. 2250', 'lat': -34.58429865140957, 'lon': -58.36958049572027},
    {'name': 'Comisaría Comunal 2', 'address': 'LAS HERAS GENERAL AV. 1861', 'lat': -34.591136443178065, 'lon': -58.39236199141657},
    {'name': 'Comisaría Vecinal 1-D', 'address': 'LAVALLE 451', 'lat': -34.60190533346012, 'lon': -58.37324885578176},
    {'name': 'Comisaría Vecinal 5-B', 'address': 'MUÑIZ 1250', 'lat': -34.62863984277676, 'lon': -58.42492801152498},
    {'name': 'Comisaría Vecinal 6-A', 'address': 'DIAZ VELEZ AV. 5152', 'lat': -34.608977891300256, 'lon': -58.43950273257121},
    {'name': 'Comisaría Vecinal 7-B', 'address': 'VALLE 1454', 'lat': -34.62677886954029, 'lon': -58.448088022379274},
    {'name': 'Comisaría Vecinal 2-B', 'address': 'CHARCAS 2844', 'lat': -34.5940780229934, 'lon': -58.406722080262135},
    {'name': 'Comisaría Vecinal 12-A', 'address': 'MACHAIN 3045', 'lat': -34.565145629242174, 'lon': -58.48252524827416},
    {'name': 'Comisaría Vecinal 15-B', 'address': 'CAMARGO 645', 'lat': -34.59932010840561, 'lon': -58.44108560356735},
    {'name': 'Comisaría Vecinal 4-B', 'address': 'QUILMES 456', 'lat': -34.64479313618811, 'lon': -58.417157992360934},
    {'name': 'Comisaría Vecinal 8-B', 'address': 'ESCALADA AV. 4347', 'lat': -34.67735534617036, 'lon': -58.454267122981484},
    {'name': 'Comisaría Vecinal 1-B', 'address': 'TACUARI 770', 'lat': -34.617160446937426, 'lon': -58.37858130354149},
    {'name': 'Comisaría Vecinal 9-C', 'address': 'REMEDIOS 3748', 'lat': -34.64146107167717, 'lon': -58.476336219370545},
    {'name': 'Comisaría Vecinal 11-B', 'address': 'CUBAS, JOSE 4154', 'lat': -34.59831458730553, 'lon': -58.51560404631523},
    {'name': 'Comisaría Vecinal 12-B (edificio anexo I)', 'address': 'NAZCA 4254', 'lat': -34.58971288961547, 'lon': -58.49936617057593},
    {'name': 'Comisaría Vecinal 8-A', 'address': 'LEGUIZAMON, MARTINIANO 4347', 'lat': -34.67903291493464, 'lon': -58.474888158101265},
    {'name': 'Comisaría Vecinal 4-E', 'address': 'MONTES DE OCA, MANUEL AV. 861', 'lat': -34.63822092897085, 'lon': -58.374858359482914},
    {'name': 'Comisaría Vecinal 4-D', 'address': 'CALIFORNIA 1850', 'lat': -34.6471488978436, 'lon': -58.37478987747005},
    {'name': 'Comisaría Vecinal 14-B', 'address': 'CABILDO AV. 232', 'lat': -34.573257038631915, 'lon': -58.43904957050002},
    {'name': 'Comisaría Vecinal 13-C', 'address': 'MENDOZA 2263', 'lat': -34.56014527431079, 'lon': -58.45609733440254},
    {'name': 'Comisaría Vecinal 13-B', 'address': 'CUBA 3145', 'lat': -34.5512909001547, 'lon': -58.463543639788206},
    {'name': 'Comisaría Vecinal 12-B', 'address': 'OLAZABAL AV. 5437', 'lat': -34.57877677036396, 'lon': -58.49009267264174},
    {'name': 'Comisaría Vecinal 10-B', 'address': 'PORCEL DE PERALTA, MANUEL 726', 'lat': -34.629562799536316, 'lon': -58.523901986041395},
    {'name': 'Comisaría Vecinal 1-A', 'address': 'SUIPACHA 1156', 'lat': -34.594643162499665, 'lon': -58.38003952667834},
    {'name': 'Comisaría Vecinal 12-C', 'address': 'JURAMENTO 4367', 'lat': -34.5731972491801, 'lon': -58.47578919089627},
    {'name': 'Comisaría Comunal 11', 'address': 'BUFANO, ALFREDO R. 1800', 'lat': -34.61102295837465, 'lon': -58.47293895840077},
    {'name': 'Comisaría Vecinal 10-A', 'address': 'CHIVILCOY 453', 'lat': -34.62880577190448, 'lon': -58.48377879857752},
    {'name': 'Comisaría Vecinal 7-C', 'address': 'GAONA AV. 2738', 'lat': -34.61611299874862, 'lon': -58.46482110249305},
    {'name': 'Comisaría Vecinal 10-C', 'address': 'BASUALDO 165', 'lat': -34.639965860505626, 'lon': -58.50508483847855},
    {'name': 'Comisaría Vecinal 3-A (edificio anexo)', 'address': 'URQUIZA, GRAL. 544', 'lat': -34.61705659478637, 'lon': -58.40928216463775},
    {'name': 'Comisaría Vecinal 13-A', 'address': 'ARTILLEROS 2081', 'lat': -34.55488835516263, 'lon': -58.444131059406836},
    {'name': 'Comisaría Vecinal 8-C', 'address': 'DIAZ, ANA 5899', 'lat': -34.68309883885219, 'lon': -58.468969318089265},
    {'name': 'Comisaria Vecinal 1-A (edificio anexo II)', 'address': 'SUIPACHA 1156', 'lat': -34.60192349060992, 'lon': -58.38890886319144},
    {'name': 'Comisaria Vecinal 14-A (edificio anexo)', 'address': 'SCALABRINI ORTIZ, RAUL AV. 1350', 'lat': -34.59249343857936, 'lon': -58.42760256512527},
    {'name': 'Comisaria Comunal 8', 'address': 'CABRERA, DELFO y 23 DE JUNIO', 'lat': -34.67303346585819, 'lon': -58.455378659756576},
    {'name': 'Comisaría Vecinal 3-A', 'address': 'LAVALLE 2625', 'lat': -34.60329113019939, 'lon': -58.40407720431502},
    {'name': 'Comisaría Comunal 3', 'address': 'REPUBLICA BOLIVARIANA DE VENEZUELA 1931', 'lat': -34.615008346785075, 'lon': -58.39367592639254},
    {'name': 'Comisaría Comunal 14', 'address': 'REPUBLICA ARABE SIRIA 2961', 'lat': -34.58126954919628, 'lon': -58.41366150581631},
    {'name': 'Comisaría Comunal 5', 'address': 'BILLINGHURST 471', 'lat': -34.604406411773645, 'lon': -58.415664541274616},
    {'name': 'Comisaría Comunal 1 Norte', 'address': 'CORRIENTES AV. 436', 'lat': -34.60339778867843, 'lon': -58.37272314184262},
    {'name': 'Comisaría Comunal 1 Sur', 'address': 'PERU 1050', 'lat': -34.62026507730856, 'lon': -58.37400376134853},
    {'name': 'Comisaría Vecinal 3-C (anexo I)', 'address': 'LAVALLE 1958', 'lat': -34.603345228951582, 'lon': -58.394768079033724},
    {'name': 'Comisaría Vecinal 14-A (edificio anexo II)', 'address': 'SANTA FE AV. 4000', 'lat': -34.58255196829385, 'lon': -58.420124506242104},
]

# Function to populate police stations
def populate_police_stations(forces):
    police_stations = [
        Facility(
            name=station["name"],
            kind="comisaria",
            force=forces["Policía"],
            address=station["address"],
            lat=station["lat"],
            lon=station["lon"],
        )
        for station in POLICE_STATIONS
    ]
    Facility.objects.bulk_create(police_stations)
    print(f"Created {len(police_stations)} police stations.")

if __name__ == "__main__":
    main()
