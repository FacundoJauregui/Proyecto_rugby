# Proyecto Rugby (SportFrame)

Aplicación Django para cargar y analizar partidos de rugby a partir de videos de YouTube y CSVs de jugadas. Incluye reproductor con selección de jugadas, exportación CSV, presets de selección y API read-only.

## Requisitos
- Python 3.10+
- PostgreSQL 13+

## Instalación rápida (Windows PowerShell)

```powershell
# 1) Crear entorno virtual
python -m venv .venv
. .\.venv\Scripts\Activate.ps1

# 2) Instalar dependencias
pip install -r requirements.txt

# 3) Configurar BD PostgreSQL
# Crea la base de datos 'rugby_player_db' y ajusta credenciales en settings.py

# 4) Migrar y crear usuario admin
python manage.py migrate
python manage.py createsuperuser

# 5) Ejecutar
python manage.py runserver
```

## Variables de entorno recomendadas
Mover SECRET_KEY, DEBUG, ALLOWED_HOSTS y credenciales de BD a variables de entorno. Ejemplo:

- DJANGO_SECRET_KEY
- DJANGO_DEBUG (True/False)
- DATABASE_URL (postgres://usuario:password@localhost:5432/rugby_player_db)

Se sugiere usar `django-environ`.

## Endpoints principales
- Web
  - /matches/ (lista)
  - /matches/upload/ (carga CSV + video)
  - /matches/<id>/ (reproductor)
- API
  - /api/matches/
  - /api/matches/{id}/plays/

## Notas
- DataTables está servido desde static/vendor, sin CDN.
- JWT habilitado (simplejwt).
