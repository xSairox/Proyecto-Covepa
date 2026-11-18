/* Cola de formularios y sincronización (HU-05).
   Cada formulario se guarda en el celular con un UUID. Al haber señal: 1) sube fotos y videos
   directo a Cloudinary, 2) agrega las URL al JSON, 3) lo envía al servidor. Reenviar el mismo
   UUID es seguro: el servidor lo reconoce y no lo duplica. */
(function () {
  'use strict';
  const COVEPA = (window.COVEPA = window.COVEPA || {});
  const db = () => COVEPA.db;
  let enCurso = false;

  const emitir = () => document.dispatchEvent(new CustomEvent('covepa:cola'));

  async function misRegistros() {
    const todos = await db().todos('cola');
    return todos.filter((r) => r.usuario_id === COVEPA.cfg.usuarioId).sort((a, b) => a.creado - b.creado);
  }

  async function encolar(registro) {
    await db().guardar('cola', { ...registro, usuario_id: COVEPA.cfg.usuarioId, estado: 'pendiente', creado: Date.now(), intentos: 0, errores: [] });
    emitir();
  }

  async function contar() {
    const r = await misRegistros();
    return { pendientes: r.filter((x) => x.estado === 'pendiente').length, conError: r.filter((x) => x.estado === 'error').length };
  }

  async function sincronizarRegistro(registro, csrf) {
    // 1) Archivos: se suben una sola vez; el avance se guarda para no repetir si se corta la señal
    for (const archivo of registro.archivos || []) {
      if (archivo.resultado) continue;
      const subido = await COVEPA.subirACloudinary(archivo.blob, archivo.tipo);
      archivo.resultado = { campo: archivo.campo, ...subido };
      archivo.blob = null; // ya está en la nube
      await db().guardar('cola', registro);
    }
    // 2) JSON con las URL
    const documento = { ...registro.doc, evidencias: (registro.archivos || []).map((a) => a.resultado) };
    const r = await fetch(COVEPA.cfg.urlSincronizar, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
      body: JSON.stringify(documento),
    });
    if (r.status === 201 || r.status === 200) {
      await db().borrar('cola', registro.id);
      return 'ok';
    }
    if (r.status === 401) return 'sesion';
    let errores = [];
    try { errores = (await r.json()).errores || []; } catch (e) { /* sin cuerpo */ }
    if ([400, 403, 409, 413].includes(r.status)) {
      // El servidor rechazó el contenido: reintentar no sirve. Se deja visible para corregir o descartar.
      registro.estado = 'error';
      registro.errores = errores.length ? errores : [`El servidor rechazó el formulario (código ${r.status}).`];
      await db().guardar('cola', registro);
      return 'rechazado';
    }
    registro.intentos += 1;
    await db().guardar('cola', registro);
    return 'reintentar';
  }

  /** Envía todo lo pendiente. Devuelve {enviados, rechazados, pendientes, sesion}. */
  async function sincronizarTodo() {
    const resumen = { enviados: 0, rechazados: 0, pendientes: 0, sesion: false };
    if (enCurso || !navigator.onLine) return resumen;
    enCurso = true;
    try {
      const pendientes = (await misRegistros()).filter((r) => r.estado === 'pendiente');
      if (!pendientes.length) return resumen;
      const sesion = await COVEPA.sesion();
      if (!sesion.autenticado) {
        resumen.sesion = !sesion.error;
        resumen.pendientes = pendientes.length;
        return resumen;
      }
      for (const registro of pendientes) {
        try {
          const estado = await sincronizarRegistro(registro, sesion.csrf);
          if (estado === 'ok') resumen.enviados += 1;
          else if (estado === 'rechazado') resumen.rechazados += 1;
          else if (estado === 'sesion') { resumen.sesion = true; break; }
          else resumen.pendientes += 1;
        } catch (e) {
          if (e && e.sesion) { resumen.sesion = true; break; }
          resumen.pendientes += 1; // sin señal o falla de red: queda para el próximo intento
        }
      }
    } finally {
      enCurso = false;
      emitir();
    }
    return resumen;
  }

  /** Descarga equipos, plantillas y pendientes para usarlos sin conexión. */
  async function refrescarPaquete() {
    if (!navigator.onLine) return null;
    try {
      const r = await fetch(COVEPA.cfg.urlPaquete, { credentials: 'same-origin', cache: 'no-store' });
      if (!r.ok) return null;
      const paquete = await r.json();
      await db().guardar('meta', { clave: 'paquete', valor: paquete });
      // Deja guardadas las pantallas de terreno para abrirlas sin señal
      ['/mantenciones/inicio/', '/mantenciones/registrar/'].forEach((u) => fetch(u, { credentials: 'same-origin' }).catch(() => {}));
      document.dispatchEvent(new CustomEvent('covepa:paquete'));
      return paquete;
    } catch (e) {
      return null;
    }
  }

  async function paqueteLocal() {
    const fila = await db().obtener('meta', 'paquete');
    const paquete = fila && fila.valor;
    return paquete && paquete.usuario && paquete.usuario.id === COVEPA.cfg.usuarioId ? paquete : null;
  }

  async function descartar(id) {
    await db().borrar('cola', id);
    emitir();
  }

  COVEPA.sync = { encolar, contar, misRegistros, sincronizarTodo, refrescarPaquete, paqueteLocal, descartar };

  // Envío automático: al abrir, al volver la señal y cada minuto mientras la pantalla está abierta
  if (COVEPA.cfg.esTecnico) {
    const intentar = () => { if (document.visibilityState === 'visible') COVEPA.sync.sincronizarTodo(); };
    window.addEventListener('online', () => { COVEPA.sync.sincronizarTodo(); COVEPA.sync.refrescarPaquete(); });
    setInterval(intentar, 60000);
    window.addEventListener('load', () => { COVEPA.sync.sincronizarTodo(); });
  }
})();
