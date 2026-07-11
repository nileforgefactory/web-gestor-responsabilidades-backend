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

## 3. QA y Develop — Destination compartida (una sola vez)

Coolify ignora cualquier `networks:` personalizado dentro de un docker-compose — cada
deploy de un recurso `Docker Compose` crea sus propios contenedores en una red aislada
nombrada con el UUID del recurso, **sin importar** lo que haya en el compose ni qué
Destination tenga asignada el recurso (confirmado también con la API de Coolify: el
campo `destination` del recurso muestra la red correcta, pero eso no se refleja en los
contenedores reales creados por `docker compose up`). La única forma que funcionó fue
conectar los contenedores a mano por Docker directo, después de cada deploy.

1. Coolify → **Destinations** → **+ Add** → Name `nonprod-shared`, Network
   `nonprod-shared-net`, Server `localhost` → Continue. (Ya está creada, no repetir).
2. Environment `staging` → **+ New Resource → Docker Compose**
3. Repo backend, branch `staging`
4. **Docker Compose Location**: `/docker-compose.shared-nonprod.yml`
5. Environment Variables: ver `DEPLOY.secrets.md` → sección "Shared QA/Dev"
6. **Domains**: ninguno en ningún servicio
7. Deploy → esperar mysql/redis/qdrant/ollama sanos
8. Conectar los 4 contenedores a la red compartida con sus alias (reemplaza los nombres
   reales, `docker ps --format "{{.Names}}" | grep -E "mysql|redis|qdrant|ollama"`):
   ```bash
   docker network connect --alias mysql  nonprod-shared-net <contenedor_mysql>
   docker network connect --alias redis  nonprod-shared-net <contenedor_redis>
   docker network connect --alias qdrant nonprod-shared-net <contenedor_qdrant>
   docker network connect --alias ollama nonprod-shared-net <contenedor_ollama>
   ```
9. Crear la 2ª base de datos a mano (el stack solo crea `gestor_qa` automático vía `MYSQL_DATABASE`):
   ```bash
   docker exec -it <contenedor_mysql> mysql -uroot -p"<MYSQL_ROOT_PASSWORD>" \
     -e "CREATE DATABASE IF NOT EXISTS gestor_dev CHARACTER SET utf8mb4; GRANT ALL PRIVILEGES ON gestor_dev.* TO 'gestor'@'%'; FLUSH PRIVILEGES;"
   ```

## 4. QA — backend-qa

1. Environment `staging` → **+ New Resource → Docker Compose**
2. Repo backend, branch `staging`
3. **Docker Compose Location**: `/docker-compose.api-nonprod.yml`
4. Environment Variables: ver `DEPLOY.secrets.md` → sección "backend-qa" (ya no usa `SHARED_NETWORK_NAME`)
5. **Domains for api**: `https://qa-api.nilesfactory.com`
6. Deploy
7. Conectar el contenedor `api` a la red compartida:
   ```bash
   docker network connect nonprod-shared-net <contenedor_api_qa>
   ```
8. Terminal → contenedor `api` → `alembic upgrade head`

## 5. Develop — backend-dev

1. Environment `development` → **+ New Resource → Docker Compose**
2. Repo backend, branch `develop`
3. **Docker Compose Location**: `/docker-compose.api-nonprod.yml`
4. Environment Variables: ver `DEPLOY.secrets.md` → sección "backend-dev" (ya no usa `SHARED_NETWORK_NAME`)
5. **Domains for api**: `https://dev-api.nilesfactory.com`
6. Deploy
7. Conectar el contenedor `api` a la red compartida:
   ```bash
   docker network connect nonprod-shared-net <contenedor_api_dev>
   ```
8. Terminal → contenedor `api` → `alembic upgrade head`

⚠️ **El `docker network connect` no sobrevive un Redeploy** — Coolify recrea el
contenedor desde cero y pierde la conexión manual. Después de CUALQUIER redeploy de
`shared-nonprod`, `backend-qa` o `backend-dev`, hay que repetir el `docker network
connect` correspondiente antes de que la app funcione otra vez.

## 6. QA — frontend-qa

1. Environment `staging` → **+ New Resource → Docker Compose**
2. Repo `web-gestor-responsabilidades-frontend`, branch `staging`
3. **Build Pack**: `Docker Compose` (cambiarlo, no lo dejes en Nixpacks)
4. **Docker Compose Location**: `/docker-compose.yml`
5. Environment Variables:
   ```
   BACKEND_URL=https://qa-api.nilesfactory.com
   ```
6. **Domains for frontend**: `https://qa-app.nilesfactory.com`
7. Deploy
8. Verificar en `https://qa-app.nilesfactory.com` con `Ctrl+Shift+R` (caché limpia)

## 7. Develop — frontend-dev

Igual que el anterior, pero:

1. Environment `development` → **+ New Resource → Docker Compose**
2. Repo frontend, branch `develop`
3. **Docker Compose Location**: `/docker-compose.yml`
4. Environment Variables:
   ```
   BACKEND_URL=https://dev-api.nilesfactory.com
   ```
5. **Domains for frontend**: `https://dev-app.nilesfactory.com`
6. Deploy

## 8. Verificación final

Login de prueba en cada entorno con su `AUTH_BOOTSTRAP_ADMIN_EMAIL`/`PASSWORD` correspondiente (QA y Dev tienen credenciales propias, distintas entre sí y de producción — ver `DEPLOY.secrets.md`). Si algo falla (login pegado a `localhost:8000`, error de puerto ya usado, etc.), revisar primero la sección "Gotchas" más abajo — son problemas que ya nos ocurrieron y tienen solución conocida.

---

## Gotchas encontrados (para no repetirlos)

- **Coolify ignora `container_name` y `networks:` personalizados en docker-compose, e incluso ignora la Destination asignada al recurso para los contenedores reales** — cada deploy crea sus propios contenedores en una red aislada nombrada con el UUID del recurso, sin importar qué compose o qué Destination tenga configurada. Ni `external: true`, ni una variable con el nombre de red, ni la función "Destinations" del panel logran que dos recursos `Docker Compose` compartan red automáticamente. La única solución que funcionó: `docker network connect` manual por SSH después de cada deploy (ver sección 3-5). Los hostnames dentro del compose son simples (`mysql`, `redis`, `qdrant`, `ollama`), no `shared-nonprod-*`.
- **La API REST de Coolify** (`Settings → Advanced → API Access`, tokens en `Keys & Tokens → API Tokens`) es mucho más rápida para diagnosticar/corregir que navegar la UI a través de capturas de pantalla — permite crear/editar/desplegar recursos, ver logs de deploy completos y gestionar variables de entorno vía `curl`. Endpoints útiles: `GET/POST /api/v1/applications`, `PATCH .../envs/bulk`, `GET /api/v1/deploy?uuid=`, `GET /api/v1/deployments/{uuid}`. El campo `destination_uuid` solo se puede fijar al crear el recurso (`POST .../private-github-app`), no se puede cambiar después con `PATCH`.
- **No usar `${VAR:?mensaje}`** en los compose — Coolify lo interpreta mal y bloquea el guardado de Environment Variables con error "Cannot delete environment variable X". Usar `${VAR}` simple.
- **No publicar puertos al host** (`ports: "8000:8000"`) en servicios detrás de dominio — choca con el proxy Traefik de Coolify. Usar `expose` en su lugar.
- **`entrypoint.sh` del frontend** reemplaza el placeholder `__BACKEND_URL__` en tiempo de arranque — `environment.prod.ts` debe usar literalmente `'__BACKEND_URL__'`, no una URL hardcodeada, o el reemplazo no tiene nada que sustituir.
- **Variables de Coolify no aplican hasta un Redeploy** — guardar el valor no reinicia el contenedor solo.
- **Migraciones**: `0001_initial_schema` crea el esquema completo vía `create_all()` desde el estado ACTUAL de los modelos. En una base nueva, migraciones posteriores que hacen `ADD COLUMN`/`CREATE TABLE` de campos que ya están en los modelos van a chocar con "Duplicate column/table" — deben ser idempotentes (verificar existencia antes de aplicar).
- **`op.bulk_insert` en migraciones** bypasea los defaults de Python del ORM (`default=`) — si una columna es `NOT NULL` sin `server_default`, hay que pasar el valor explícito en el insert crudo.
- Git: si otra sesión de Claude/terminal está trabajando en el mismo repo local en paralelo, revisar `git status`/`git branch --show-current` antes de cualquier `checkout`/`commit` para no pisar cambios sin commitear de esa sesión.
