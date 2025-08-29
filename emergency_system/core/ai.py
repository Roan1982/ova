# Módulo simple de "IA" basado en reglas ponderadas para triage
# Evalúa gravedad por palabras clave, contexto, vulnerabilidad y multiplicidad

import re

SEVERE_KEYWORDS = {
    # Médicas críticas
    'paro cardiaco': 60,
    'paro cardiorrespiratorio': 60,
    'pcr': 60,
    'infarto': 55,
    'inconsciente': 50,
    'convulsion': 45,
    'convulsión': 45,
    'asfixia': 55,
    'ahogo': 45,
    'hemorragia masiva': 60,
    'hemorragia': 50,
    'quemaduras graves': 55,
    # Eventos críticos
    'explosion': 60,
    'explosión': 60,
    'derrumbe': 60,
    'incendio masivo': 60,
    'tiroteo': 60,
    'arma de fuego': 55,
    'apuñalado': 55,
    'arma blanca': 50,
    # Fuego sin decir "incendio"
    'se esta quemando': 60,
    'se está quemando': 60,
    'se quema': 60,
    'en llamas': 60,
    'fuego': 50,
    # Delitos críticos e infraestructura sensible
    'asalto': 55,
    'atraco': 55,
    'banco central': 25,
}

MODERATE_KEYWORDS = {
    'accidente': 30,
    'choque': 30,
    'herido': 30,
    'fractura': 35,
    'luxacion': 25,
    'luxación': 25,
    'quemadura': 25,
    'incendio': 40,
    'caida': 20,
    'caída': 20,
    'intoxicacion': 30,
    'intoxicación': 30,
    'agresion': 30,
    'agresión': 30,
    'robo con violencia': 40,
    'humo': 25,
    # Delitos comunes
    'robo': 40,
    'robando': 40,
    'roban': 40,
    # Tránsito / orden público
    'transito': 30,
    'tránsito': 30,
    'trafico': 30,
    'tráfico': 30,
    'bloqueo': 30,
    'corte': 30,
    'manifestacion': 30,
    'manifestación': 30,
    'obstruccion': 30,
    'obstrucción': 30,
    'disturbio': 35,
}

MINOR_KEYWORDS = {
    'dolor de cabeza': 5,
    'fiebre': 5,
    'resfriado': 5,
    'gripe': 5,
    'mareo': 10,
}

# Modificadores de contexto
VULNERABLE = {
    'bebé': 15,
    'bebe': 15,
    'niño': 10,
    'nino': 10,
    'embarazada': 15,
    'anciano': 10,
    'adulto mayor': 10,
}

MULTIPLE = {
    'múltiples': 15,
    'multiples': 15,
    'varios heridos': 20,
    'masivo': 20,
}

LUGARES_SENSIBLES = {
    'escuela': 15,
    'jardin': 15,
    'jardín': 15,
    'hospital': 10,
    'estacion': 10,
    'estación': 10,
    'banco': 10,
}


def _normalize_text(text: str) -> str:
    t = text.lower()
    t = re.sub(r"[\s]+", " ", t)
    return t


def analyze_description(text: str):
    """Devuelve (score, razones[]) analizando la descripción."""
    if not text:
        return 0, ['Sin descripción']

    txt = _normalize_text(text)
    score = 0
    reasons = []

    def apply_dict(dic, label):
        nonlocal score
        for k, w in dic.items():
            if k in txt:
                score += w
                reasons.append(f"{label}: '{k}' (+{w})")

    apply_dict(SEVERE_KEYWORDS, 'Severidad alta')
    apply_dict(MODERATE_KEYWORDS, 'Severidad media')
    apply_dict(MINOR_KEYWORDS, 'Leve')
    apply_dict(VULNERABLE, 'Vulnerable')
    apply_dict(MULTIPLE, 'Multiplicidad')
    apply_dict(LUGARES_SENSIBLES, 'Lugar sensible')

    # Si hay elementos contradictorios, priorizar lo más grave
    score = max(1, min(100, score))

    # Si no hubo coincidencias, caso leve por defecto
    if score == 1:
        reasons.append('Sin coincidencias relevantes: caso leve por defecto')

    return score, reasons


def classify_emergency(text: str):
    score, reasons = analyze_description(text)
    # Umbrales ajustados
    if score >= 60:
        code = 'rojo'
    elif score >= 25:
        code = 'amarillo'
    else:
        code = 'verde'
    return code, score, reasons
