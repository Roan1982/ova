@echo off
echo Creando entorno virtual...
python -m venv venv

echo Cambiando al directorio del proyecto...
cd emergency_system

echo Activando entorno virtual...
call ..\venv\Scripts\activate

echo Instalando dependencias...
pip install -r requirements.txt

echo Ejecutando el sistema...
python manage.py runserver

pause