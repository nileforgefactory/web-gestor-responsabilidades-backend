# Despliegue — Hostinger VPS + Coolify

Dominio: `nilesfactory.com` · VPS: `177.7.50.136` · Panel: `https://coolify.nilesfactory.com`

Los valores reales de contraseñas/keys **no están en este archivo** (no se versionan).
Viven en:
1. `docs/DEPLOY.secrets.md` (local, gitignored) — copia de referencia.
2. Coolify → cada recurso → Environment Variables (fuente de verdad real).
3. Tu gestor de contraseñas (1Password/Bitwarden) — recomendado como respaldo definitivo.

---

## 0. Ya hecho (no repetir)

- [x] VPS Hostinger + Coolify instalado
- [x] DNS: `app`, `api`, `coolify`, `qa-app`, `qa-api`, `dev-app`, `dev-api` → `177.7.50.136`
- [x] Firewall (`ufw`): solo `22`, `80`, `443` abiertos
- [x] Dominio propio de Coolify con SSL
- [x] GitHub App conectada en Coolify (Sources) para backend y frontend
- [x] Producción desplegada y funcionando (`app.nilesfactory.com` / `api.nilesfactory.com`)

---

## 1. Producción — backend

1. Project → Environment `production` → **+ New Resource → Docker Compose**
2. Repo `web-gestor-responsabilidades-backend`, branch `main`
3. **Build Pack**: `Docker Compose` (cambiarlo manualmente, no queda en Nixpacks)
4. **Docker Compose Location**: `/docker-compose.coolify.yml`
5. Environment Variables: ver `DEPLOY.secrets.md` → sección "Producción"
6. **Domains for api**: `https://api.nilesfactory.com` (dejar vacíos ollama/qdrant/mysql/redis)
7. Deploy
8. Terminal → contenedor `api` → `alembic upgrade head`

## 2. Producción — frontend

1. Environment `production` → **+ New Resource → Docker Compose**
2. Repo `web-gestor-responsabilidades-frontend`, branch `main`
3. **Docker Compose Location**: `/docker-compose.yml`
4. Environment Variables: `BACKEND_URL=https://api.nilesfactory.com`
5. **Domains for frontend**: `https://app.nilesfactory.com`
6. Deploy

## 3. QA y Develop — stack compartido (una sola vez)

1. Environment `staging` → **+ New Resource → Docker Compose**
2. Repo backend, branch `staging`
3. **Docker Compose Location**: `/docker-compose.shared-nonprod.yml`
4. Environment Variables: ver `DEPLOY.secrets.md` → sección "Shared QA/Dev"
5. **Domains**: ninguno en ningún servicio
6. Deploy → esperar mysql/redis/qdrant/ollama sanos
7. Crear la 2ª base de datos a mano (el stack solo crea `gestor_qa` automático vía `MYSQL_DATABASE`):
   ```bash
   docker exec -it <contenedor_mysql_shared> mysql -uroot -p"<MYSQL_ROOT_PASSWORD>" \
     -e "CREATE DATABASE IF NOT EXISTS gestor_dev CHARACTER SET utf8mb4; GRANT ALL PRIVILEGES ON gestor_dev.* TO 'gestor'@'%'; FLUSH PRIVILEGES;"
   ```
8. Obtener el nombre real de la red que Coolify asignó (necesario para los pasos 4 y 5):
   ```bash
   docker ps --format "{{.Names}}" | grep mysql
   docker inspect <contenedor_mysql_shared> --format "{{json .NetworkSettings.Networks}}"
   ```
   El nombre de la red = la clave del JSON (ej. `c8ogqj8buktyauvtg79rbvjy`). Guardarlo como `SHARED_NETWORK_NAME`.

## 4. QA — backend-qa

1. Environment `staging` → **+ New Resource → Docker Compose**
2. Repo backend, branch `staging`
3. **Docker Compose Location**: `/docker-compose.api-nonprod.yml`
4. Environment Variables: ver `DEPLOY.secrets.md` → sección "backend-qa" **+** `SHARED_NETWORK_NAME=<uuid del paso 3.8>`
5. **Domains for api**: `https://qa-api.nilesfactory.com`
6. Deploy → Terminal → `alembic upgrade head`

## 5. Develop — backend-dev

1. Environment `development` → **+ New Resource → Docker Compose**
2. Repo backend, branch `develop`
3. **Docker Compose Location**: `/docker-compose.api-nonprod.yml`
4. Environment Variables: ver `DEPLOY.secrets.md` → sección "backend-dev" **+** `SHARED_NETWORK_NAME=<mismo uuid>`
5. **Domains for api**: `https://dev-api.nilesfactory.com`
6. Deploy → Terminal → `alembic upgrade head`

## 6. Frontends QA y Dev

**frontend-qa**: Environment `staging`, repo frontend branch `staging`, `/docker-compose.yml`, `BACKEND_URL=https://qa-api.nilesfactory.com`, dominio `qa-app.nilesfactory.com`.

**frontend-dev**: Environment `development`, repo frontend branch `develop`, `/docker-compose.yml`, `BACKEND_URL=https://dev-api.nilesfactory.com`, dominio `dev-app.nilesfactory.com`.

---

## Gotchas encontrados (para no repetirlos)

- **Coolify ignora `container_name` y nombres de red personalizados** en docker-compose — genera los suyos con el UUID del recurso. Por eso `backend-qa`/`backend-dev` necesitan `SHARED_NETWORK_NAME` apuntando al UUID real, y los hostnames dentro del compose son simples (`mysql`, `redis`, `qdrant`, `ollama`), no `shared-nonprod-*`.
- **No usar `${VAR:?mensaje}`** en los compose — Coolify lo interpreta mal y bloquea el guardado de Environment Variables con error "Cannot delete environment variable X". Usar `${VAR}` simple.
- **No publicar puertos al host** (`ports: "8000:8000"`) en servicios detrás de dominio — choca con el proxy Traefik de Coolify. Usar `expose` en su lugar.
- **`entrypoint.sh` del frontend** reemplaza el placeholder `__BACKEND_URL__` en tiempo de arranque — `environment.prod.ts` debe usar literalmente `'__BACKEND_URL__'`, no una URL hardcodeada, o el reemplazo no tiene nada que sustituir.
- **Variables de Coolify no aplican hasta un Redeploy** — guardar el valor no reinicia el contenedor solo.
- **Migraciones**: `0001_initial_schema` crea el esquema completo vía `create_all()` desde el estado ACTUAL de los modelos. En una base nueva, migraciones posteriores que hacen `ADD COLUMN`/`CREATE TABLE` de campos que ya están en los modelos van a chocar con "Duplicate column/table" — deben ser idempotentes (verificar existencia antes de aplicar).
- **`op.bulk_insert` en migraciones** bypasea los defaults de Python del ORM (`default=`) — si una columna es `NOT NULL` sin `server_default`, hay que pasar el valor explícito en el insert crudo.
- Git: si otra sesión de Claude/terminal está trabajando en el mismo repo local en paralelo, revisar `git status`/`git branch --show-current` antes de cualquier `checkout`/`commit` para no pisar cambios sin commitear de esa sesión.
