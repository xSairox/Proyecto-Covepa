"""Pruebas de la validación del JSON de mantención (CP01-CP09 del informe, parte pura).
No requieren Django: python -m unittest discover -s core/tests  (o pytest core/tests)."""

import unittest
import uuid
from datetime import datetime, timezone

from core.validators import ErrorValidacion, validar_definicion_campos, validar_formulario

CAMPOS = validar_definicion_campos([
    {"clave": "horometro_inicial", "etiqueta": "Horómetro inicial", "tipo": "numero", "obligatorio": True, "min": 0, "unidad": "h"},
    {"clave": "horometro_final", "etiqueta": "Horómetro final", "tipo": "numero", "obligatorio": True, "mayor_que": "horometro_inicial", "unidad": "h"},
    {"clave": "nivel_aceite_ok", "etiqueta": "¿Nivel de aceite correcto?", "tipo": "si_no", "obligatorio": True},
    {"clave": "estado_general", "etiqueta": "Estado general", "tipo": "lista", "opciones": ["Bueno", "Regular", "Malo"]},
    {"clave": "observaciones", "etiqueta": "Observaciones", "tipo": "texto"},
    {"clave": "foto_equipo", "etiqueta": "Foto del equipo", "tipo": "foto", "obligatorio": True},
    {"clave": "video_arranque", "etiqueta": "Video de arranque", "tipo": "video"},
])
URL = "https://res.cloudinary.com/demo/image/upload/covepa/foto1.jpg"


def documento(**cambios):
    base = {
        "_id": str(uuid.uuid4()),
        "equipo": {"codigo": "GEN-FRE-01", "categoria": "Generador"},
        "sucursal": "Fresia",
        "plantilla": {"id": 1, "nombre": "Generador", "version": 1},
        "tecnico_id": 3,
        "inicio": "2026-11-20T09:00:00Z",
        "termino": "2026-11-20T09:20:00Z",
        "respuestas": {"horometro_inicial": 1200, "horometro_final": 1203.5, "nivel_aceite_ok": True},
        "evidencias": [{"campo": "foto_equipo", "tipo": "foto", "url": URL, "public_id": "covepa/foto1", "peso_kb": 340}],
        "origen": "app_movil_sin_conexion",
    }
    base.update(cambios)
    return base


def errores_de(doc, **kw):
    with_ahora = {"ahora": datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)}
    with_ahora.update(kw)
    try:
        validar_formulario(doc, CAMPOS, **with_ahora)
    except ErrorValidacion as e:
        return e.errores
    return []


class FormularioValido(unittest.TestCase):
    def test_documento_correcto_se_normaliza(self):
        r = validar_formulario(documento(), CAMPOS)
        self.assertEqual(r["respuestas"]["horometro_final"], 1203.5)
        self.assertEqual(len(r["evidencias"]), 1)
        self.assertEqual(r["origen"], "app_movil_sin_conexion")

    def test_cp07_horometro_final_menor_o_igual_se_rechaza(self):
        for final in (1100, 1200):
            doc = documento(respuestas={"horometro_inicial": 1200, "horometro_final": final, "nivel_aceite_ok": True})
            errores = errores_de(doc)
            self.assertTrue(any("debe ser mayor que" in e for e in errores), errores)

    def test_obligatorios_faltantes_se_informan_todos_juntos(self):
        errores = errores_de(documento(respuestas={}, evidencias=[]))
        self.assertGreaterEqual(len(errores), 4)  # 3 respuestas + foto

    def test_tipos_y_rangos(self):
        doc = documento(respuestas={"horometro_inicial": -5, "horometro_final": "abc", "nivel_aceite_ok": "si", "estado_general": "Excelente"})
        errores = " | ".join(errores_de(doc))
        self.assertIn("menor que 0", errores)
        self.assertIn("debe ser un número", errores)
        self.assertIn("Sí o No", errores)
        self.assertIn("no está permitida", errores)

    def test_booleano_no_es_numero(self):
        doc = documento(respuestas={"horometro_inicial": True, "horometro_final": 5, "nivel_aceite_ok": True})
        self.assertTrue(any("debe ser un número" in e for e in errores_de(doc)))

    def test_campos_desconocidos_en_respuestas_y_documento(self):
        doc = documento(respuestas={"horometro_inicial": 1, "horometro_final": 2, "nivel_aceite_ok": True, "hack": 1}, extra=1)
        errores = " | ".join(errores_de(doc))
        self.assertIn("que no existen en la plantilla", errores)
        self.assertIn("no permitidos en el documento", errores)

    def test_id_debe_ser_uuid(self):
        self.assertTrue(any("UUID" in e for e in errores_de(documento(_id="123"))))

    def test_fechas(self):
        self.assertTrue(any("anterior" in e for e in errores_de(documento(inicio="2026-11-20T10:00:00Z", termino="2026-11-20T09:00:00Z"))))
        self.assertTrue(any("24 horas" in e for e in errores_de(documento(inicio="2026-11-18T09:00:00Z", termino="2026-11-20T09:00:00Z"))))
        self.assertTrue(any("futuro" in e for e in errores_de(documento(termino="2027-01-01T00:00:00Z", inicio="2026-12-31T23:00:00Z"))))
        self.assertTrue(any("no es una fecha válida" in e for e in errores_de(documento(inicio="ayer"))))

    def test_texto_largo(self):
        doc = documento(respuestas={"horometro_inicial": 1, "horometro_final": 2, "nivel_aceite_ok": True, "observaciones": "x" * 1001})
        self.assertTrue(any("máximo" in e for e in errores_de(doc)))

    def test_plan_id(self):
        self.assertEqual(validar_formulario(documento(plan_id=4), CAMPOS)["plan_id"], 4)
        self.assertTrue(any("plan_id" in e for e in errores_de(documento(plan_id=0))))
        self.assertTrue(any("plan_id" in e for e in errores_de(documento(plan_id=True))))

    def test_cuerpo_no_objeto(self):
        with self.assertRaises(ErrorValidacion):
            validar_formulario([], CAMPOS)


class Evidencias(unittest.TestCase):
    def _con(self, *evidencias):
        return documento(evidencias=[{"campo": "foto_equipo", "tipo": "foto", "url": URL, "public_id": "a", "peso_kb": 1}, *evidencias])

    def test_cp09_video_de_mas_de_30_segundos_se_rechaza(self):
        video = {"campo": "video_arranque", "tipo": "video", "url": "https://res.cloudinary.com/demo/video/upload/v.mp4", "public_id": "v", "peso_kb": 900, "duracion_seg": 45}
        self.assertTrue(any("30 segundos" in e for e in errores_de(self._con(video))))
        video["duracion_seg"] = 30
        self.assertEqual(errores_de(self._con(video)), [])

    def test_url_debe_ser_https_y_del_almacenamiento_autorizado(self):
        malo = {"campo": "foto_equipo", "tipo": "foto", "url": "http://sitio.cl/a.jpg", "public_id": "a", "peso_kb": 1}
        self.assertTrue(any("URL inválida" in e for e in errores_de(documento(evidencias=[malo]))))
        ajeno = {"campo": "foto_equipo", "tipo": "foto", "url": "https://otro.com/a.jpg", "public_id": "a", "peso_kb": 1}
        errores = errores_de(documento(evidencias=[ajeno]), prefijo_url="https://res.cloudinary.com/demo/")
        self.assertTrue(any("autorizado" in e for e in errores))

    def test_el_tipo_debe_coincidir_con_el_campo(self):
        ev = {"campo": "foto_equipo", "tipo": "video", "url": URL, "public_id": "a", "peso_kb": 1}
        self.assertTrue(any("debe ser de tipo foto" in e for e in errores_de(documento(evidencias=[ev]))))

    def test_evidencia_en_campo_que_no_es_media(self):
        ev = {"campo": "observaciones", "tipo": "foto", "url": URL, "public_id": "a", "peso_kb": 1}
        self.assertTrue(any("no admite fotos" in e for e in errores_de(self._con(ev))))

    def test_no_se_aceptan_binarios_ni_claves_extra(self):
        ev = {"campo": "foto_equipo", "tipo": "foto", "url": URL, "public_id": "a", "peso_kb": 1, "base64": "AAAA"}
        self.assertTrue(any("no permitidos" in e for e in errores_de(documento(evidencias=[ev]))))

    def test_limite_de_evidencias(self):
        muchas = [{"campo": "foto_equipo", "tipo": "foto", "url": URL, "public_id": str(i), "peso_kb": 1} for i in range(31)]
        self.assertTrue(any("máximo 30" in e or "como máximo" in e for e in errores_de(documento(evidencias=muchas))))


class DefinicionDePlantilla(unittest.TestCase):
    def test_exige_al_menos_un_campo(self):
        with self.assertRaises(ErrorValidacion):
            validar_definicion_campos([])

    def test_clave_invalida_y_repetida(self):
        with self.assertRaises(ErrorValidacion) as c:
            validar_definicion_campos([
                {"clave": "Horómetro", "etiqueta": "x", "tipo": "numero"},
                {"clave": "a", "etiqueta": "A", "tipo": "texto"},
                {"clave": "a", "etiqueta": "B", "tipo": "texto"},
            ])
        self.assertEqual(len(c.exception.errores), 2)

    def test_lista_necesita_dos_opciones_distintas(self):
        for opciones in (["una"], ["a", "a"], [], None):
            with self.assertRaises(ErrorValidacion):
                validar_definicion_campos([{"clave": "l", "etiqueta": "L", "tipo": "lista", "opciones": opciones}])

    def test_mayor_que_debe_apuntar_a_un_numero_previo(self):
        with self.assertRaises(ErrorValidacion):
            validar_definicion_campos([{"clave": "b", "etiqueta": "B", "tipo": "numero", "mayor_que": "a"}])
        with self.assertRaises(ErrorValidacion):
            validar_definicion_campos([{"clave": "a", "etiqueta": "A", "tipo": "texto"}, {"clave": "b", "etiqueta": "B", "tipo": "numero", "mayor_que": "a"}])

    def test_minimo_no_supera_maximo(self):
        with self.assertRaises(ErrorValidacion):
            validar_definicion_campos([{"clave": "a", "etiqueta": "A", "tipo": "numero", "min": 10, "max": 1}])

    def test_tipo_no_permitido(self):
        with self.assertRaises(ErrorValidacion):
            validar_definicion_campos([{"clave": "a", "etiqueta": "A", "tipo": "firma"}])


if __name__ == "__main__":
    unittest.main()
