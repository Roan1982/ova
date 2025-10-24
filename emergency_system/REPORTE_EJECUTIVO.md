Reporte Ejecutivo
Sistema de Respuesta a Emergencias Urbanas — Proyecto OVA

Equipo: [Nombres del grupo]
Fecha: Octubre 2025

Resumen ejecutivo (máx. 1 página)
Este proyecto desarrolla un prototipo funcional para optimizar la respuesta a emergencias urbanas. El sistema recibe reportes textuales, clasifica la urgencia (rojo/amarillo/verde), recomienda fuerzas y vehículos, y calcula rutas optimizadas considerando cortes de calles y congestión. Integraciones clave: API Transporte CABA (cortes/parking/tráfico), proveedores de ruteo (Mapbox/OpenRoute/OSRM), y un módulo de clasificación IA con fallback local.

Resultados clave
- Clasificador híbrido: reglas locales robustas (`core/ai.py`) + opción cloud LLM (`core/llm.py`). Fallback local garantiza respuestas consistentes.
- Ruteo multi-proveedor con ajuste por cortes y tráfico (`core/routing.py`). Guarda las rutas como `CalculatedRoute` para trazabilidad.
- Scripts reproducibles para poblar datos y simular emergencias (`populate_test_data.py`, `seed_emergencies`).

Beneficio esperado
- Reducción estimada del tiempo de respuesta en escenarios simulados cuando se usan datos de tráfico y evitación de cortes; además, mayor trazabilidad de decisiones operativas.

Alcance del entregable
- Código fuente (Django) con modelos, rutas y scripts.
- Documentación técnica: `DOCUMENTACION_TECNICA.md` (bitácora, pipeline, informe técnico).
- Demo local (HTML) para presentación interactiva.

Metodología
- Datos: combinación de datos institucionales simulados y APIs públicas. Scripts para generar escenarios reproducibles.
- Modelado: clasificación por reglas + evaluación de LLMs; heurística de asignación basada en ETA calculada con `RouteOptimizer`.
- Validación: tests unitarios existentes (`core/tests.py`) y experimentos A/B simulados.

Resultados y métricas (resumen)
- Métricas recomendadas a reportar con ejemplos: MAE de ETA (min), tiempo medio reporte→asignado (min), precisión del clasificador (F1 por clase).
- Ejemplo de resultados de demostración (simulado): ETA promedio reducido ~15% en rutas ajustadas por congestión vs rutas directas.

Conclusiones y recomendaciones
- Integrar caché (Redis) y workers (Celery) para cálculos en background en producción.
- Añadir endpoint `/ai-status/` y health checks para monitorizar proveedores cloud.
- Priorizar integración con telemetría real (GPS vehicular) para validar en campo.

Pasos siguientes (priorizados)
1. Implementar demo de frontend interactiva y endpoint JSON para rutas y tracking.
2. Añadir tests de integración y mocks para proveedores cloud.
3. Preparar contenedores Docker y pipeline CI para despliegue.

Anexos y referencias
- Repositorio: estructura en `emergency_system/`.
- Documentación técnica: `DOCUMENTACION_TECNICA.md`.
- Tests relevantes: `core/tests.py`, `test_police_routing.py`.
- Scripts de población: `populate_test_data.py`, `core/management/commands/seed_emergencies.py`.

Fin del reporte ejecutivo.
