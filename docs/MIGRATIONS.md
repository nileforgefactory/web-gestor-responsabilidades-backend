# Migraciones MySQL (Alembic)

**Ninguna migración se ejecuta al arrancar la API.** Solo vía CLI (`alembic upgrade` / `alembic downgrade`).

---

## Cadena de revisiones

```text
(base)
  └── 0001_initial_schema     → crea todas las tablas (create_all)
        └── 740b43697f28      → ajusta server_default de timestamps
              └── a1b2c3d4e5f6 (head) → seed roles + superadmin
```

| Revisión | `down_revision` | Upgrade | Downgrade revierte a |
|----------|-----------------|---------|----------------------|
| `0001_initial_schema` | `None` | `Base.metadata.create_all()` | `drop_all()` → BD vacía |
| `740b43697f28` | `0001_initial_schema` | `server_default now()` en 4 columnas | Mismos defaults (reversible) |
| `a1b2c3d4e5f6` | `740b43697f28` | Inserta 3 roles + usuario superadmin | Borra superadmin y roles sin usuarios referenciados |

Comprobar cadena:

```bash
alembic history --verbose
alembic current
```

---

## Arranque limpio completo (recomendado)

### Opción A — script PowerShell

```powershell
cd D:\Empresa\Agentic\web-gestor-responsabilidades-backend
.\scripts\db-fresh-start.ps1
```

Hace: `docker compose down -v` → build API → MySQL → `alembic upgrade head` → `docker compose up -d`.

### Opción B — paso a paso

```powershell
cd D:\Empresa\Agentic\web-gestor-responsabilidades-backend

# 1. Borrar contenedores y volúmenes (datos MySQL/Qdrant/etc.)
docker compose down -v --remove-orphans

# 2. Reconstruir imagen con migraciones actuales
docker compose build api

# 3. Solo MySQL hasta que esté healthy
docker compose up -d mysql

# 4. Migraciones MANUALES (obligatorio antes de usar la API)
docker compose run --rm api alembic upgrade head
docker compose run --rm api alembic current
# Debe mostrar: a1b2c3d4e5f6 (head)

# 5. Levantar todo
docker compose up -d
```

### Variables del superadmin (opcional, antes del paso 4)

En `.env` o en `docker-compose.yml` → servicio `api`:

```env
AUTH_BOOTSTRAP_ADMIN_EMAIL=superadmin@gestor.local
AUTH_BOOTSTRAP_ADMIN_PASSWORD=SuperAdmin123!
AUTH_BOOTSTRAP_ADMIN_NOMBRE=Super Administrador
AUTH_BOOTSTRAP_ADMIN_TERRITORIO=["COLOMBIA", null, null]
```

Si no se definen, la migración `a1b2c3d4e5f6` usa esos valores por defecto.

### Verificar

```powershell
docker compose exec mysql mysql -ugestor -pgestor_pass gestor_responsabilidades -e "SELECT codigo, nombre FROM roles;"
docker compose exec mysql mysql -ugestor -pgestor_pass gestor_responsabilidades -e "SELECT email, coleccion_id FROM usuarios;"
curl http://localhost:8000/health/ready
```

---

## Aplicar migraciones (entorno ya levantado)

```bash
# Docker
docker compose exec api alembic upgrade head

# Host local (MySQL en :3307)
alembic upgrade head
```

---

## Downgrade (revertir revisiones)

Un paso hacia atrás desde la revisión actual:

```bash
docker compose exec api alembic downgrade -1
```

Ir a una revisión concreta:

```bash
# Solo datos auth (tablas roles/usuarios siguen existiendo)
docker compose exec api alembic downgrade 740b43697f28

# Esquema inicial sin seed auth
docker compose exec api alembic downgrade 0001_initial_schema

# BD completamente vacía (drop_all)
docker compose exec api alembic downgrade base
```

| Comando | Efecto |
|---------|--------|
| `downgrade -1` desde `head` | Quita superadmin + roles seed (`a1b2` downgrade) |
| `downgrade 740b43697f28` | Igual que arriba si está en `head` |
| `downgrade 0001_initial_schema` | + revierte defaults de `740b` |
| `downgrade base` | + elimina **todas** las tablas (`0001` downgrade) |

> Para empezar de cero en desarrollo es más simple `docker compose down -v` que encadenar downgrades.

---

## Desarrollo local sin Docker (solo MySQL en Docker)

```powershell
docker compose up -d mysql
# .env con MYSQL_URL=mysql+aiomysql://gestor:gestor_pass@localhost:3307/gestor_responsabilidades?charset=utf8mb4
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

---

## Nueva migración (tras cambiar modelos)

```bash
alembic revision --autogenerate -m "descripcion_corta"
# Revisar alembic/versions/XXXX_descripcion_corta.py
# Confirmar down_revision apunta a la revisión anterior (head actual)
alembic upgrade head
```

En Docker:

```bash
docker compose exec api alembic revision --autogenerate -m "descripcion_corta"
docker compose exec api alembic upgrade head
```

---

## Solución de problemas

### `Table 'roles' already exists`

La revisión `a1b2c3d4e5f6` **no crea tablas** (las crea `0001`). Si ves este error, la imagen Docker está desactualizada:

```powershell
docker compose build api
docker compose run --rm api alembic upgrade head
```

### `alembic_version` desincronizado con tablas reales

Arranque limpio:

```powershell
docker compose down -v
.\scripts\db-fresh-start.ps1
```

### La API responde 503 en rutas MySQL

Falta `MYSQL_URL` o no se ejecutó `alembic upgrade head`.

---

## Estructura

```text
alembic.ini
alembic/env.py
alembic/versions/
  0001_initial_schema.py
  740b43697f28_baseline.py
  a1b2c3d4e5f6_add_usuarios.py
app/db/models_registry.py
scripts/db-fresh-start.ps1
```

La API (`app/main.py`) **no** invoca `run_migrations` al arrancar.
