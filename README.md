# Inmobiliario — Backend (Flask)

API REST del SaaS inmobiliario. Multi-tenant: toda tabla de negocio cuelga de
una `Agency`, y el scoping se aplica a nivel de aplicación leyendo
`agency_id` del JWT (ver `app/utils/tenancy.py`) — nunca confiar en un
`agency_id` que venga del cliente.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Editá `.env` y pegá tu connection string de Supabase en `DATABASE_URL`
(`postgresql://postgres:<password>@db.<project-ref>.supabase.co:5432/postgres`).
Si lo dejás vacío, la app usa un SQLite local (`dev.db`) para desarrollo sin
credenciales.

```bash
flask db upgrade   # aplica las migraciones
flask run          # http://127.0.0.1:8000
```

Nota (macOS): el puerto 5000 es usado por AirPlay Receiver (AirTunes), por eso
`FLASK_RUN_PORT=8000` en `.env` — `flask run` ya levanta ahí por default. Para
probar con `curl` usá `127.0.0.1:8000` en vez de `localhost:8000`.

## Estructura

```
app/
  __init__.py       # application factory
  extensions.py      # db, migrate, jwt, cors
  config.py
  models/            # Agency, User (resto de los módulos se agregan por fase)
  blueprints/        # un blueprint por módulo, montado en /api/<modulo>
  utils/             # tenancy.py (scoping por agencia), slugify.py
migrations/          # Alembic
tests/
```

Cada blueprint de negocio (`properties`, `offers`, `clients`, `bookings`,
`payments`, `documents`, `team`, `availability`, `public`) está scaffoldeado
como stub (`GET /api/<modulo>/` devuelve 501) y se va implementando por fase
según el plan del producto. `auth` también es stub por ahora — se implementa
en la fase 1 (alta de agencia + login + JWT).

## Tests

```bash
pytest
```
