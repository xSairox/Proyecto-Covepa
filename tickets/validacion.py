"""Validación de materiales y documentos de respaldo de un ticket (sin dependencias de Django)."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from core.validators import ErrorValidacion

TIPOS_DOCUMENTO = ("factura", "guia_despacho", "otro")
MAX_FILAS = 30


def normalizar_materiales(bruto: Any) -> list[dict]:
    errores: list[str] = []
    if bruto in (None, ""):
        return []
    if not isinstance(bruto, list):
        raise ErrorValidacion(["Los materiales deben ser una lista."])
    if len(bruto) > MAX_FILAS:
        raise ErrorValidacion([f"Se admiten como máximo {MAX_FILAS} materiales."])
    limpios = []
    for pos, fila in enumerate(bruto, start=1):
        if not isinstance(fila, dict):
            errores.append(f"Material {pos}: formato inválido.")
            continue
        descripcion = str(fila.get("descripcion", "")).strip()
        unidad = str(fila.get("unidad", "unidad")).strip() or "unidad"
        try:
            cantidad = Decimal(str(fila.get("cantidad", "")).replace(",", "."))
        except InvalidOperation:
            errores.append(f"Material {pos}: la cantidad debe ser un número.")
            continue
        if not descripcion or len(descripcion) > 120:
            errores.append(f"Material {pos}: la descripción es obligatoria (máx. 120 caracteres).")
        if not cantidad.is_finite() or cantidad <= 0 or cantidad > Decimal("1000000"):
            errores.append(f"Material {pos}: la cantidad debe ser mayor que 0.")
            continue
        if len(unidad) > 20:
            errores.append(f"Material {pos}: la unidad admite hasta 20 caracteres.")
        limpios.append({"descripcion": descripcion, "cantidad": cantidad.quantize(Decimal("0.01")), "unidad": unidad})
    if errores:
        raise ErrorValidacion(errores)
    return limpios


def normalizar_documentos(bruto: Any, prefijo_url: str | None = None) -> list[dict]:
    errores: list[str] = []
    if bruto in (None, ""):
        return []
    if not isinstance(bruto, list):
        raise ErrorValidacion(["Los documentos deben ser una lista."])
    if len(bruto) > MAX_FILAS:
        raise ErrorValidacion([f"Se admiten como máximo {MAX_FILAS} documentos."])
    limpios = []
    for pos, fila in enumerate(bruto, start=1):
        if not isinstance(fila, dict):
            errores.append(f"Documento {pos}: formato inválido.")
            continue
        tipo = fila.get("tipo", "factura")
        if tipo not in TIPOS_DOCUMENTO:
            errores.append(f"Documento {pos}: tipo no permitido.")
            continue
        numero = str(fila.get("numero", "")).strip()
        proveedor = str(fila.get("proveedor", "")).strip()
        if len(numero) > 30 or len(proveedor) > 100:
            errores.append(f"Documento {pos}: número o proveedor demasiado largo.")
            continue
        monto = fila.get("monto")
        if monto in (None, ""):
            monto = None
        else:
            try:
                monto = int(str(monto).replace(".", "").replace(",", ""))
            except ValueError:
                errores.append(f"Documento {pos}: el monto debe ser un número entero.")
                continue
            if monto < 0 or monto > 2_000_000_000:
                errores.append(f"Documento {pos}: monto fuera de rango.")
                continue
        public_id = str(fila.get("public_id", "")).strip()
        url = str(fila.get("url", "")).strip()
        if not public_id or not url.startswith("https://") or len(url) > 255:
            errores.append(f"Documento {pos}: falta la foto del documento.")
            continue
        if prefijo_url and not url.startswith(prefijo_url):
            errores.append(f"Documento {pos}: la foto no pertenece al almacenamiento autorizado.")
            continue
        limpios.append(
            {"tipo": tipo, "numero": numero, "proveedor": proveedor, "monto": monto, "public_id": public_id, "url": url}
        )
    if errores:
        raise ErrorValidacion(errores)
    return limpios
