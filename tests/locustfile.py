"""CP03 · Prueba de carga con Locust (informe, sección 9).

Simula técnicos que descargan su paquete de datos y sincronizan formularios.
Uso (contra un entorno de pruebas, nunca contra datos reales):

    pip install locust
    export COVEPA_CORREO=tecnico@covepa.test COVEPA_CLAVE=...
    export COVEPA_EQUIPO=GEN-FRE-01 COVEPA_PLANTILLA_ID=1
    locust -f tests/locustfile.py --host https://TU-PROYECTO.vercel.app --users 20 --spawn-rate 2 --run-time 3m --headless

Los formularios enviados usan fotos de Cloudinary inexistentes, por lo que el servidor responde 400 a propósito:
esa es la ruta completa de validación (sesión, CSRF, plantilla en Mongo, Cloudinary). Para medir también la escritura
en las dos bases, define COVEPA_PUBLIC_ID con una foto real ya subida a la carpeta autorizada
(cada envío usa un UUID nuevo, así que cada uno crea un registro)."""

import json
import os
import uuid
from datetime import datetime, timedelta, timezone

from locust import HttpUser, between, task

CORREO = os.environ.get("COVEPA_CORREO", "tecnico@covepa.test")
CLAVE = os.environ.get("COVEPA_CLAVE", "")
EQUIPO = os.environ.get("COVEPA_EQUIPO", "GEN-FRE-01")
PLANTILLA_ID = int(os.environ.get("COVEPA_PLANTILLA_ID", "1"))
PUBLIC_ID = os.environ.get("COVEPA_PUBLIC_ID", "")


class Tecnico(HttpUser):
    wait_time = between(2, 6)

    def on_start(self):
        r = self.client.get("/cuentas/login/", name="login (GET)")
        token = r.cookies.get("csrftoken", "")
        r = self.client.post(
            "/cuentas/login/",
            {"correo": CORREO, "password": CLAVE, "csrfmiddlewaretoken": token},
            headers={"Referer": self.host + "/cuentas/login/"},
            name="login (POST)",
            allow_redirects=False,
        )
        if r.status_code != 302:
            raise RuntimeError("No se pudo iniciar sesión: revisa COVEPA_CORREO y COVEPA_CLAVE.")
        self.usuario_id = self.client.get("/api/v1/sesion/", name="api sesión").json()["usuario"]["id"]

    @task(3)
    def paquete(self):
        self.client.get("/api/v1/paquete/", name="api paquete")

    @task(1)
    def inicio(self):
        self.client.get("/mantenciones/inicio/", name="pantalla inicio")

    @task(2)
    def sincronizar(self):
        sesion = self.client.get("/api/v1/sesion/", name="api sesión").json()
        ahora = datetime.now(timezone.utc)
        evidencias = []
        if PUBLIC_ID:
            evidencias = [{"campo": "foto_equipo", "tipo": "foto", "url": "", "public_id": PUBLIC_ID, "peso_kb": 100}]
        doc = {
            "_id": str(uuid.uuid4()),
            "equipo": {"codigo": EQUIPO, "categoria": "Generador"},
            "sucursal": "Fresia",
            "plantilla": {"id": PLANTILLA_ID, "nombre": "Generador · prueba semanal", "version": 1},
            "tecnico_id": self.usuario_id,
            "inicio": (ahora - timedelta(minutes=15)).isoformat(),
            "termino": ahora.isoformat(),
            "respuestas": {"horometro_inicial": 1000, "horometro_final": 1001.5, "nivel_aceite_ok": True, "nivel_combustible": "Lleno"},
            "evidencias": evidencias,
            "origen": "app_movil",
        }
        with self.client.post(
            "/api/v1/mantenciones/sincronizar/",
            data=json.dumps(doc),
            headers={"Content-Type": "application/json", "X-CSRFToken": sesion["csrf"], "Referer": self.host + "/"},
            name="api sincronizar",
            catch_response=True,
        ) as r:
            # 201 = guardado; 400 = rechazo de validación esperado cuando no hay foto real
            if r.status_code in (201, 400):
                r.success()
            else:
                r.failure(f"código inesperado {r.status_code}")
