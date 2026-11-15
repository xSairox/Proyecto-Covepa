/* Cierre de trabajo de un ticket (HU-07): materiales y fotos de facturas o guías.
   Las fotos suben directo a Cloudinary; el servidor solo recibe las URL. */
(function () {
  'use strict';
  const COVEPA = window.COVEPA;
  const { el } = COVEPA;
  const $ = (id) => document.getElementById(id);

  const form = $('form-realizar');
  const errores = $('errores-realizar');
  const boton = $('enviar-realizar');
  const contMateriales = $('materiales');
  const contDocumentos = $('documentos');
  const salidaMateriales = document.getElementById('id_materiales_json');
  const salidaDocumentos = document.getElementById('id_documentos_json');

  const materiales = [];
  const documentos = [];
  let subidasEnCurso = 0;

  const volcar = () => {
    salidaMateriales.value = JSON.stringify(materiales.filter((m) => m.descripcion.trim() || m.cantidad !== ''));
    salidaDocumentos.value = JSON.stringify(documentos.filter((d) => d.url).map(({ tipo, numero, proveedor, monto, public_id, url }) => ({ tipo, numero, proveedor, monto, public_id, url })));
  };

  function entrada(fila, clave, etiqueta, atributos) {
    const e = el('input', { class: 'campo', value: fila[clave] ?? '', ...atributos });
    e.addEventListener('input', () => { fila[clave] = e.value; volcar(); });
    return el('div', {}, el('label', { class: 'etiqueta', texto: etiqueta }), e);
  }

  function pintarMateriales() {
    contMateriales.replaceChildren(...materiales.map((m, i) => el('div', { class: 'fila-dinamica' },
      entrada(m, 'descripcion', 'Material', { type: 'text', maxlength: 120 }),
      entrada(m, 'cantidad', 'Cantidad', { type: 'number', step: '0.01', min: '0', inputmode: 'decimal' }),
      entrada(m, 'unidad', 'Unidad', { type: 'text', maxlength: 20 }),
      el('button', { class: 'boton boton--peligro boton--chico', type: 'button', texto: 'Quitar', onclick: () => { materiales.splice(i, 1); pintarMateriales(); volcar(); } }))));
  }

  function pintarDocumentos() {
    contDocumentos.replaceChildren(...documentos.map((d, i) => {
      const estado = el('p', { class: 'ayuda', role: 'status', texto: d.url ? 'Foto subida.' : 'Falta la foto del documento.' });
      const archivo = el('input', { class: 'campo', type: 'file', accept: 'image/*', capture: 'environment', 'aria-label': `Foto del documento ${i + 1}` });
      archivo.addEventListener('change', async () => {
        const f = archivo.files[0];
        if (!f) return;
        if (!navigator.onLine) { estado.textContent = 'Necesitas conexión para subir la foto.'; archivo.value = ''; return; }
        estado.textContent = 'Subiendo…';
        subidasEnCurso += 1;
        boton.disabled = true;
        try {
          const r = await COVEPA.subirACloudinary(f, 'foto');
          d.url = r.url; d.public_id = r.public_id;
          estado.textContent = 'Foto subida.';
        } catch (e) {
          d.url = ''; d.public_id = '';
          estado.textContent = e.sesion ? 'Tu sesión venció. Inicia sesión de nuevo.' : (e.message || 'No se pudo subir la foto.');
        } finally {
          subidasEnCurso -= 1;
          boton.disabled = subidasEnCurso > 0;
          volcar();
        }
      });
      const tipo = el('select', { class: 'campo' }, [['factura', 'Factura'], ['guia_despacho', 'Guía de despacho'], ['otro', 'Otro']].map(([v, t]) => el('option', { value: v, texto: t, selected: d.tipo === v })));
      tipo.addEventListener('change', () => { d.tipo = tipo.value; volcar(); });
      return el('div', { class: 'fila-dinamica' },
        el('div', {}, el('label', { class: 'etiqueta', texto: 'Tipo' }), tipo),
        entrada(d, 'numero', 'N.º de documento', { type: 'text', maxlength: 30 }),
        entrada(d, 'proveedor', 'Proveedor', { type: 'text', maxlength: 100 }),
        entrada(d, 'monto', 'Monto (CLP)', { type: 'text', inputmode: 'numeric', maxlength: 14 }),
        el('div', {}, el('label', { class: 'etiqueta', texto: 'Foto' }), archivo, estado),
        el('button', { class: 'boton boton--peligro boton--chico', type: 'button', texto: 'Quitar', onclick: () => { documentos.splice(i, 1); pintarDocumentos(); volcar(); } }));
    }));
  }

  $('agregar-material').addEventListener('click', () => {
    materiales.push({ descripcion: '', cantidad: '', unidad: 'unidad' });
    pintarMateriales();
    contMateriales.querySelector('.fila-dinamica:last-child input').focus();
  });
  $('agregar-documento').addEventListener('click', () => {
    documentos.push({ tipo: 'factura', numero: '', proveedor: '', monto: '', public_id: '', url: '' });
    pintarDocumentos();
  });

  form.addEventListener('submit', (ev) => {
    const faltan = [];
    materiales.forEach((m, i) => {
      if (!m.descripcion.trim() && m.cantidad === '') return;
      if (!m.descripcion.trim()) faltan.push(`Material ${i + 1}: escribe qué material es.`);
      if (!(Number(String(m.cantidad).replace(',', '.')) > 0)) faltan.push(`Material ${i + 1}: la cantidad debe ser mayor que 0.`);
    });
    documentos.forEach((d, i) => { if (!d.url) faltan.push(`Documento ${i + 1}: falta subir la foto.`); });
    if (subidasEnCurso) faltan.push('Espera a que termine de subir la foto.');
    volcar();
    errores.replaceChildren(...faltan.map((t) => el('li', { texto: t })));
    errores.hidden = faltan.length === 0;
    if (faltan.length) { ev.preventDefault(); errores.scrollIntoView({ block: 'center' }); }
  });

  pintarMateriales();
  pintarDocumentos();
  volcar();
})();
