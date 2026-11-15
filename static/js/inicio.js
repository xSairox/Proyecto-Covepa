/* Inicio del técnico: se dibuja con los datos guardados en el dispositivo (funciona sin conexión). */
(function () {
  'use strict';
  const { el, fechaLegible } = window.COVEPA;
  const COVEPA = window.COVEPA;
  const $ = (id) => document.getElementById(id);

  const diasHasta = (fechaIso) => {
    const hoy = new Date();
    hoy.setHours(0, 0, 0, 0);
    return Math.round((new Date(`${fechaIso}T00:00:00`) - hoy) / 86400000);
  };
  const textoDias = (d) => (d < 0 ? `Vencida hace ${-d} día${d === -1 ? '' : 's'}` : d === 0 ? 'Vence hoy' : `Vence en ${d} día${d === 1 ? '' : 's'}`);
  const tono = (d) => (d < 0 ? 'vencido' : d <= 2 ? 'alerta' : 'ok');

  function vacio(titulo, texto) {
    return el('li', { class: 'vacio' }, el('strong', { texto: titulo }), texto);
  }

  async function pintarCola() {
    const panel = $('panel-sync');
    let lista = $('lista-cola');
    if (!lista) {
      lista = el('ul', { class: 'lista', id: 'lista-cola', style: 'margin-bottom:16px' });
      panel.after(lista);
    }
    const registros = await COVEPA.sync.misRegistros();
    lista.replaceChildren();
    const pendientes = registros.filter((r) => r.estado === 'pendiente');
    const conError = registros.filter((r) => r.estado === 'error');
    panel.hidden = registros.length === 0;
    $('texto-sync').textContent = pendientes.length
      ? `${pendientes.length} formulario${pendientes.length === 1 ? '' : 's'} guardado${pendientes.length === 1 ? '' : 's'} en este dispositivo, pendiente${pendientes.length === 1 ? '' : 's'} de enviar.`
      : conError.length ? 'Hay formularios que el servidor rechazó. Revísalos abajo.' : '';
    $('boton-sync').hidden = pendientes.length === 0;

    pendientes.forEach((r) => lista.append(
      el('li', { class: 'item item--alerta' },
        el('span', { class: 'item__titulo' }, el('span', { class: 'codigo', texto: r.doc.equipo.codigo }), r.doc.plantilla.nombre),
        el('span', { class: 'item__meta', texto: `Registrada ${fechaLegible(r.doc.termino)}` }),
        el('span', { class: 'item__lado' }, el('span', { class: 'chip chip--alerta', texto: 'Pendiente de enviar' })))));

    conError.forEach((r) => lista.append(
      el('li', { class: 'item item--vencido' },
        el('span', { class: 'item__titulo' }, el('span', { class: 'codigo', texto: r.doc.equipo.codigo }), r.doc.plantilla.nombre),
        el('ul', { class: 'errorlist' }, r.errores.map((e) => el('li', { texto: e }))),
        el('span', { class: 'item__lado' },
          el('button', { class: 'boton boton--peligro boton--chico', type: 'button', texto: 'Descartar', onclick: async () => { await COVEPA.sync.descartar(r.id); } }),
          el('span', { class: 'item__meta', texto: 'Vuelve a registrar la mantención con los datos corregidos.' })))));
    return registros;
  }

  async function pintar() {
    const registros = await pintarCola();
    const enCola = new Set(registros.filter((r) => r.doc.plan_id).map((r) => r.doc.plan_id));
    const paquete = await COVEPA.sync.paqueteLocal();
    const pend = $('lista-pendientes');
    const tick = $('lista-tickets');
    const rec = $('lista-recientes');
    [pend, tick, rec].forEach((l) => l.replaceChildren());

    if (!paquete) {
      pend.append(vacio('Aún no hay datos en este dispositivo', 'Conéctate a internet una vez para descargar tus equipos y formularios.'));
      tick.append(vacio('Sin datos', ''));
      rec.append(vacio('Sin datos', ''));
      $('nota-datos').textContent = '';
      return;
    }

    const lista = paquete.pendientes.filter((p) => !enCola.has(p.plan_id));
    if (!lista.length) pend.append(vacio('No tienes mantenciones por vencer', 'Todo al día para los próximos 7 días.'));
    lista.forEach((p) => {
      const d = diasHasta(p.proxima_fecha);
      pend.append(el('li', {}, el('a', { class: `item item--${tono(d)}`, href: `/mantenciones/registrar/?equipo=${p.equipo_id}&plan=${p.plan_id}` },
        el('span', { class: 'item__titulo' }, p.actividad, el('span', { class: 'codigo', texto: p.equipo_codigo })),
        el('span', { class: 'item__lado' }, el('span', { class: `chip chip--${tono(d)}`, texto: textoDias(d) })))));
    });

    if (!paquete.tickets.length) tick.append(vacio('No tienes tickets asignados', 'Cuando la jefatura te asigne un trabajo, aparecerá aquí.'));
    paquete.tickets.forEach((t) => tick.append(el('li', {}, el('a', { class: 'item item--curso', href: t.url },
      el('span', { class: 'item__titulo' }, t.numero, el('span', { class: 'chip chip--curso', texto: t.estado })),
      el('span', { texto: t.descripcion }),
      t.equipo ? el('span', { class: 'item__meta codigo', texto: t.equipo }) : null))));

    if (!paquete.recientes.length) rec.append(vacio('Sin registros en los últimos 30 días', ''));
    paquete.recientes.forEach((r) => rec.append(el('li', {}, el('a', { class: 'item item--ok', href: `/mantenciones/registro/${r.id}/` },
      el('span', { class: 'item__titulo' }, el('span', { class: 'codigo', texto: r.equipo })),
      el('span', { class: 'item__meta', texto: fechaLegible(r.inicio) })))));

    $('nota-datos').textContent = `Datos descargados el ${fechaLegible(paquete.generado_en)}. Se actualizan solos cuando hay señal.`;
  }

  function mostrarFlash() {
    const texto = sessionStorage.getItem('covepa_flash');
    if (!texto) return;
    sessionStorage.removeItem('covepa_flash');
    const lista = el('ul', { class: 'mensajes', role: 'status' }, el('li', { class: 'mensaje mensaje--success', texto }));
    document.querySelector('.titulo-pagina').after(lista);
  }

  $('boton-sync').addEventListener('click', async () => {
    $('boton-sync').disabled = true;
    const r = await COVEPA.sync.sincronizarTodo();
    $('boton-sync').disabled = false;
    if (r.sesion) $('texto-sync').textContent = 'Tu sesión venció. Vuelve a iniciar sesión para enviar los formularios; siguen guardados aquí.';
    await pintar();
  });

  document.addEventListener('covepa:cola', pintar);
  document.addEventListener('covepa:paquete', pintar);
  mostrarFlash();
  pintar();
  COVEPA.sync.refrescarPaquete();
})();
