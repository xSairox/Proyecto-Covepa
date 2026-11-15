/* Constructor de plantillas (HU-03): la jefatura arma el formulario sin escribir JSON.
   Escribe el resultado en el campo oculto id_campos_json; el servidor lo vuelve a validar. */
(function () {
  'use strict';
  const COVEPA = window.COVEPA;
  const { el } = COVEPA;
  const $ = (id) => document.getElementById(id);

  const TIPOS = [
    ['si_no', 'Sí / No'], ['numero', 'Número'], ['texto', 'Texto'],
    ['lista', 'Lista de opciones'], ['foto', 'Foto'], ['video', 'Video (máx. 30 s)'],
  ];
  const contenedor = $('constructor');
  const salida = document.getElementById('id_campos_json');
  const errores = $('errores-constructor');
  let campos = JSON.parse($('campos-iniciales').textContent || '[]');
  if (!Array.isArray(campos)) campos = [];

  const claveDesde = (texto) => {
    const base = texto.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
    return /^[a-z]/.test(base) ? base.slice(0, 40) : (`c_${base}`).slice(0, 40);
  };

  function claveUnica(base, excepto) {
    let clave = base || 'campo';
    let n = 2;
    while (campos.some((c) => c !== excepto && c.clave === clave)) clave = `${base}_${n++}`.slice(0, 40);
    return clave;
  }

  function sincronizar() {
    const limpio = campos.map((c) => {
      const o = { clave: c.clave, etiqueta: c.etiqueta, tipo: c.tipo, obligatorio: !!c.obligatorio };
      if (c.tipo === 'lista') o.opciones = c.opciones || [];
      if (c.tipo === 'numero') {
        ['min', 'max'].forEach((k) => { if (c[k] !== undefined && c[k] !== null && c[k] !== '') o[k] = Number(c[k]); });
        if (c.unidad) o.unidad = c.unidad;
        if (c.mayor_que) o.mayor_que = c.mayor_que;
      }
      return o;
    });
    salida.value = JSON.stringify(limpio);
  }

  function mover(i, delta) {
    const j = i + delta;
    if (j < 0 || j >= campos.length) return;
    [campos[i], campos[j]] = [campos[j], campos[i]];
    pintar();
  }

  function filaCampo(c, i) {
    const n = i + 1;
    const etiqueta = el('input', { class: 'campo', type: 'text', maxlength: 120, value: c.etiqueta || '', 'aria-label': `Pregunta del campo ${n}` });
    etiqueta.addEventListener('input', () => {
      const anterior = c.clave;
      const autoClave = !c.clave || c.clave === claveDesde(c.etiquetaPrevia || '') || c.claveAuto;
      c.etiqueta = etiqueta.value;
      c.etiquetaPrevia = etiqueta.value;
      if (autoClave) {
        c.claveAuto = true;
        c.clave = claveUnica(claveDesde(etiqueta.value), c);
        if (anterior !== c.clave) campos.forEach((o) => { if (o.mayor_que === anterior) o.mayor_que = c.clave; });
      }
      sincronizar();
    });

    const tipo = el('select', { class: 'campo', 'aria-label': `Tipo del campo ${n}` }, TIPOS.map(([v, t]) => el('option', { value: v, texto: t, selected: c.tipo === v })));
    tipo.addEventListener('change', () => { c.tipo = tipo.value; pintar(); });

    const obligatorio = el('input', { type: 'checkbox', id: `obl_${i}`, checked: !!c.obligatorio });
    obligatorio.addEventListener('change', () => { c.obligatorio = obligatorio.checked; sincronizar(); });

    const extras = el('div', { class: 'fila-campos', style: 'grid-column:1/-1' });
    if (c.tipo === 'lista') {
      const opciones = el('textarea', { class: 'campo', rows: 3, 'aria-label': `Opciones del campo ${n}`, placeholder: 'Una opción por línea' });
      opciones.value = (c.opciones || []).join('\n');
      opciones.addEventListener('input', () => { c.opciones = opciones.value.split('\n').map((s) => s.trim()).filter(Boolean); sincronizar(); });
      extras.append(el('div', {}, el('label', { class: 'etiqueta', texto: 'Opciones (una por línea)' }), opciones));
    }
    if (c.tipo === 'numero') {
      const num = (clave, texto) => {
        const e = el('input', { class: 'campo', type: 'number', step: 'any', inputmode: 'decimal', value: c[clave] ?? '' });
        e.addEventListener('input', () => { c[clave] = e.value === '' ? undefined : Number(e.value); sincronizar(); });
        return el('div', {}, el('label', { class: 'etiqueta', texto }), e);
      };
      const unidad = el('input', { class: 'campo', type: 'text', maxlength: 20, value: c.unidad || '', placeholder: 'h, °C, V…' });
      unidad.addEventListener('input', () => { c.unidad = unidad.value.trim(); sincronizar(); });
      const previos = campos.slice(0, i).filter((o) => o.tipo === 'numero');
      const mayor = el('select', { class: 'campo' }, el('option', { value: '', texto: 'Sin comparación' }),
        previos.map((o) => el('option', { value: o.clave, texto: `Mayor que «${o.etiqueta || o.clave}»`, selected: c.mayor_que === o.clave })));
      mayor.addEventListener('change', () => { c.mayor_que = mayor.value || undefined; sincronizar(); });
      extras.append(num('min', 'Mínimo'), num('max', 'Máximo'), el('div', {}, el('label', { class: 'etiqueta', texto: 'Unidad' }), unidad),
        el('div', {}, el('label', { class: 'etiqueta', texto: 'Debe cumplir' }), mayor));
    }

    return el('div', { class: 'fila' },
      el('div', {}, el('label', { class: 'etiqueta', texto: `Pregunta ${n}` }), etiqueta),
      el('div', {}, el('label', { class: 'etiqueta', texto: 'Tipo de respuesta' }), tipo),
      el('div', { style: 'display:flex;align-items:center;gap:8px;align-self:end;min-height:48px' }, obligatorio, el('label', { for: `obl_${i}`, texto: 'Obligatorio' })),
      extras,
      el('div', { class: 'acciones', style: 'grid-column:1/-1;margin:0' },
        el('button', { class: 'boton boton--secundario boton--chico', type: 'button', texto: 'Subir', disabled: i === 0, onclick: () => mover(i, -1) }),
        el('button', { class: 'boton boton--secundario boton--chico', type: 'button', texto: 'Bajar', disabled: i === campos.length - 1, onclick: () => mover(i, 1) }),
        el('button', { class: 'boton boton--peligro boton--chico', type: 'button', texto: 'Quitar campo', onclick: () => { campos.splice(i, 1); pintar(); } }),
        el('span', { class: 'ayuda', texto: `Identificador interno: ${c.clave || '—'}` })));
  }

  function pintar() {
    contenedor.replaceChildren(...campos.map(filaCampo));
    if (!campos.length) contenedor.append(el('p', { class: 'ayuda', texto: 'Aún no hay campos. Agrega el primero.' }));
    sincronizar();
  }

  $('agregar-campo').addEventListener('click', () => {
    campos.push({ clave: claveUnica('campo'), etiqueta: '', tipo: 'si_no', obligatorio: false, claveAuto: true });
    pintar();
    const filas = contenedor.querySelectorAll('.fila');
    const ultima = filas[filas.length - 1];
    if (ultima) ultima.querySelector('input').focus();
  });

  $('form-plantilla').addEventListener('submit', (ev) => {
    sincronizar();
    const faltan = [];
    campos.forEach((c, i) => {
      if (!(c.etiqueta || '').trim()) faltan.push(`Pregunta ${i + 1}: escribe la pregunta.`);
      if (c.tipo === 'lista' && (c.opciones || []).length < 2) faltan.push(`Pregunta ${i + 1}: la lista necesita al menos 2 opciones.`);
    });
    if (!campos.length) faltan.push('Agrega al menos un campo.');
    errores.replaceChildren(...faltan.map((t) => el('li', { texto: t })));
    errores.hidden = faltan.length === 0;
    if (faltan.length) { ev.preventDefault(); errores.scrollIntoView({ block: 'center' }); }
  });

  // Los campos que ya existen conservan su identificador: no se regenera al editar la pregunta
  campos.forEach((c) => { c.claveAuto = false; c.etiquetaPrevia = c.etiqueta; });
  pintar();
})();
