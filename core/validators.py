"""Validación de formularios de mantención y de definiciones de plantilla.

Este módulo NO importa Django: así se puede probar de forma aislada y el mismo código
valida tanto el JSON que llega desde el celular como las plantillas que arma la jefatura.

Informe, sección 7.3: "el sistema valida la estructura del JSON, es decir, los campos
obligatorios, los tipos de dato y los rangos, como que el horómetro final sea mayor que el inicial".
"""

from __future__ import annotations

import math
import re
import uuid
from datetime import datetime, timedelta
from typing import Any

TIPOS_CAMPO = ("si_no", "numero", "texto", "lista", "foto", "video")
TIPOS_MEDIA = ("foto", "video")
ORIGENES = ("app_movil_sin_conexion", "app_movil", "web")
CLAVE_RE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
MAX_CAMPOS = 60
MAX_TEXTO = 1000
MAX_EVIDENCIAS = 30
CLAVES_PERMITIDAS = {
    "_id", "equipo", "sucursal", "plantilla", "tecnico_id", "inicio", "termino",
    "respuestas", "evidencias", "origen", "estado", "plan_id",
}
CLAVES_EVIDENCIA = {"campo", "tipo", "url", "public_id", "peso_kb", "duracion_seg"}


class ErrorValidacion(Exception):
    """Reúne todos los errores encontrados para devolverlos juntos al cliente."""

    def __init__(self, errores: list[str]):
        self.errores = list(errores)
        super().__init__("; ".join(self.errores))


# --------------------------------------------------------------------------- plantillas


def validar_definicion_campos(campos: Any) -> list[dict]:
    """Valida y normaliza la lista de campos de una plantilla (HU-03)."""
    errores: list[str] = []
    if not isinstance(campos, list) or not campos:
        raise ErrorValidacion(["La plantilla debe tener al menos un campo."])
    if len(campos) > MAX_CAMPOS:
        raise ErrorValidacion([f"Una plantilla admite como máximo {MAX_CAMPOS} campos."])

    normalizados: list[dict] = []
    claves_vistas: dict[str, str] = {}
    for posicion, bruto in enumerate(campos, start=1):
        if not isinstance(bruto, dict):
            errores.append(f"Campo {posicion}: formato inválido.")
            continue
        clave = str(bruto.get("clave", "")).strip()
        etiqueta = str(bruto.get("etiqueta", "")).strip()
        tipo = bruto.get("tipo")
        prefijo = f"Campo {posicion} ({clave or 'sin clave'})"
        if not CLAVE_RE.match(clave):
            errores.append(f"{prefijo}: la clave debe usar minúsculas, números y guion bajo (ej. horometro_final).")
            continue
        if clave in claves_vistas:
            errores.append(f"{prefijo}: la clave está repetida.")
            continue
        if not etiqueta or len(etiqueta) > 120:
            errores.append(f"{prefijo}: la etiqueta es obligatoria (máx. 120 caracteres).")
        if tipo not in TIPOS_CAMPO:
            errores.append(f"{prefijo}: tipo '{tipo}' no permitido. Use: {', '.join(TIPOS_CAMPO)}.")
            continue
        campo: dict[str, Any] = {
            "clave": clave,
            "etiqueta": etiqueta,
            "tipo": tipo,
            "obligatorio": bool(bruto.get("obligatorio", False)),
        }
        if tipo == "lista":
            opciones = bruto.get("opciones")
            if (
                not isinstance(opciones, list)
                or len(opciones) < 2
                or any(not isinstance(o, str) or not o.strip() for o in opciones)
                or len(set(o.strip() for o in opciones)) != len(opciones)
            ):
                errores.append(f"{prefijo}: una lista necesita al menos 2 opciones distintas.")
            else:
                campo["opciones"] = [o.strip() for o in opciones]
        if tipo == "numero":
            for limite in ("min", "max"):
                valor = bruto.get(limite)
                if valor is not None:
                    if not _es_numero(valor):
                        errores.append(f"{prefijo}: '{limite}' debe ser un número.")
                    else:
                        campo[limite] = valor
            if "min" in campo and "max" in campo and campo["min"] > campo["max"]:
                errores.append(f"{prefijo}: el mínimo no puede superar al máximo.")
            unidad = str(bruto.get("unidad", "")).strip()
            if unidad:
                campo["unidad"] = unidad[:20]
            mayor_que = bruto.get("mayor_que")
            if mayor_que:
                if mayor_que not in claves_vistas or claves_vistas[mayor_que] != "numero":
                    errores.append(f"{prefijo}: 'mayor_que' debe apuntar a un campo numérico definido antes.")
                else:
                    campo["mayor_que"] = mayor_que
        claves_vistas[clave] = tipo
        normalizados.append(campo)

    if errores:
        raise ErrorValidacion(errores)
    return normalizados


# --------------------------------------------------------------------------- formularios


def _es_numero(valor: Any) -> bool:
    return isinstance(valor, (int, float)) and not isinstance(valor, bool) and math.isfinite(valor)


def _fecha(valor: Any, nombre: str, errores: list[str]) -> datetime | None:
    if not isinstance(valor, str):
        errores.append(f"'{nombre}' debe ser una fecha y hora ISO 8601 (ej. 2026-11-20T09:05:00).")
        return None
    try:
        return datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError:
        errores.append(f"'{nombre}' no es una fecha válida: {valor!r}.")
        return None


def _comparable(a: datetime, b: datetime) -> tuple[datetime, datetime]:
    """Permite comparar fechas con y sin zona horaria sin lanzar TypeError."""
    if (a.tzinfo is None) != (b.tzinfo is None):
        return a.replace(tzinfo=None), b.replace(tzinfo=None)
    return a, b


def validar_formulario(
    payload: Any,
    campos: list[dict],
    *,
    ahora: datetime | None = None,
    video_max_seg: int = 30,
    prefijo_url: str | None = None,
) -> dict:
    """Valida el JSON generado por la app móvil contra los campos de la versión de plantilla.

    Devuelve un diccionario normalizado o lanza ErrorValidacion con TODOS los errores.
    """
    errores: list[str] = []
    if not isinstance(payload, dict):
        raise ErrorValidacion(["El cuerpo debe ser un objeto JSON."])

    desconocidas = sorted(set(payload) - CLAVES_PERMITIDAS)
    if desconocidas:
        errores.append(f"Campos no permitidos en el documento: {', '.join(desconocidas)}.")

    # Identificador generado en el celular
    id_doc = None
    try:
        id_doc = str(uuid.UUID(str(payload.get("_id", ""))))
    except ValueError:
        errores.append("'_id' debe ser un UUID generado por la aplicación.")

    inicio = _fecha(payload.get("inicio"), "inicio", errores)
    termino = _fecha(payload.get("termino"), "termino", errores)
    if inicio and termino:
        a, b = _comparable(inicio, termino)
        if b < a:
            errores.append("'termino' no puede ser anterior a 'inicio'.")
        elif b - a > timedelta(hours=24):
            errores.append("Una mantención no puede durar más de 24 horas.")
        if ahora is not None:
            ref, fin = _comparable(ahora, termino)
            if fin > ref + timedelta(days=1):
                errores.append("'termino' está en el futuro; revise la hora del dispositivo.")

    origen = payload.get("origen", "app_movil")
    if origen not in ORIGENES:
        errores.append(f"'origen' inválido. Use: {', '.join(ORIGENES)}.")

    plan_id = payload.get("plan_id")
    if plan_id is not None and (not isinstance(plan_id, int) or isinstance(plan_id, bool) or plan_id < 1):
        errores.append("'plan_id' debe ser un número entero positivo.")

    # Respuestas
    respuestas = payload.get("respuestas")
    limpias: dict[str, Any] = {}
    if not isinstance(respuestas, dict):
        errores.append("'respuestas' debe ser un objeto.")
        respuestas = {}
    por_clave = {c["clave"]: c for c in campos}
    ajenas = sorted(set(respuestas) - {c["clave"] for c in campos if c["tipo"] not in TIPOS_MEDIA})
    if ajenas:
        errores.append(f"Respuestas a campos que no existen en la plantilla: {', '.join(ajenas)}.")

    for campo in campos:
        clave, tipo, etiqueta = campo["clave"], campo["tipo"], campo["etiqueta"]
        if tipo in TIPOS_MEDIA:
            continue
        valor = respuestas.get(clave)
        vacio = valor is None or (isinstance(valor, str) and not valor.strip())
        if vacio:
            if campo.get("obligatorio"):
                errores.append(f"'{etiqueta}' es obligatorio.")
            continue
        if tipo == "si_no":
            if not isinstance(valor, bool):
                errores.append(f"'{etiqueta}' debe ser Sí o No.")
                continue
        elif tipo == "numero":
            if not _es_numero(valor):
                errores.append(f"'{etiqueta}' debe ser un número.")
                continue
            if "min" in campo and valor < campo["min"]:
                errores.append(f"'{etiqueta}' no puede ser menor que {campo['min']}.")
            if "max" in campo and valor > campo["max"]:
                errores.append(f"'{etiqueta}' no puede ser mayor que {campo['max']}.")
        elif tipo == "texto":
            if not isinstance(valor, str):
                errores.append(f"'{etiqueta}' debe ser texto.")
                continue
            valor = valor.replace("\x00", "").strip()
            if len(valor) > MAX_TEXTO:
                errores.append(f"'{etiqueta}' admite como máximo {MAX_TEXTO} caracteres.")
                continue
        elif tipo == "lista":
            if valor not in campo.get("opciones", []):
                errores.append(f"'{etiqueta}': la opción '{valor}' no está permitida.")
                continue
        limpias[clave] = valor

    # Regla entre campos: p. ej. horómetro final mayor que el inicial
    for campo in campos:
        otro_clave = campo.get("mayor_que")
        if not otro_clave:
            continue
        actual, previo = limpias.get(campo["clave"]), limpias.get(otro_clave)
        if _es_numero(actual) and _es_numero(previo) and actual <= previo:
            errores.append(
                f"'{campo['etiqueta']}' debe ser mayor que '{por_clave[otro_clave]['etiqueta']}'."
            )

    # Evidencias (solo URL de Cloudinary, nunca el archivo)
    evidencias = payload.get("evidencias", [])
    limpias_ev: list[dict] = []
    if not isinstance(evidencias, list):
        errores.append("'evidencias' debe ser una lista.")
        evidencias = []
    if len(evidencias) > MAX_EVIDENCIAS:
        errores.append(f"Se admiten como máximo {MAX_EVIDENCIAS} evidencias por formulario.")
        evidencias = evidencias[:MAX_EVIDENCIAS]
    campos_con_evidencia: set[str] = set()
    for pos, ev in enumerate(evidencias, start=1):
        if not isinstance(ev, dict):
            errores.append(f"Evidencia {pos}: formato inválido.")
            continue
        extra = sorted(set(ev) - CLAVES_EVIDENCIA)
        if extra:
            errores.append(f"Evidencia {pos}: campos no permitidos ({', '.join(extra)}).")
            continue
        campo_ev = por_clave.get(ev.get("campo"))
        if not campo_ev or campo_ev["tipo"] not in TIPOS_MEDIA:
            errores.append(f"Evidencia {pos}: el campo '{ev.get('campo')}' no admite fotos ni videos.")
            continue
        if ev.get("tipo") != campo_ev["tipo"]:
            errores.append(f"Evidencia {pos}: debe ser de tipo {campo_ev['tipo']}.")
            continue
        url = ev.get("url")
        if not isinstance(url, str) or not url.startswith("https://") or len(url) > 255:
            errores.append(f"Evidencia {pos}: URL inválida.")
            continue
        if prefijo_url and not url.startswith(prefijo_url):
            errores.append(f"Evidencia {pos}: la URL no pertenece al almacenamiento autorizado.")
            continue
        duracion = ev.get("duracion_seg")
        if ev["tipo"] == "video" and duracion is not None:
            if not _es_numero(duracion) or duracion < 0:
                errores.append(f"Evidencia {pos}: duración inválida.")
                continue
            if duracion > video_max_seg:
                errores.append(f"Evidencia {pos}: el video dura más de {video_max_seg} segundos.")
                continue
        peso = ev.get("peso_kb", 0)
        if not isinstance(peso, int) or isinstance(peso, bool) or peso < 0:
            errores.append(f"Evidencia {pos}: peso inválido.")
            continue
        public_id = ev.get("public_id", "")
        if not isinstance(public_id, str) or len(public_id) > 255:
            errores.append(f"Evidencia {pos}: identificador de archivo inválido.")
            continue
        campos_con_evidencia.add(ev["campo"])
        limpias_ev.append(
            {
                "campo": ev["campo"],
                "tipo": ev["tipo"],
                "url": url,
                "public_id": public_id,
                "peso_kb": peso,
                "duracion_seg": duracion,
            }
        )

    for campo in campos:
        if campo["tipo"] in TIPOS_MEDIA and campo.get("obligatorio") and campo["clave"] not in campos_con_evidencia:
            errores.append(f"'{campo['etiqueta']}' es obligatorio: falta la {campo['tipo']}.")

    if errores:
        raise ErrorValidacion(errores)

    return {
        "id": id_doc,
        "inicio": inicio,
        "termino": termino,
        "respuestas": limpias,
        "evidencias": limpias_ev,
        "origen": origen,
        "plan_id": plan_id,
    }
