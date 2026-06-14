# Autenticación JWT, roles, usuarios y territorios

La API protege todos los endpoints (excepto salud y login) con **JWT Bearer**. Los usuarios tienen un **rol** (tabla `roles`) y un **territorio** que define qué colecciones pueden consultar.

## Tabla `roles`

| `codigo` | Nombre | Permisos |
|----------|--------|----------|
| `usuario` | Usuario | Solo **lectura** en su territorio |
| `administrador` | Administrador | **Lectura y escritura** en su territorio + gestión de usuarios locales |
| `superadmin` | Super Administrador | **Global**: provisiona usuarios en cualquier territorio, ve todas las colecciones |

Los roles se insertan en la migración `a1b2c3d4e5f6_add_usuarios.py`.

## Superadmin (migración)

Al ejecutar Alembic se crea automáticamente un usuario **superadmin** con credenciales de entorno:

| Variable | Default |
|----------|---------|
| `AUTH_BOOTSTRAP_ADMIN_EMAIL` | `superadmin@gestor.local` |
| `AUTH_BOOTSTRAP_ADMIN_PASSWORD` | `SuperAdmin123!` |
| `AUTH_BOOTSTRAP_ADMIN_NOMBRE` | `Super Administrador` |
| `AUTH_BOOTSTRAP_ADMIN_TERRITORIO` | `["COLOMBIA", null, null]` |

> Cambie la contraseña en producción **antes** de ejecutar la migración, o actualícela después en BD.

El superadmin usa ese login para crear administradores y usuarios en cualquier territorio vía `POST /api/v1/users`.

## Territorio y colecciones

Cada usuario tiene territorio `[País, Departamento, Municipio]` → `coleccion_id`.

Ejemplo Palermo:

```json
["COLOMBIA", "HUILA", "PALERMO"]
```

→ `COLOMBIA_HUILA_PALERMO`

Usuarios territoriales ven su colección + ancestros (`COLOMBIA_HUILA`, `COLOMBIA`). El **superadmin** ve todas las colecciones.

## Variables JWT

| Variable | Default |
|----------|---------|
| `JWT_SECRET_KEY` | *(cambiar en prod)* |
| `JWT_ALGORITHM` | `HS256` |
| `JWT_EXPIRE_MINUTES` | `1440` |

## Modelo de datos

**`roles`**: `id`, `codigo`, `nombre`, `descripcion`

**`usuarios`**: `id`, `nombre`, `email`, `password_hash`, `rol_id` → `roles.id`, `territorio`, `coleccion_id`, `activo`, `eliminado_en`

## Endpoints (`/api/v1`)

| Método | Ruta | Acceso |
|--------|------|--------|
| `POST` | `/auth/login` | Público |
| `GET` | `/me` | Autenticado |
| `GET` | `/roles` | Admin / superadmin |
| `GET` | `/users` | Admin (territorio) / superadmin (todos) |
| `POST` | `/users` | Admin; superadmin asigna `territorio` |
| `PUT` | `/user/{id}/change-rol` | Admin (mismo territorio) / superadmin |
| `DELETE` | `/user/{id}` | Admin / superadmin (no elimina superadmin) |

### Crear usuario en otro territorio (superadmin)

```json
POST /api/v1/users
{
  "nombre": "Admin Neiva",
  "email": "admin.neiva@gov.co",
  "password": "clave-segura-123",
  "rol": "administrador",
  "territorio": ["COLOMBIA", "HUILA", "NEIVA"]
}
```

Solo se pueden asignar roles `usuario` o `administrador` vía API (no `superadmin`).

## Swagger

1. Ejecute migraciones manualmente: `alembic upgrade head` (ver `docs/MIGRATIONS.md`).
2. `POST /api/v1/auth/login` con `superadmin@gestor.local` / `SuperAdmin123!`.
3. **Authorize** → pegue el `access_token`.
4. `GET /roles` → `POST /users` para provisionar territorios.

## curl

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"superadmin@gestor.local","password":"SuperAdmin123!"}' \
  | jq -r .access_token)

curl -s http://localhost:8000/api/v1/me -H "Authorization: Bearer $TOKEN"
```
