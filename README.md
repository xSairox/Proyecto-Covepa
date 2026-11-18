# COVEPA Mantenciones

Sistema de gestión de inventario y mantenciones de equipos de **COVEPA SpA** (piloto sucursal Fresia).
Proyecto Integrado TIHV43 · INAC AP · Grupo XX_Sección XX

| Capa | Tecnología |
|---|---|
| Aplicación | Django 5.2 (PWA instalable, funciona sin conexión) en **Vercel** |
| Base relacional | PostgreSQL en **Neon** (usuarios, equipos, planes, tickets, auditoría) |
| Base no relacional | **MongoDB Atlas** (formularios completos de mantención y versiones de plantilla) |
| Fotos y videos | **Cloudinary** (subida directa desde el celular, firmada por el servidor) |

Historias de usuario implementadas: HU-01 a HU-09 (usuarios y perfiles, inventario, plantillas, formulario móvil, sincronización sin conexión, tickets, aprobación y cierre, avisos, auditoría).

## 1. Puesta en marcha local

Requiere Python 3.12 o superior.

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows (cmd).  En Mac/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
copy .env.example .env            # Windows (cmd).  En Mac/Linux: cp .env.example .env
```

Deja `DEBUG=True` en el `.env` y las líneas `DATABASE_URL`, `DIRECT_DATABASE_URL` y `MONGODB_URI` **comentadas con `#`** (así viene el archivo): con ellas vacías o comentadas se usa SQLite y MongoDB en memoria. En PowerShell usa `.venv\Scripts\Activate.ps1` y `Copy-Item .env.example .env`.

Con `DEBUG=True` y sin `DATABASE_URL`, `MONGODB_URI` ni credenciales de Cloudinary, el sistema usa **SQLite, MongoDB en memoria y un Cloudinary de mentira**. Sirve para probar pantallas sin crear cuentas. Los datos de MongoDB en memoria se pierden al reiniciar.

**Las migraciones no vienen incluidas**: se generan en tu equipo para que coincidan con tu versión de Django.

```bash
python manage.py makemigrations cuentas inventario mantenciones tickets notificaciones auditoria
python manage.py migrate
python manage.py seed_demo --clave "TuClaveDemo2026"     # datos de Fresia y un usuario por perfil
python manage.py runserver
```

Abre http://127.0.0.1:8000. Usuarios de demostración (los entrega `seed_demo`): `jefatura@covepa.test`, `tecnico@covepa.test`, `externo@covepa.test`, `trabajador@covepa.test`, `auditor@covepa.test`. Jefatura y auditor deben activar la verificación en dos pasos (app autenticadora) en el primer ingreso. Para crear un administrador propio: `python manage.py createsuperuser`.

## 2. Servicios en la nube

### Neon (PostgreSQL)
1. Crea un proyecto en neon.tech (región más cercana, p. ej. São Paulo).
2. En *Connect* copia **dos** cadenas: la **pooled** (host con `-pooler`) → `DATABASE_URL`, y la **directa** → `DIRECT_DATABASE_URL`.
3. Aplica las migraciones desde tu computador, con las dos variables en `.env` y `DEBUG=False` o `True`: `python manage.py migrate` (usa la cadena directa automáticamente).

### MongoDB Atlas
1. Crea un clúster gratuito (M0) y un usuario de base de datos.
2. En *Network Access* permite el acceso desde cualquier IP (`0.0.0.0/0`): las funciones de Vercel no tienen IP fija. La protección es la contraseña de la cadena de conexión.
3. Copia la cadena `mongodb+srv://…` en `MONGODB_URI`. El nombre de la base va en `MONGODB_DB_NAME`.
Las colecciones (`formularios_mantencion`, `versiones_plantilla`) y sus índices se crean solas.

### Cloudinary
Copia *Cloud name*, *API key* y *API secret* del panel. Las fotos y los videos se suben directo desde el celular con una firma que emite el servidor; el servidor luego verifica con la API de Cloudinary que cada archivo exista, esté en la carpeta `CLOUDINARY_FOLDER`, pese lo permitido (foto 10 MB, video 100 MB) y que el video dure 30 segundos o menos.

### Vercel
1. Sube el proyecto a GitHub e impórtalo en vercel.com (Vercel detecta Django con `manage.py`).
2. En *Settings → Environment Variables* agrega **todas** las variables de `.env.example`, con `DEBUG=False`, una `SECRET_KEY` larga y aleatoria, `ALLOWED_HOSTS` y `CSRF_TRUSTED_ORIGINS` con tu dominio (`https://…vercel.app`). Márcalas también para *Build*.
3. Despliega. Revisa `https://TU-DOMINIO/salud/`: debe responder `{"estado": "ok"}` con las dos bases conectadas.
4. `CRON_SECRET`: cualquier texto largo. Vercel lo envía en el cron diario (`/cron/vencimientos/`, 11:00 UTC) que genera los avisos de mantenciones por vencer. El plan Hobby permite un cron por día.

**Si el despliegue falla:**
- `DJANGO_SETTINGS_FAILED` / `No module named 'django'`: Vercel instala desde `pyproject.toml` (tiene prioridad sobre `requirements.txt`). Por eso las dependencias están declaradas en ambos archivos; si agregas una librería, agrégala en los dos (la prueba `core/tests/test_dependencias.py` avisa si se desalinean).
- `"tool.vercel.entrypoint" ... no matching module file`: Vercel no encuentra `config/wsgi.py`. El repositorio debe tener `manage.py` y `config/` en la raíz (o indica la carpeta en *Settings → General → Root Directory*).
- `Faltan variables de entorno obligatorias`: define `SECRET_KEY` y `DATABASE_URL` (y el resto de `.env.example`) en *Settings → Environment Variables* y vuelve a desplegar.

## 3. Pruebas

```bash
pytest core/tests                  # sin base de datos; corren en cualquier equipo con Python
python manage.py test pruebas      # casos CP01–CP09, tickets, permisos, auditoría, PWA
python manage.py verificar_integridad   # compara PostgreSQL y MongoDB (ids de formularios)
```

El detalle de cada caso, la prueba de carga (Locust) y la colección de Postman están en `docs/PROTOCOLO_DE_PRUEBAS.md` y `tests/`.

## 4. Estructura

```
config/          ajustes, urls, wsgi
core/            validadores, permisos, MongoDB, Cloudinary, middleware, PWA (core/pwa/sw.js)
cuentas/         usuarios, perfiles, dos pasos, enlaces de acceso
inventario/      sucursales, categorías, equipos, versiones de software
mantenciones/    plantillas versionadas, planes, registros, API móvil (/api/v1/)
tickets/         máquina de estados, materiales y documentos de respaldo
notificaciones/  avisos por rol y vencimientos
auditoria/       registro de solo inserción (aplicación + trigger en PostgreSQL)
static/ templates/ pruebas/ tests/ docs/
```

Documentación: `docs/er/` (diagrama entidad-relación), `docs/diccionario_datos.md`, `docs/GUIA_ESTILO_6_4.md`.

## 5. Aplicación móvil (PWA)

La interfaz es una *Progressive Web App*: se instala en el celular y se abre a pantalla completa, como una app nativa.

- **Instalable:** `manifest.webmanifest` (`display: standalone`, íconos 192/512 y *maskable*) y etiquetas para iPhone en `templates/base.html`. En Android/Chrome aparece el botón **Instalar la app** en *Mi perfil* (`static/js/instalar.js`); en iPhone se indican los pasos de *Compartir → Añadir a pantalla de inicio*.
- **Sin conexión:** `core/pwa/sw.js` (service worker, servido desde `/sw.js`) guarda los archivos estáticos y las pantallas de terreno (*Mis mantenciones* y *Registrar mantención*); la app las guarda por adelantado al abrir el inicio con señal, así que el técnico debe abrir la app con señal al menos una vez (y de nuevo después de cada actualización).
- **Cola de envío:** los formularios se guardan en IndexedDB (`static/js/db.js`, `sync.js`) y se envían al volver la señal, sin duplicarse (identificador UUID).
- Requiere HTTPS (Vercel lo entrega) o `localhost`.

## 6. Seguridad (resumen)

Contraseñas de 10 o más caracteres con letras y números; bloqueo de 15 minutos tras 5 intentos; verificación en dos pasos obligatoria para jefatura y auditor; sesión de 12 h para técnicos y 30 min para el resto; enlaces de invitación y recuperación de un solo uso (24 h y 1 h); control de acceso por perfil y por equipo asignado (403 y auditoría ante cualquier intento ajeno); auditoría que no se puede editar ni borrar; CSP estricta sin JavaScript en línea; token CSRF en toda la API.

## 7. Límites conocidos

- La sincronización corre mientras la app está abierta o al volver la señal; no usa *Background Sync* (no existe en iPhone).
- No se incluyen los archivos de la fuente Roboto: si no están instalados, la interfaz usa la fuente del sistema.
- Con MongoDB en memoria (desarrollo sin Atlas) los formularios se pierden al reiniciar el servidor.
