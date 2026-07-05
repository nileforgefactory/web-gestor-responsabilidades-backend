# Manual rápido de pruebas — Caja de Herramientas SGR

Entorno 100% en Docker: backend (FastAPI + MySQL + Redis + Qdrant + Ollama) y frontend (Angular compilado, servido por nginx).

## 1. Servicios y URLs

| Servicio | URL | Notas |
|---|---|---|
| Frontend | http://localhost | nginx sirviendo el build de producción de Angular (imagen `gestor-frontend:latest`) |
| Backend API | http://localhost:8000 | FastAPI en Docker (imagen `gestor-backend-api:local`) |
| Swagger / OpenAPI | http://localhost:8000/docs | Probar endpoints sin frontend |
| Healthcheck | http://localhost:8000/health/ready | Debe responder `healthy: true` |
| MySQL | localhost:3307 | user `gestor` / pass `gestor_pass` / db `gestor_responsabilidades` |
| Qdrant | localhost:6333 (solo dentro de red docker) | Colección `rag_chunks` + `proyectos_sgr` |
| Redis | interno (sin puerto expuesto al host) | Sesiones SSE |

Contenedores backend: `gestor-backend-api`, `gestor-backend-mysql`, `gestor-backend-redis`, `gestor-backend-qdrant`, `gestor-backend-ollama`.
Contenedor frontend: `gestor-frontend` (red Docker separada `gestor-frontend`, no comparte red con el backend — el navegador conecta a ambos por `localhost`).

## 1.1 Usuarios de prueba

Todas las rutas de la API van bajo el prefijo `/api/v1` (ej. `POST /api/v1/auth/login`), aunque el frontend ya lo maneja solo.

| Rol | Email | Password | Territorio | Notas |
|---|---|---|---|---|
| **superadmin** | `superadmin@gestor.local` | `SuperAdmin123!` | COLOMBIA (global) | Creado por bootstrap en la migración `a1b2c3d4e5f6`. Es quien puede crear cualquier usuario/admin en cualquier territorio. |
| **administrador** (territorial) | `admin.tello@gov.co` | `AdminTello123!` | COLOMBIA / HUILA / TELLO | Creado para pruebas. Puede crear/gestionar usuarios `usuario` dentro de su mismo territorio (Tello). |
| **usuario** (municipio) | `planeacion.tello@gov.co` | `TelloHuila123!` | COLOMBIA / HUILA / TELLO | Usuario final simulando la Secretaría de Planeación de Tello, Huila. DIVIPOLA `41797`, categoría `6` (valores de prueba, no verificados contra fuente oficial). |

Los dos usuarios de Tello quedan con `estado_onboarding = credenciales_provisionales` y `password_provisional = true`, es decir: al hacer login por primera vez en el frontend, el sistema **forzará el flujo de onboarding obligatorio** (cambio de contraseña → carga del Plan de Desarrollo) antes de dar acceso al resto de módulos. Esto es intencional — replica el comportamiento real para un municipio nuevo.

Si quieres saltarte el onboarding y probar el módulo SGR directamente, puedes forzar el estado en BD:
```bash
docker compose exec mysql mysql -ugestor -pgestor_pass gestor_responsabilidades -e \
  "UPDATE usuarios SET estado_onboarding='plan_analizado', password_provisional=0 WHERE email='planeacion.tello@gov.co';"
```
(Nota: esto no crea un Plan de Desarrollo real; solo destraba el acceso. Sin un plan cargado, el módulo SGR no tendrá datos con qué trabajar.)

Recrear estos usuarios tras un `docker compose down -v` (que borra el volumen de MySQL): usa el superadmin para volver a darlos de alta vía `POST /api/v1/users`, y actualiza manualmente `divipola`/`categoria_municipio`/`nbi`/`icld` por SQL (el endpoint de creación aún no expone esos campos — ver sección 8).

## 2. Comandos de arranque/parada

```bash
# Backend (desde la carpeta del backend)
docker compose up -d --build   # compila (si hace falta) y levanta todo
docker compose logs -f api     # ver logs en vivo
docker compose down            # apagar (los datos persisten en volúmenes)

# Frontend (desde la carpeta del frontend)
docker compose up -d --build   # compila la imagen (multi-stage: node build → nginx) y la levanta
docker compose logs -f         # ver logs de nginx
docker compose down            # apagar
```

Si cambias código del frontend, hay que **reconstruir la imagen** (no hay hot-reload en este modo):
```bash
docker compose build && docker compose up -d
```

La variable `BACKEND_URL` (por defecto `http://localhost:8000`) se inyecta en el JS compilado al arrancar el contenedor (`entrypoint.sh`), así que el navegador siempre apunta a la URL pública del backend.

Si `alembic` no está al día tras un `docker compose up` del backend:
```bash
docker compose exec api alembic upgrade head
docker compose exec api alembic current   # debe mostrar "sgr001 (head)"
```

## 3. Flujo de prueba end-to-end (UI)

### Paso 0 — Login / Onboarding
1. Entra a `http://localhost`.
2. Si es un usuario nuevo con contraseña provisional → te redirige a `/onboarding/cambiar-contrasena`.
   - Regla: mínimo 10 caracteres, mayúscula + minúscula + número, distinta a la provisional.
3. Tras cambiar la contraseña → redirige a `/onboarding/cargar-plan`.

### Paso 1 — Cargar el Plan de Desarrollo
1. Sube un PDF de Plan de Desarrollo municipal (usa alguno de `sample_documents/` del backend si no tienes uno propio).
2. Espera el análisis (barra de progreso vía SSE). Al terminar debe mostrar brechas, responsabilidades, leyes, matriz.

### Paso 2 — Ir al módulo SGR
1. Desde **Biblioteca** → abre el plan recién analizado.
2. En el detalle del plan, botón verde **💰 Evaluar SGR** (arriba en la card de análisis, o en el sidebar "Acciones").
3. Te lleva a `/sgr/oportunidades/{planId}` — lista de candidatos SGR generados desde las brechas (Modo 1), con score, semáforo y 4 mini-dimensiones.

### Paso 3 — Ficha MGA (Modo 1)
1. Desde un candidato, botón **Generar Ficha MGA** → `/sgr/ficha-mga/{proyectoId}`.
2. Verifica las 4 secciones: Identificación, Preparación, Evaluación, Programación.
3. Prueba el botón de regenerar y el de copiar texto por sección.

### Paso 4 — Verificación de duplicidad
1. Desde el mismo candidato, botón **Verificar duplicidad** → `/sgr/duplicidad/{proyectoId}`.
2. Revisa: nivel (ALTO/MEDIO/BAJO), score de similitud, proyecto similar (si existe), lista de similares en Qdrant.
3. Si `nivel = ALTO` debe mostrarse el banner de bloqueo (animación pulse).

### Paso 5 — Evaluación inversa (Modo 2)
1. Desde el navbar, ítem **SGR** (💰) → `/sgr/evaluar-proyecto`.
2. Pega un texto de proyecto (mínimo 50 caracteres). Opcional: `plan_id`, `proyecto_id`.
3. Revisa las 4 pestañas del resultado:
   - **Resumen** — grid de las 4 dimensiones con semáforo.
   - **Dimensiones** — hallazgos y recomendaciones por dimensión.
   - **Plan** — evidencia de si el proyecto está respaldado en el plan.
   - **Concejo** — checklist de inclusión + botón para copiar el texto de Acuerdo sugerido.

## 4. Flujo de prueba end-to-end (Swagger, sin UI)

Abre `http://localhost:8000/docs`.

1. `POST /auth/login` → copia el `access_token`.
2. Botón **Authorize** (candado arriba a la derecha) → pega el token.
3. Sube un plan (endpoint de ingesta de PDF) y espera a que el estado sea `plan_analizado`.
4. `POST /sgr/evaluar-plan/{plan_id}` → lista de candidatos con `proyecto_id`.
5. `POST /sgr/verificar-duplicidad/{proyecto_id}`.
6. `POST /sgr/generar-ficha-mga/{proyecto_id}`.
7. `POST /sgr/evaluar-proyecto` con body:
   ```json
   {
     "texto_proyecto": "Construcción de acueducto veredal para 200 familias...",
     "plan_id": "<uuid-del-plan>",
     "guardar": true
   }
   ```

## 5. Casos de prueba sugeridos (según el documento del proyecto)

| Caso | Texto de ejemplo | Resultado esperado |
|---|---|---|
| Verde (óptimo) | Acueducto veredal para 200 familias | Alta alineación al plan, semáforo VERDE, cuadrante ÓPTIMO |
| Amarillo | Dotación de tablets para escuelas | Cobertura parcial, sugiere ampliar alcance, AMARILLO |
| Rojo | Parque recreativo urbano sin brecha priorizada | Baja alineación, ROJO, top 3 alternativas sugeridas |
| Duplicidad ALTA | Reingresar el mismo proyecto ya evaluado | Debe bloquear (`bloqueado: true`) |

## 6. Troubleshooting rápido

- **`health/ready` = false** → revisa `docker compose logs api` y `docker compose logs ollama-pull` (modelos no descargados).
- **Frontend no refleja cambios de código** → la imagen es un build estático; hay que `docker compose build && docker compose up -d` de nuevo tras editar.
- **Frontend no puede llamar al backend (CORS / red rara)** → confirma `BACKEND_URL` en `docker-compose.yml` del frontend (por defecto `http://localhost:8000`); el navegador resuelve `localhost`, no la red interna de Docker.
- **401 en el frontend** → el token expiró; vuelve a hacer login.
- **Duplicidad no encuentra nada en Qdrant** → normal en la primera consulta; el sistema cae a datos.gov.co y auto-indexa para la próxima vez.
- **MGA con campos vacíos** → revisa que el LLM (Ollama/Gemini/OpenAI según configuración) esté respondiendo; ver logs de `api` para el prompt/respuesta cruda.

## 7. Apagar el entorno

```bash
# Backend (desde la carpeta del backend)
docker compose down

# Frontend (desde la carpeta del frontend)
docker compose down
```

## 8. Bug encontrado y corregido durante esta sesión

Al crear los usuarios de prueba (`POST /api/v1/users`) se detectó un error 500 real:

```
sqlalchemy.exc.MissingGreenlet: greenlet_spawn has not been called; can't call await_only() here.
```

**Causa:** en `app/slices/auth/repository.py::create_user`, tras el `flush()` solo se refrescaba el atributo `role`. Las columnas `creado_en`/`actualizado_en` tienen `server_default=func.now()`, así que quedan "expiradas" y SQLAlchemy intenta recargarlas de forma perezosa (lazy) en cuanto `to_user_summary()` las lee — y con el driver async eso dispara `MissingGreenlet` porque el lazy-load no está dentro de un contexto `await`.

**Fix aplicado:**
```python
# antes
await db.refresh(user, attribute_names=["role"])
# después
await db.refresh(user, attribute_names=["role", "creado_en", "actualizado_en"])
```

Esto significa que **antes de este fix, crear cualquier usuario/admin vía API fallaba siempre con 500** (no era un problema del entorno de pruebas, sino un bug latente). Ya está corregido y la imagen `gestor-backend-api:local` reconstruida lo incluye. Pendiente: commitear el cambio si quieres dejarlo en el repo (`git add app/slices/auth/repository.py`).

Además, quedó identificado el gap ya conocido: `UserCreateRequest` no expone `divipola`/`categoria_municipio`/`nbi`/`icld`, por lo que esos campos SGR del perfil municipal solo se pueden cargar manualmente por SQL tras crear el usuario (como se hizo arriba para Tello). Si se va a automatizar el alta de municipios Cat. 5/6, vale la pena extender ese schema.
