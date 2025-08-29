# Módulo de IA avanzado basado en reglas ponderadas para triage
# Evalúa gravedad por palabras clave, contexto, vulnerabilidad y multiplicidad
# Genera respuestas coherentes y asignación inteligente de fuerzas

import re
import random

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
    'herido grave': 55,
    'herida grave': 55,
    'dolor de pecho': 45,
    'no respira': 60,
    'sin pulso': 60,
    'overdosis': 50,
    # Eventos críticos
    'explosion': 60,
    'explosión': 60,
    'derrumbe': 60,
    'incendio masivo': 60,
    'tiroteo': 60,
    'arma de fuego': 55,
    'apuñalado': 55,
    'arma blanca': 50,
    'balacera': 60,
    'disparo': 55,
    'tiros': 55,
    # Fuego
    'se esta quemando': 60,
    'se está quemando': 60,
    'se quema': 60,
    'en llamas': 60,
    'fuego': 50,
    'humo denso': 45,
    'olor a gas': 55,
    'escape de gas': 60,
    # Delitos críticos
    'asalto': 55,
    'atraco': 55,
    'secuestro': 60,
    'violacion': 60,
    'violación': 60,
    'homicidio': 60,
    'asesinato': 60,
}

MODERATE_KEYWORDS = {
    'accidente': 30,
    'choque': 30,
    'colision': 35,
    'colisión': 35,
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
    'golpe': 25,
    'pelea': 35,
    'riña': 35,
    'violencia': 40,
    # Delitos comunes
    'robo': 40,
    'robando': 40,
    'roban': 40,
    'hurto': 30,
    'vandalismo': 25,
    'daños': 30,
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
    'desorden': 30,
    # Médicas moderadas
    'desmayo': 25,
    'mareo': 20,
    'vomitos': 20,
    'vómitos': 20,
    'falta de aire': 30,
    'dificultad respirar': 35,
}

MINOR_KEYWORDS = {
    'dolor de cabeza': 5,
    'cefalea': 5,
    'fiebre': 5,
    'resfriado': 5,
    'gripe': 5,
    'molestias': 10,
    'ruido': 15,
    'musica alta': 15,
    'música alta': 15,
    'problema menor': 10,
    'consulta': 5,
}

# Modificadores de contexto
VULNERABLE = {
    'bebé': 15,
    'bebe': 15,
    'niño': 10,
    'nino': 10,
    'menor': 10,
    'embarazada': 15,
    'anciano': 10,
    'adulto mayor': 10,
    'discapacitado': 15,
    'silla de ruedas': 15,
}

MULTIPLE = {
    'múltiples': 15,
    'multiples': 15,
    'varios heridos': 20,
    'muchas personas': 15,
    'masivo': 20,
    'multitudinario': 20,
}

LUGARES_SENSIBLES = {
    'escuela': 15,
    'colegio': 15,
    'jardin': 15,
    'jardín': 15,
    'hospital': 10,
    'clinica': 10,
    'clínica': 10,
    'estacion': 10,
    'estación': 10,
    'banco': 10,
    'shopping': 15,
    'estadio': 20,
    'plaza': 10,
    'subte': 15,
    'tren': 15,
    'aeropuerto': 20,
}

# Patrones para identificar el tipo de emergencia
MEDICAL_PATTERNS = [
    r'dolor|herido|sangra|inconsciente|infarto|convuls|asfixia|ahogo|hemorragia|quemadura|fractura|desmayo|mareo|vomito|fiebre|dificultad.*respir|falta.*aire|overdosis|intoxica',
    r'ambulancia|same|medico|hospital|clinica'
]

FIRE_PATTERNS = [
    r'fuego|incendio|llamas|humo|quema|explosion|gas|bomberos',
    r'se.*quema|en.*llamas|olor.*gas|escape.*gas'
]

POLICE_PATTERNS = [
    r'robo|asalto|atraco|tiroteo|disparo|arma|balacera|pelea|agresion|violencia|secuestro|homicidio|asesinato|hurto|vandalismo|policia',
    r'disturbio|manifestacion|desorden|bloqueo|corte.*calle'
]

TRAFFIC_PATTERNS = [
    r'accidente.*transit|choque|colision|transito|trafico|vehiculo.*impact|auto.*choca',
    r'semaforo|corte.*ruta|bloqueo.*avenida'
]


def _normalize_text(text: str) -> str:
    t = text.lower()
    t = re.sub(r"[\s]+", " ", t)
    return t


def _matches_pattern(text: str, patterns: list) -> bool:
    """Verifica si el texto coincide con algún patrón de la lista"""
    for pattern in patterns:
        if re.search(pattern, text):
            return True
    return False


def analyze_description(text: str):
    """Devuelve (score, razones[], tipo_sugerido) analizando la descripción."""
    if not text:
        return 0, ['Sin descripción'], 'policial'

    txt = _normalize_text(text)
    score = 0
    reasons = []
    tipo_sugerido = 'policial'  # default

    def apply_dict(dic, label):
        nonlocal score
        found_any = False
        for k, w in dic.items():
            if k in txt:
                score += w
                reasons.append(f"{label}: '{k}' (+{w})")
                found_any = True
        return found_any

    # Aplicar diccionarios de palabras clave
    apply_dict(SEVERE_KEYWORDS, 'Severidad alta')
    apply_dict(MODERATE_KEYWORDS, 'Severidad media')
    apply_dict(MINOR_KEYWORDS, 'Leve')
    apply_dict(VULNERABLE, 'Vulnerable')
    apply_dict(MULTIPLE, 'Multiplicidad')
    apply_dict(LUGARES_SENSIBLES, 'Lugar sensible')

    # Determinar tipo de emergencia basado en patrones
    if _matches_pattern(txt, MEDICAL_PATTERNS):
        tipo_sugerido = 'medico'
        reasons.append('Patrón médico detectado')
    elif _matches_pattern(txt, FIRE_PATTERNS):
        tipo_sugerido = 'bomberos'
        reasons.append('Patrón de bomberos detectado')
    elif _matches_pattern(txt, TRAFFIC_PATTERNS):
        # Tránsito puede ser policial o bomberos según la gravedad
        if score > 40:
            tipo_sugerido = 'bomberos'  # Accidente grave
        else:
            tipo_sugerido = 'policial'  # Infracción de tránsito
        reasons.append('Patrón de tránsito detectado')
    elif _matches_pattern(txt, POLICE_PATTERNS):
        tipo_sugerido = 'policial'
        reasons.append('Patrón policial detectado')

    # Ajustar score
    score = max(1, min(100, score))

    # Si no hubo coincidencias, caso leve por defecto
    if score == 1 and not reasons:
        reasons.append('Sin coincidencias relevantes: caso leve por defecto')

    return score, reasons, tipo_sugerido


def classify_emergency(text: str):
    """Clasificación completa de emergencia"""
    score, reasons, tipo = analyze_description(text)
    
    # Umbrales ajustados
    if score >= 60:
        code = 'rojo'
    elif score >= 25:
        code = 'amarillo'
    else:
        code = 'verde'
    
    return code, score, reasons, tipo


def generate_ia_response(description: str, tipo: str, codigo: str, score: int, reasons: list):
    """Genera una respuesta coherente de IA simulando análisis inteligente"""
    
    # Respuestas base por tipo y código
    responses = {
        'medico': {
            'rojo': [
                'Emergencia médica crítica detectada. Requiere intervención inmediata del SAME.',
                'Situación de riesgo vital. Activando protocolo de emergencia médica.',
                'Caso médico de máxima prioridad. Despachando ambulancia con UTI móvil.',
                'Emergencia sanitaria grave. Coordinando con hospital más cercano.'
            ],
            'amarillo': [
                'Emergencia médica moderada. SAME debe evaluar en sitio.',
                'Situación médica que requiere atención especializada.',
                'Caso médico prioritario. Despachando ambulancia.',
                'Emergencia sanitaria. Activando protocolo médico estándar.'
            ],
            'verde': [
                'Consulta médica menor. SAME puede atender según disponibilidad.',
                'Situación médica leve. No requiere respuesta urgente.',
                'Caso médico rutinario. Derivar a centro de salud cercano.',
                'Emergencia sanitaria menor. Prioridad baja.'
            ]
        },
        'bomberos': {
            'rojo': [
                'Emergencia de bomberos crítica. Riesgo inminente para la seguridad pública.',
                'Situación de máximo riesgo. Activando protocolo de emergencia total.',
                'Caso crítico para bomberos. Despachando múltiples unidades.',
                'Emergencia grave. Coordinando con fuerzas adicionales.'
            ],
            'amarillo': [
                'Emergencia de bomberos moderada. Requiere intervención especializada.',
                'Situación de riesgo controlado. Despachando unidad de bomberos.',
                'Caso prioritario para bomberos. Activando protocolo estándar.',
                'Emergencia que requiere equipo especializado.'
            ],
            'verde': [
                'Situación menor para bomberos. Atención según disponibilidad.',
                'Caso de baja prioridad. No requiere respuesta urgente.',
                'Emergencia menor. Puede resolverse con unidad básica.',
                'Situación rutinaria para bomberos.'
            ]
        },
        'policial': {
            'rojo': [
                'Emergencia policial crítica. Riesgo inmediato para la seguridad ciudadana.',
                'Situación de máxima gravedad. Activando protocolo de emergencia.',
                'Caso policial urgente. Despachando múltiples patrullas.',
                'Emergencia de seguridad. Coordinando respuesta inmediata.'
            ],
            'amarillo': [
                'Emergencia policial moderada. Requiere intervención oportuna.',
                'Situación que compromete la seguridad. Despachando patrulla.',
                'Caso policial prioritario. Activando protocolo estándar.',
                'Emergencia de orden público que requiere atención.'
            ],
            'verde': [
                'Situación policial menor. Atención según prioridades.',
                'Caso de baja urgencia. No requiere respuesta inmediata.',
                'Emergencia menor. Puede resolverse con patrulla básica.',
                'Situación rutinaria de seguridad.'
            ]
        }
    }
    
    # Seleccionar respuesta base aleatoria
    base_response = random.choice(responses.get(tipo, {}).get(codigo, ['Emergencia clasificada.']))
    
    # Agregar contexto específico según las razones detectadas
    context_additions = []
    
    for reason in reasons:
        if 'Vulnerable' in reason:
            context_additions.append('Involucra población vulnerable.')
        elif 'Multiplicidad' in reason:
            context_additions.append('Evento de múltiples víctimas.')
        elif 'Lugar sensible' in reason:
            context_additions.append('Ocurre en zona sensible.')
        elif 'Severidad alta' in reason:
            context_additions.append('Indicadores de alta gravedad.')
    
    # Agregar recomendaciones específicas
    if codigo == 'rojo':
        if tipo == 'medico':
            context_additions.append('Coordinar con hospital receptor.')
        elif tipo == 'bomberos':
            context_additions.append('Evaluar necesidad de evacuación.')
        elif tipo == 'policial':
            context_additions.append('Considerar refuerzos adicionales.')
    
    # Ensamblar respuesta final
    full_response = base_response
    if context_additions:
        full_response += ' ' + ' '.join(context_additions)
    
    # Agregar información del score si es relevante
    if score > 50:
        full_response += f' (Índice de gravedad: {score}/100)'
    
    return full_response


def get_ai_classification_with_response(description: str):
    """Función principal que devuelve clasificación completa con respuesta de IA"""
    if not description:
        return {
            'tipo': 'policial',
            'codigo': 'verde',
            'score': 1,
            'razones': ['Sin descripción proporcionada'],
            'respuesta_ia': 'No se puede clasificar sin descripción del evento.'
        }
    
    codigo, score, reasons, tipo = classify_emergency(description)
    respuesta_ia = generate_ia_response(description, tipo, codigo, score, reasons)
    
    return {
        'tipo': tipo,
        'codigo': codigo,
        'score': score,
        'razones': reasons,
        'respuesta_ia': respuesta_ia
    }

