"""Acceso a la base no relacional (MongoDB Atlas).

Colecciones del informe (sección 7.2):
  - formularios_mantencion ... respuestas de cada formulario junto con sus evidencias (URL de Cloudinary)
  - versiones_plantilla ...... campos de cada versión de una plantilla

Se define una interfaz pequeña con dos implementaciones:
  - RepoMongo ..... pymongo contra Atlas (producción y desarrollo con Atlas)
  - RepoMemoria ... en memoria (pruebas automáticas y desarrollo sin conexión a Atlas)

Este módulo no importa Django al cargarse; `obtener_repo()` lee la configuración recién cuando se usa.
"""

from __future__ import annotations

import copy
import threading
from datetime import datetime, timezone
from typing import Any


class ConflictoDeVersion(Exception):
    """No se pudo asignar un número de versión tras varios intentos."""


class RepoMemoria:
    """Implementación en memoria. Imita la semántica de MongoDB (_id único)."""

    def __init__(self) -> None:
        self._formularios: dict[str, dict] = {}
        self._versiones: list[dict] = []
        self._lock = threading.Lock()

    # formularios
    def insertar_formulario(self, doc: dict) -> bool:
        """Inserta el documento. Devuelve False si el _id ya existía (no lo sobrescribe)."""
        with self._lock:
            if doc["_id"] in self._formularios:
                return False
            self._formularios[doc["_id"]] = copy.deepcopy(doc)
            return True

    def obtener_formulario(self, id_doc: str) -> dict | None:
        doc = self._formularios.get(id_doc)
        return copy.deepcopy(doc) if doc else None

    def eliminar_formulario(self, id_doc: str) -> None:
        self._formularios.pop(id_doc, None)

    def ids_formularios(self) -> set[str]:
        return set(self._formularios)

    # versiones de plantilla
    def crear_version(self, plantilla_id: int, nombre: str, campos: list[dict]) -> dict:
        with self._lock:
            numero = max((v["numero"] for v in self._versiones if v["plantilla_id"] == plantilla_id), default=0) + 1
            doc = {
                "_id": f"{plantilla_id}-{numero}",
                "plantilla_id": plantilla_id,
                "nombre": nombre,
                "numero": numero,
                "fecha": datetime.now(timezone.utc),
                "campos": copy.deepcopy(campos),
            }
            self._versiones.append(doc)
            return copy.deepcopy(doc)

    def obtener_version(self, plantilla_id: int, numero: int | None = None) -> dict | None:
        candidatas = [v for v in self._versiones if v["plantilla_id"] == plantilla_id]
        if numero is not None:
            candidatas = [v for v in candidatas if v["numero"] == numero]
        if not candidatas:
            return None
        return copy.deepcopy(max(candidatas, key=lambda v: v["numero"]))

    def listar_versiones(self, plantilla_id: int) -> list[dict]:
        return [
            copy.deepcopy(v)
            for v in sorted(self._versiones, key=lambda v: v["numero"], reverse=True)
            if v["plantilla_id"] == plantilla_id
        ]

    def ping(self) -> bool:
        return True


class RepoMongo:
    """Implementación con pymongo. El cliente se crea una vez por instancia de la función serverless."""

    def __init__(self, uri: str, nombre_bd: str) -> None:
        from pymongo import MongoClient  # import diferido: no se necesita en pruebas

        self._cliente = MongoClient(uri, serverSelectionTimeoutMS=5000, appname="covepa-mantenciones")
        self._bd = self._cliente[nombre_bd]
        self._formularios = self._bd["formularios_mantencion"]
        self._versiones = self._bd["versiones_plantilla"]
        self._indices_listos = False

    def _asegurar_indices(self) -> None:
        if self._indices_listos:
            return
        self._formularios.create_index([("equipo.codigo", 1), ("inicio", -1)])
        self._formularios.create_index([("tecnico_id", 1), ("inicio", -1)])
        self._versiones.create_index([("plantilla_id", 1), ("numero", -1)], unique=True)
        self._indices_listos = True

    def insertar_formulario(self, doc: dict) -> bool:
        from pymongo.errors import DuplicateKeyError

        self._asegurar_indices()
        try:
            self._formularios.insert_one(doc)
            return True
        except DuplicateKeyError:
            return False

    def obtener_formulario(self, id_doc: str) -> dict | None:
        return self._formularios.find_one({"_id": id_doc})

    def eliminar_formulario(self, id_doc: str) -> None:
        self._formularios.delete_one({"_id": id_doc})

    def ids_formularios(self) -> set[str]:
        return {d["_id"] for d in self._formularios.find({}, {"_id": 1})}

    def crear_version(self, plantilla_id: int, nombre: str, campos: list[dict]) -> dict:
        from pymongo.errors import DuplicateKeyError

        self._asegurar_indices()
        for _ in range(5):  # el índice único evita que dos publicaciones simultáneas repitan el número
            ultima = self._versiones.find_one({"plantilla_id": plantilla_id}, sort=[("numero", -1)])
            numero = (ultima["numero"] if ultima else 0) + 1
            doc = {
                "plantilla_id": plantilla_id,
                "nombre": nombre,
                "numero": numero,
                "fecha": datetime.now(timezone.utc),
                "campos": campos,
            }
            try:
                resultado = self._versiones.insert_one(doc)
            except DuplicateKeyError:
                continue
            doc["_id"] = str(resultado.inserted_id)
            return doc
        raise ConflictoDeVersion("No se pudo asignar el número de versión de la plantilla.")

    def obtener_version(self, plantilla_id: int, numero: int | None = None) -> dict | None:
        filtro: dict[str, Any] = {"plantilla_id": plantilla_id}
        if numero is not None:
            filtro["numero"] = numero
        doc = self._versiones.find_one(filtro, sort=[("numero", -1)])
        if doc:
            doc["_id"] = str(doc["_id"])
        return doc

    def listar_versiones(self, plantilla_id: int) -> list[dict]:
        docs = list(self._versiones.find({"plantilla_id": plantilla_id}).sort("numero", -1))
        for d in docs:
            d["_id"] = str(d["_id"])
        return docs

    def ping(self) -> bool:
        self._cliente.admin.command("ping")
        return True


_repo: RepoMemoria | RepoMongo | None = None


def obtener_repo() -> RepoMemoria | RepoMongo:
    """Devuelve el repositorio configurado (singleton por proceso)."""
    global _repo
    if _repo is None:
        from django.conf import settings
        from django.core.exceptions import ImproperlyConfigured

        if settings.MONGODB_URI:
            _repo = RepoMongo(settings.MONGODB_URI, settings.MONGODB_DB_NAME)
        elif settings.DEBUG or settings.TESTING:
            _repo = RepoMemoria()
        else:
            raise ImproperlyConfigured("Falta MONGODB_URI (cadena de conexión de MongoDB Atlas).")
    return _repo


def fijar_repo(repo: RepoMemoria | RepoMongo | None) -> None:
    """Permite a las pruebas inyectar un repositorio (o None para reiniciar)."""
    global _repo
    _repo = repo
