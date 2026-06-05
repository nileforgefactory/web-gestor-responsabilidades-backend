# Migraciones MySQL (Alembic)

El esquema relacional lo definen los modelos en `app/slices/*/models.py`. Las revisiones viven en `alembic/versions/`.

---

## Comportamiento por entorno

| Entorno | `APP_ENV` | Migraciones al arrancar la API |
|---------|-----------|--------------------------------|
| Desarrollo / Docker local | `dev`, `docker` | **Automáticas** (`alembic upgrade head`) |
| Producción | `prod` | **Manuales** — la API **no** migra sola |

La API usa `effective_mysql_run_migrations`: en `prod`/`production` siempre es `false`, aunque `MYSQL_RUN_MIGRATIONS=true`.

---

## Desarrollo y Docker (automático)

Con `docker compose up --build -d` (o `-f docker-compose.gpu.yml`):

1. MySQL arranca con la base vacía (primer volumen).
2. La API ejecuta Alembic al iniciar.
3. No hace falta ningún paso extra.

Variables en `docker-compose.yml`:

```env
APP_ENV=docker
MYSQL_RUN_MIGRATIONS=true
```

Sin archivo `.env`, Alembic usa por defecto `localhost:3307` (credenciales de `docker-compose.yml`). Requiere MySQL levantado (`docker compose up -d mysql`).

---

## Producción (manual)

Perfil prod: `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d`

Antes o después de desplegar una versión con **nuevas migraciones**, entrar al contenedor backend y ejecutar:

```bash
docker compose exec api alembic upgrade head
```

Comprobar revisión activa:

```bash
docker compose exec api alembic current
```

En producción `APP_ENV=prod` y `MYSQL_RUN_MIGRATIONS=false`.

---

## Crear una nueva migración (desarrollo)

Tras cambiar un modelo SQLAlchemy:

```bash
# Desde el host (con .env y MySQL accesible)
alembic revision --autogenerate -m "descripcion del cambio"

# Revisar alembic/versions/XXXX_descripcion.py
alembic upgrade head
```

En Docker (sin instalar Python en el host):

```bash
docker compose exec api alembic revision --autogenerate -m "descripcion del cambio"
docker compose exec api alembic upgrade head
```

Alembic **no** genera migraciones solo: hay que ejecutar `revision --autogenerate` después de editar modelos.

---

## Estructura

```text
alembic.ini
alembic/env.py
alembic/versions/
app/db/models_registry.py   # importa todos los modelos
app/db/migrate.py           # upgrade al arrancar (solo no-prod)
database/README.md
```

---

## Arranque desde cero (volúmenes nuevos)

```powershell
docker compose down -v
docker compose up --build -d
# GPU: docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build -d
```

MySQL queda vacío; la API aplica `0001_initial_schema` en el primer arranque (entornos no productivos).
