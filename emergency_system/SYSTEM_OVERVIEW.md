# Sistema de Emergencias CABA – Visión Técnica Integral

## 1. Objetivo General
Unificar clasificación inteligente de emergencias, asignación óptima de recursos y simulación de movilidad urbana (rutas, progreso, tráfico sintético y "onda verde") proporcionando una vista operativa consistente y extensible.

## 2. Arquitectura Lógica

Componentes principales:
- Ingesta & Clasificación: Procesa descripciones de emergencias y aplica modelo IA (cloud + fallback de reglas).
- Persistencia: Modelos Django (Emergencies, Forces, Agents, Facilities, CalculatedRoute, Dispatches, etc.).
- Motor de Ruteo: Calcula múltiples alternativas y las persiste (no recalcula una vez resuelta la emergencia).
- Motor de Movilidad: Interpola progreso y posición por recurso basado en ETA ajustado por tráfico.
- Simulador de Tráfico: Genera `traffic_factor` determinístico que modifica tiempos base.
- Gestor Onda Verde: Calcula ventanas de paso en intersecciones y activa prioridades.
- Capa API: Endpoints JSON para UI (rutas, movilidad, tracking, green wave, noticias, clima, incidentes).
- Frontend Operativo: Template con Leaflet + JS que pinta rutas, marcadores, barras de progreso y timelines.
- Fallbacks: Mecanismos para degradar funcionalidad (sin IA, sin tracking real, sin API clima, etc.).

## 3. Modelos Clave (Resumen)
- Emergency: Datos básicos + severidad + estado (activa/resuelta).
- Force / Agent / Vehicle: Recursos asignables con posición y capacidades (abstracción según dominio real).
- EmergencyDispatch: Vincula emergencia con recurso (rol, orden de prioridad, timestamps).
- CalculatedRoute: Ruta persistida (geometry LineString, distancia, ETA base, orden).
- Facility / HospitalAgent: Soporte de infraestructura estática y puntos de referencia.
- EmergencyAIResponse / EmergencyAddress (según migraciones): Metadatos de clasificación y geocodificación.
- CalculatedRoute (añade múltiples variantes para una emergencia, congelables al resolver).

## 4. Flujo de Datos Principal
1. Usuario / Sistema crea una emergencia con coordenadas → se llama a motor IA para clasificación y sugerencia de recursos.
2. Se generan rutas candidatas (N alternativas) → se guardan en `CalculatedRoute`.
3. UI consulta `/api/stored-routes/<id>/` para pintar rutas iniciales (sin recalcular).
4. Polling periódico a `/api/mobility/<id>/` devuelve progreso por recurso (progreso sintético si no hay tracking real).
5. Si la emergencia es código rojo y se activa onda verde: POST `/api/green-wave/<id>/` → gestor calcula ventanas.
6. Frontend muestra: barra global (promedio), tarjetas por recurso, timeline de intersecciones próximas.
7. Al resolver emergencia: rutas congeladas; progreso se fija en 100%; polling se detiene.

## 5. Endpoints (Catálogo Resumido)
| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/api/routes/<id>/` | GET/POST | Cálculo o recálculo (si no resuelta) de rutas |
| `/api/stored-routes/<id>/` | GET | Devuelve rutas persistidas sin recalcular |
| `/api/mobility/<id>/` | GET | Progreso, ETA ajustada, intersecciones próximas, ventanas onda verde |
| `/api/tracking/` | GET | Tracking genérico (placeholder/sintético / futuro real) |
| `/api/green-wave/<id>/` | POST | Activa onda verde para recursos críticos |
| `/api/traffic-status/` | GET | Estado agregado de ondas/intersecciones |
| `/api/news/` | GET | Noticias clasificadas con severidad |
| `/api/weather/` | GET | Clima y mini pronóstico |
| `/api/incidents/` | GET | Incidentes / tránsito categorizados |
| `/ai/status` | GET | Salud del proveedor IA + fallback |

## 6. Algoritmos y Heurísticas
### 6.1 Clasificación IA
- Intenta primero proveedor cloud (OpenAI u otro) con timeout y reintentos.
- Prompt context con reglas de decisión + extracción estructurada (JSON esperado).
- Fallback: Reglas locales basadas en keywords priorizadas (choque, incendio, herido, etc.).

### 6.2 Cálculo de Rutas
- Genera múltiples alternativas (Óptima / Rápidas / Respaldo) — abstracción actual (no integra aún servicio GIS externo real).
- Persiste distancia y tiempo estimado (`estimated_time_minutes`).
- No se recalcula mientras la emergencia está activa salvo petición explícita y condiciones de cambio.
- Al resolver: bandera `frozen` → evita cálculos posteriores.

### 6.3 Progreso y Movilidad
- Para cada recurso se deriva un `traffic_factor` determinístico (semilla = id + hora/time-slice) modulando ETA.
- Progreso = tiempo transcurrido / (ETA_base * factor_tráfico) (clamp 0..1).
- Posición interpolada sobre la geometría (LineString) con reparto proporcional a longitudes de segmentos acumulados.
- Distancia restante y ETA dinámica derivadas de progreso.
- Global Progress = promedio simple de progresos individuales.

### 6.4 Tráfico Sintético
- Factor basado en franjas horarias: picos elevan coeficiente >1; noches reducen (<1).
- Ajuste adicional según severidad del código (reducción para emergencias críticas simulando prioridad vial).
- Resultado reproducible para la misma franja y recurso (consistencia entre polls).

### 6.5 Onda Verde
- Conjunto estático de intersecciones mayores (`MAJOR_INTERSECTIONS`).
- Detección de intersecciones “en ruta” por proximidad (buffer configurable ~50m).
- Para cada intersección se calcula ventana estimada: [ETA_arribo - delta_pre, ETA_arribo + delta_post].
- Activación: guarda timestamp de inicio y duración objetivo (por defecto ~30s segmento). Limpia expirados automáticamente.
- Estados derivados en frontend: ACTIVA (now dentro), Próx (<15s), Pendiente (>15s).

### 6.6 Fallbacks
- Sin tracking: se usa progreso sintético de movilidad.
- Sin IA: clasificación por reglas.
- Sin clima API: Open‑Meteo → si falla: panel vacío.
- Sin rutas válidas: ruta placeholder corta.

## 7. Frontend Operativo
- Leaflet para render de capas y polilíneas.
- Marcadores diferenciados por tipo de recurso (vehículo, agente, hospital, genérico).
- Barra global (promedio) + tarjetas individuales con métricas.
- Mini timeline por recurso (intersecciones y ventanas estimadas).
- Timeline agregado de ondas activas (si aplica).
- Polling: intervalos configurables (movilidad, noticias, clima, incidentes).

## 8. Congelación de Rutas
- Al resolver emergencia: backend responde `frozen=true`.
- Progreso forzado a 1.0; frontend detiene animaciones/movilidad.
- El badge de estado indica “Rutas congeladas”.

## 9. Extensibilidad y Puntos de Integración
| Área | Estrategia de Extensión |
|------|-------------------------|
| Cálculo de rutas | Sustituir función actual por cliente a motor GIS externo (OSRM, GraphHopper, Valhalla) manteniendo forma GeoJSON + ETA |
| Factores de tráfico | Reemplazar generador determinístico por feeds en tiempo real (Waze, TomTom Traffic API) |
| Onda verde | Integrar con sistema real de semáforos (API municipal) y validar disponibilidad por intersección |
| Clasificación IA | Añadir más proveedores vía factory (`AI_PROVIDER`) |
| Métricas agregadas | Persistir snapshots de movilidad para análisis histórico (tiempos reales vs estimados) |
| Notificaciones | WebSockets / SSE para reducir polling intensivo |
| Seguridad | Autenticación JWT/Session + roles para activar onda verde |

## 10. Consideraciones de Rendimiento
- Polling ligero (payload reducido — recorte a 5–6 intersecciones próximas) reduce ancho de banda.
- Cálculos deterministas evitan almacenamiento de estados intermedios.
- Posible cuello de botella futuro: interpolación en gran número de recursos concurrentes (optimizable con pre-cálculo de cumulativas).

## 11. Observabilidad (Futuro)
- Añadir logging estructurado (JSON) por endpoint para auditoría.
- Métricas: latencia de clasificación, desviación ETA real vs. estimada, ratio de uso fallback.
- Health checks internos: estado de proveedor IA, latencia de ruteo, cola de solicitudes.

## 12. Seguridad y Riesgos
- Validar input de coordenadas (prevención de rutas inválidas / inyección).
- Límite de frecuencia en activación de onda verde.
- Sanitizar feeds externos (RSS) antes de renderizar.
- Manejar expiración y rotación de API keys del proveedor IA.

## 13. Roadmap Sugerido
Corto Plazo:
- WebSockets para movilidad y estado de ondas.
- Percentil configurable para progreso global.
- Mejoras UI (clustering y filtros por tipo de recurso).

Mediano Plazo:
- Integración real GIS (OSRM) + perfiles (vehículo ligero / pesado / peatonal).
- Persistencia histórica de sesiones de emergencia (analytics).
- Calidad de datos: validación direcciones y geocodificación inversa.

Largo Plazo:
- Integración semafórica municipal en vivo.
- Optimización multi-objetivo (tiempo + cobertura territorial + balance de carga de bases).
- Predicción ML de congestión específica de corredores.

## 14. Mantenimiento
- Actualizar dependencias de IA y librerías de red/HTTP periódicamente.
- Revisar `MAJOR_INTERSECTIONS` al cambiar cartografía urbana.
- Testear regresiones tras modificar heurísticas de tráfico.

## 15. Glosario Rápido
| Término | Definición |
|---------|-----------|
| ETA | Tiempo estimado de arribo |
| Onda Verde | Coordinación de semáforos para paso continuo |
| Ventana | Intervalo de tiempo en el que se espera luz verde o prioridad |
| Fallback | Mecanismo de respaldo cuando un servicio falla |
| Interpolación | Cálculo de posición entre puntos discretos de la geometría |

---
**Estado actual:** Arquitectura estable para prototipo avanzado; listo para incorporar fuentes reales de datos de tráfico y mejorar canal de actualización (push).
