/* Formulario de mantención dinámico (HU-04). Lee la plantilla guardada en el dispositivo,
   funciona sin conexión y deja el resultado en la cola de envío. */
(function () {
  'use strict';
  const COVEPA = window.COVEPA;
  const { el } = COVEPA;
  const $ = (id) => document.getElementById(id);

  const form = $('form-mantencion');
  const selEquipo = $('sel-equipo');
  const selPlantilla = $('sel-plantilla');
  const contenedor = $('campos-dinamicos');
  const erroresForm = $('errores-form');
  const params = new URLSearchParams(location.search);

  let paquete = null;
  let sesionForm = null; // {equipo, plantilla, inicio, lectores, archivos}

  // ------------------------------------------------------------ medios
  async function comprimirImagen(archivo, ladoMax = 1600, calidad = 0.82) {
    let origen;
    try {
      origen = await createImageBitmap(archivo, { imageOrientation: 'from-image' });
    } catch (e) {
      return archivo; // formato que el navegador no decodifica (p. ej. HEIC): el servidor lo acepta tal cual
    }
    const escala = Math.min(1, ladoMax / Math.max(origen.width, origen.height));
    const lienzo = document.createElement('canvas');
    lienzo.width = Math.round(origen.width * escala);
    lienzo.height = Math.round(origen.height * escala);
    lienzo.getContext('2d').drawImage(origen, 0, 0, lienzo.width, lienzo.height);
    const blob = await new Promise((res) => lienzo.toBlob(res, 'image/jpeg', calidad));
    return blob && blob.size < archivo.size ? blob : archivo;
  }

  function duracionVideo(archivo) {
    return new Promise((resolver) => {
      const v = document.createElement('video');
      v.preload = 'metadata';
      const url = URL.createObjectURL(archivo);
      v.onloadedmetadata = () => { URL.revokeObjectURL(url); resolver(v.duration); };
      v.onerror = () => { URL.revokeObjectURL(url); resolver(null); };
      v.src = url;
    });
  }

  // ------------------------------------------------------------ constructores de campos
  function crearCampo(campo, estado) {
    const id = `c_${campo.clave}`;
    const etiqueta = campo.etiqueta + (campo.unidad ? ` (${campo.unidad})` : '') + (campo.obligatorio ? ' *' : '');
    const caja = el('div', { class: 'campo-mantencion' });
    const aviso = el('p', { class: 'error-campo', role: 'alert', hidden: true });

    if (campo.tipo === 'si_no') {
      caja.append(el('span', { class: 'etiqueta', id: `${id}_et`, texto: etiqueta }),
        el('div', { class: 'si-no', role: 'radiogroup', 'aria-labelledby': `${id}_et` },
          el('input', { type: 'radio', name: id, id: `${id}_si`, value: 'true' }), el('label', { for: `${id}_si`, texto: 'Sí' }),
          el('input', { type: 'radio', name: id, id: `${id}_no`, value: 'false' }), el('label', { for: `${id}_no`, texto: 'No' })));
      estado.lectores[campo.clave] = () => { const s = caja.querySelector(`input[name="${id}"]:checked`); return s ? s.value === 'true' : null; };
    } else if (campo.tipo === 'numero') {
      const entrada = el('input', { class: 'campo', type: 'number', step: 'any', inputmode: 'decimal', id, min: campo.min, max: campo.max });
      caja.append(el('label', { class: 'etiqueta', for: id, texto: etiqueta }), entrada);
      estado.lectores[campo.clave] = () => (entrada.value === '' ? null : Number(entrada.value));
    } else if (campo.tipo === 'texto') {
      const entrada = el('textarea', { class: 'campo', id, maxlength: 1000, rows: 3 });
      caja.append(el('label', { class: 'etiqueta', for: id, texto: etiqueta }), entrada);
      estado.lectores[campo.clave] = () => (entrada.value.trim() === '' ? null : entrada.value.trim());
    } else if (campo.tipo === 'lista') {
      const entrada = el('select', { class: 'campo', id }, el('option', { value: '', texto: 'Elige una opción' }), campo.opciones.map((o) => el('option', { value: o, texto: o })));
      caja.append(el('label', { class: 'etiqueta', for: id, texto: etiqueta }), entrada);
      estado.lectores[campo.clave] = () => (entrada.value === '' ? null : entrada.value);
    } else {
      const esVideo = campo.tipo === 'video';
      const previa = el('div', { class: 'vista-previa' });
      const entrada = el('input', { class: 'campo', type: 'file', id, accept: esVideo ? 'video/*' : 'image/*', capture: 'environment' });
      caja.append(el('label', { class: 'etiqueta', for: id, texto: etiqueta }), entrada, previa);
      entrada.addEventListener('change', async () => {
        const archivo = entrada.files[0];
        aviso.hidden = true;
        delete estado.archivos[campo.clave];
        previa.replaceChildren();
        if (!archivo) return;
        const limites = paquete.limites;
        if (esVideo) {
          if (archivo.size > limites.video_max_mb * 1048576) return rechazar(`El video pesa más de ${limites.video_max_mb} MB.`);
          const duracion = await duracionVideo(archivo);
          if (duracion !== null && duracion > limites.video_max_seg) return rechazar(`El video dura ${Math.round(duracion)} segundos. El máximo es ${limites.video_max_seg}.`);
          estado.archivos[campo.clave] = { campo: campo.clave, tipo: 'video', blob: archivo, nombre: archivo.name };
          previa.append(el('video', { src: URL.createObjectURL(archivo), controls: true, muted: true, preload: 'metadata' }));
        } else {
          const blob = await comprimirImagen(archivo);
          if (blob.size > limites.foto_max_mb * 1048576) return rechazar(`La foto pesa más de ${limites.foto_max_mb} MB.`);
          estado.archivos[campo.clave] = { campo: campo.clave, tipo: 'foto', blob, nombre: archivo.name };
          previa.append(el('img', { src: URL.createObjectURL(blob), alt: `Vista previa de ${campo.etiqueta}` }));
        }
      });
      function rechazar(texto) {
        entrada.value = '';
        aviso.textContent = texto;
        aviso.hidden = false;
      }
      estado.lectores[campo.clave] = () => null;
    }
    caja.append(aviso);
    caja.dataset.clave = campo.clave;
    return caja;
  }

  // ------------------------------------------------------------ armado y validación
  function armarFormulario() {
    contenedor.replaceChildren();
    erroresForm.hidden = true;
    sesionForm = null;
    const equipo = paquete.equipos.find((e) => String(e.id) === selEquipo.value);
    const plantilla = paquete.plantillas[selPlantilla.value];
    $('boton-guardar').hidden = !equipo || !plantilla;
    if (!equipo || !plantilla) { $('info-automatica').textContent = ''; return; }
    sesionForm = { equipo, plantilla, inicio: new Date(), lectores: {}, archivos: {} };
    plantilla.campos.forEach((c) => contenedor.append(crearCampo(c, sesionForm)));
    $('info-automatica').textContent = `La fecha, la hora y tu nombre (${paquete.usuario.nombre}) se registran solos.`;
  }

  function validar() {
    const errores = [];
    const { plantilla, lectores, archivos } = sesionForm;
    const valores = {};
    plantilla.campos.forEach((c) => {
      if (c.tipo === 'foto' || c.tipo === 'video') {
        if (c.obligatorio && !archivos[c.clave]) errores.push(`«${c.etiqueta}» es obligatorio: falta la ${c.tipo}.`);
        return;
      }
      const v = lectores[c.clave]();
      if (v === null) { if (c.obligatorio) errores.push(`«${c.etiqueta}» es obligatorio.`); return; }
      if (c.tipo === 'numero') {
        if (Number.isNaN(v)) { errores.push(`«${c.etiqueta}» debe ser un número.`); return; }
        if (c.min !== undefined && v < c.min) errores.push(`«${c.etiqueta}» no puede ser menor que ${c.min}.`);
        if (c.max !== undefined && v > c.max) errores.push(`«${c.etiqueta}» no puede ser mayor que ${c.max}.`);
      }
      valores[c.clave] = v;
    });
    plantilla.campos.forEach((c) => {
      if (c.mayor_que && typeof valores[c.clave] === 'number' && typeof valores[c.mayor_que] === 'number' && valores[c.clave] <= valores[c.mayor_que]) {
        const otro = plantilla.campos.find((x) => x.clave === c.mayor_que);
        errores.push(`«${c.etiqueta}» debe ser mayor que «${otro.etiqueta}».`);
      }
    });
    return { errores, valores };
  }

  async function guardar(ev) {
    ev.preventDefault();
    if (!sesionForm) return mostrarErrores(['Elige el equipo y el formulario.']);
    const { errores, valores } = validar();
    if (errores.length) return mostrarErrores(errores);

    const boton = $('boton-guardar');
    boton.disabled = true;
    const { equipo, plantilla, inicio, archivos } = sesionForm;
    const documento = {
      _id: COVEPA.uuid(),
      equipo: { codigo: equipo.codigo, categoria: equipo.categoria },
      sucursal: equipo.sucursal,
      plantilla: { id: plantilla.id, nombre: plantilla.nombre, version: plantilla.version },
      tecnico_id: COVEPA.cfg.usuarioId,
      inicio: inicio.toISOString(),
      termino: new Date().toISOString(),
      respuestas: valores,
      origen: navigator.onLine ? 'app_movil' : 'app_movil_sin_conexion',
    };
    // El plan solo se envía si corresponde al equipo elegido: si la persona cambió de equipo,
    // el servidor rechazaría el formulario por "plan de otro equipo".
    const plan = planDeLaUrl();
    if (plan && plan.equipo_id === equipo.id) documento.plan_id = plan.plan_id;

    try {
      await COVEPA.sync.encolar({ id: documento._id, doc: documento, archivos: Object.values(archivos) });
    } catch (e) {
      boton.disabled = false;
      return mostrarErrores(['No se pudo guardar en este dispositivo. Revisa que tenga espacio disponible.']);
    }

    let mensaje = 'Mantención guardada en este dispositivo. Se enviará cuando vuelva la señal.';
    if (navigator.onLine) {
      boton.textContent = 'Enviando…';
      const r = await COVEPA.sync.sincronizarTodo();
      if (r.enviados) mensaje = 'Mantención enviada.';
      else if (r.rechazados) mensaje = 'El servidor rechazó el formulario. Revisa el detalle en tu pantalla de inicio.';
      else mensaje = 'Mantención guardada. Se enviará en cuanto sea posible.';
    }
    sessionStorage.setItem('covepa_flash', mensaje);
    location.href = '/mantenciones/inicio/';
  }

  function mostrarErrores(lista) {
    erroresForm.replaceChildren(...lista.map((t) => el('li', { texto: t })));
    erroresForm.hidden = false;
    erroresForm.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  // ------------------------------------------------------------ arranque
  function planDeLaUrl() {
    return paquete.pendientes.find((p) => String(p.plan_id) === params.get('plan')) || null;
  }

  function llenarPlantillas() {
    selPlantilla.replaceChildren();
    const equipo = paquete.equipos.find((e) => String(e.id) === selEquipo.value);
    const ids = equipo ? equipo.plantillas : [];
    $('grupo-plantilla').hidden = ids.length <= 1;
    // Sin formularios publicados se explica el motivo (antes el aviso quedaba dentro de un menú oculto y la pantalla parecía vacía)
    const faltaFormulario = Boolean(equipo) && ids.length === 0;
    $('sin-formularios').hidden = !faltaFormulario;
    if (faltaFormulario) $('categoria-sin-formulario').textContent = `«${equipo.categoria}»`;
    ids.forEach((id) => selPlantilla.append(el('option', { value: String(id), texto: paquete.plantillas[id].nombre })));
    const plan = planDeLaUrl();
    if (plan && equipo && plan.equipo_id === equipo.id && ids.includes(plan.plantilla_id)) selPlantilla.value = String(plan.plantilla_id);
    armarFormulario();
  }

  async function iniciar() {
    // Con señal se descargan los datos al día (equipos o plantillas nuevas); sin señal, los guardados.
    paquete = (navigator.onLine && (await COVEPA.sync.refrescarPaquete())) || (await COVEPA.sync.paqueteLocal());
    if (!paquete) {
      $('sin-datos').hidden = false;
      if (navigator.onLine) {
        // Con señal pero sin datos: el servidor no respondió bien (no es falta de conexión)
        $('sin-datos-titulo').textContent = 'No pudimos descargar tus datos';
        $('sin-datos-texto').textContent = 'El servidor no respondió. Inténtalo de nuevo; si sigue igual, avisa a la jefatura.';
        $('reintentar').hidden = false;
        $('reintentar').addEventListener('click', () => location.reload());
      }
      return;
    }
    if (!paquete.equipos.length) { $('sin-equipos').hidden = false; return; }
    form.hidden = false;
    // append() nativo NO acepta arreglos (los convierte a texto): hay que esparcirlos con "...".
    selEquipo.append(el('option', { value: '', texto: 'Elige un equipo' }),
      ...paquete.equipos.map((e) => el('option', { value: String(e.id), texto: `${e.codigo} · ${e.nombre}` })));
    const previo = params.get('equipo');
    if (previo && paquete.equipos.some((e) => String(e.id) === previo)) selEquipo.value = previo;
    else if (paquete.equipos.length === 1) selEquipo.value = String(paquete.equipos[0].id);
    selEquipo.addEventListener('change', llenarPlantillas);
    selPlantilla.addEventListener('change', armarFormulario);
    form.addEventListener('submit', guardar);
    llenarPlantillas();
  }

  async function mostrarCola() {
    const { pendientes } = await COVEPA.sync.contar();
    const panel = $('panel-sync');
    panel.hidden = pendientes === 0;
    $('texto-sync').textContent = `${pendientes} formulario${pendientes === 1 ? '' : 's'} pendiente${pendientes === 1 ? '' : 's'} de enviar.`;
  }
  $('boton-sync').addEventListener('click', () => COVEPA.sync.sincronizarTodo());
  document.addEventListener('covepa:cola', mostrarCola);
  mostrarCola();
  iniciar();
})();
