# 🚀 Guía de Deploy en Render - Sistema de Emergencias CABA

## ✅ Cambios Implementados

### 1. **Configuración de Base de Datos PostgreSQL**
- ✅ `settings.py` ahora usa `DATABASE_URL` automáticamente
- ✅ Agregado soporte para `dj-database-url`
- ✅ Fallback a SQLite en desarrollo local

### 2. **Creación Automática de Superuser**
- ✅ Command: `python manage.py ensuresuperuser`
- Usuario: **Admin**
- Email: **roaniamusic@gmail.com**
- Password: **Coordinacion2031**

### 3. **Interfaz Web para Poblar Datos**
- ✅ URL: `/admin-tools/populate/`
- Solo accesible para superusers
- Pobla 32 hospitales, 73 comisarías, vehículos, agentes, etc.

### 4. **Configuración Watson**
- ✅ Variables de entorno configuradas en Render
- ✅ Sistema detecta proveedor Watson correctamente

---

## 🔧 Configuración en Render

### **Start Command** (actualizar en Render):

```bash
cd emergency_system && python manage.py migrate --noinput && python manage.py ensuresuperuser && python manage.py collectstatic --noinput && gunicorn emergency_app.wsgi:application --bind 0.0.0.0:$PORT --timeout 120
```

**Qué hace:**
1. `migrate --noinput` → Aplica solo migraciones pendientes (no reaplica las existentes)
2. `ensuresuperuser` → Crea superuser Admin si no existe
3. `collectstatic --noinput` → Recolecta archivos estáticos
4. `gunicorn --timeout 120` → Inicia servidor web con timeout de 120 segundos (necesario para operaciones largas)

---

### **Variables de Entorno en Render** ✅ Ya configuradas:

⚠️ **IMPORTANTE**: Verifica que estas variables estén exactamente así en Render (Settings → Environment):

| Variable | Valor | Nota |
|----------|-------|------|
| `DATABASE_URL` | `postgresql://ova_user:...` | Auto por link a PostgreSQL |
| `AI_PROVIDER` | `watson` | ⚠️ TODO EN MINÚSCULAS |
| `WATSON_API_KEY` | `azE6dXNyX2U1NzUzNDU0...` | Tu API key de Watson |
| `WATSON_INSTANCE_URL` | `https://api.dl.watson-orchestrate.ibm.com/instances/...` | Tu instancia de Watson |
| `WATSON_IAM_URL` | `https://iam.platform.saas.ibm.com/siusermgr/api/1.0/apikeys/token` | Endpoint IAM (platform.saas) |

---

## 📝 Pasos para Deploy

### 1. **Actualizar Start Command en Render**
Ve a tu Web Service → **Settings** → **Build & Deploy** → **Start Command** y pega:

```bash
cd emergency_system && python manage.py migrate --noinput && python manage.py ensuresuperuser && python manage.py collectstatic --noinput && gunicorn emergency_app.wsgi:application --bind 0.0.0.0:$PORT --timeout 120
```

### 2. **Forzar Redeploy**
- Ve a **Manual Deploy** → **Deploy latest commit**
- Espera que termine el build (~3-5 minutos)

### 3. **Verificar que funciona**
Accede a: `https://ova-tujh.onrender.com/`

---

## 🎯 Después del Deploy

### **1. Acceder al Admin de Django**
URL: `https://ova-tujh.onrender.com/admin/`

**Credenciales:**
- Username: `Admin`
- Password: `Coordinacion2031`

### **2. Poblar Base de Datos**
URL: `https://ova-tujh.onrender.com/admin-tools/populate/`

O desde el admin:
1. Login en `/admin/`
2. Ve a `/admin-tools/populate/`
3. Click en **"📦 Poblar Base de Datos"**
4. Confirma la acción
5. Espera ~10-20 segundos
6. Se crearán automáticamente:
   - 32 Hospitales
   - 73 Comisarías
   - ~180 Vehículos
   - ~250 Agentes
   - 12 Emergencias de ejemplo

### **3. Verificar Estado de Watson**
URL: `https://ova-tujh.onrender.com/ai-status/`

Deberías ver:
```
Proveedor configurado: WATSON
API Key cargada: ✅ Sí
Endpoint IAM: https://iam.platform.saas.ibm.com/...
```

---

## 🔍 Troubleshooting

### **Si aún muestra OpenAI en lugar de Watson:**
1. **Verifica la variable `AI_PROVIDER` en Render:**
   - Ve a Settings → Environment
   - Busca `AI_PROVIDER`
   - Debe estar escrita exactamente como: `watson` (todo en minúsculas)
   - Si no existe o está mal escrita (ej: `Watson`, `WATSON`), edítala o créala
2. **Verifica las otras variables de Watson:**
   - `WATSON_API_KEY` debe tener tu API key completa
   - `WATSON_INSTANCE_URL` debe apuntar a tu instancia
   - `WATSON_IAM_URL` debe ser: `https://iam.platform.saas.ibm.com/siusermgr/api/1.0/apikeys/token`
3. **Fuerza un redeploy manual:**
   - Cualquier cambio en variables de entorno requiere redeploy
   - Ve a Manual Deploy → Deploy latest commit
4. **Revisa los logs del deploy:**
   - Si hay errores de Watson, aparecerán en los logs
   - Busca mensajes como "Watson Orchestrate conectado" o errores de token IAM

### **Si no puede conectarse a PostgreSQL:**
1. Verifica que `DATABASE_URL` esté configurada
2. Asegúrate de haber linkeado la base de datos PostgreSQL

### **Si el superuser no se crea:**
- Es normal si ya existe
- Puedes crearlo manualmente desde la shell (plan Pro) o desde el admin

---

## 📊 URLs Importantes

| Descripción | URL |
|-------------|-----|
| **Home** | https://ova-tujh.onrender.com/ |
| **Dashboard** | https://ova-tujh.onrender.com/dashboard/ |
| **Admin Django** | https://ova-tujh.onrender.com/admin/ |
| **Poblar Datos** | https://ova-tujh.onrender.com/admin-tools/populate/ |
| **Estado Watson** | https://ova-tujh.onrender.com/ai-status/ |
| **Lista Emergencias** | https://ova-tujh.onrender.com/list/ |
| **Crear Emergencia** | https://ova-tujh.onrender.com/create/ |

---

## ✅ Checklist Final

- [ ] Start Command actualizado en Render
- [ ] Variables de entorno Watson configuradas
- [ ] Deploy ejecutado y exitoso
- [ ] Admin accesible con credenciales
- [ ] Base de datos poblada
- [ ] Watson se muestra como proveedor activo
- [ ] Dashboard funcional con datos

---

## 🎉 Listo!

Una vez completados todos los pasos, tu aplicación estará completamente funcional en producción con:
- ✅ PostgreSQL en Render
- ✅ Watson como proveedor de IA
- ✅ Datos de ejemplo poblados
- ✅ Admin accesible
- ✅ Sistema de emergencias operativo
