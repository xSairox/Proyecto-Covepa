/* COVEPA Mantenciones · utilidades comunes, aviso de conexión y service worker.
   No hay JavaScript en línea en las plantillas (CSP): todo vive en archivos estáticos. */
(function () {
  'use strict';
  const cuerpo = document.body;
  const COVEPA = (window.COVEPA = window.COVEPA || {});

  COVEPA.cfg = {
    urlSesion: cuerpo.dataset.urlSesion,
    urlPaquete: cuerpo.dataset.urlPaquete,
    urlFirma: cuerpo.dataset.urlFirma,
    urlSincronizar: cuerpo.dataset.urlSincronizar,
    urlLogin: cuerpo.dataset.urlLogin,
    esTecnico: cuerpo.dataset.esTecnico === '1',
    usuarioId: cuerpo.dataset.usuarioId ? Number(cuerpo.dataset.usuarioId) : null,
  };

  /** Crea elementos sin usar innerHTML: los datos siempre entran como texto (evita XSS). */
  COVEPA.el = function (etiqueta, atributos, ...hijos) {
    const nodo = document.createElement(etiqueta);
    Object.entries(atributos || {}).forEach(([clave, valor]) => {
      if (valor === null || valor === undefined || valor === false) return;
      if (clave === 'class') nodo.className = valor;
      else if (clave === 'texto') nodo.textContent = valor;
      else if (clave.startsWith('on') && typeof valor === 'function') nodo.addEventListener(clave.slice(2), valor);
      else nodo.setAttribute(clave, valor === true ? '' : valor);
    });
    hijos.flat().forEach((h) => {
      if (h === null || h === undefined || h === false) return;
      nodo.append(h.nodeType ? h : document.createTextNode(String(h)));
    });
    return nodo;
  };

  COVEPA.uuid = function () {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    const b = crypto.getRandomValues(new Uint8Array(16));
    b[6] = (b[6] & 0x0f) | 0x40;
    b[8] = (b[8] & 0x3f) | 0x80;
    const h = [...b].map((x) => x.toString(16).padStart(2, '0')).join('');
    return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
  };

  COVEPA.fechaLegible = function (iso) {
    const f = new Date(iso);
    return f.toLocaleString('es-CL', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  };

  /** Sesión y token CSRF vigentes. Devuelve {autenticado, csrf} o {autenticado:false} si no hay red. */
  COVEPA.sesion = async function () {
    try {
      const r = await fetch(COVEPA.cfg.urlSesion, { credentials: 'same-origin', cache: 'no-store' });
      if (!r.ok) return { autenticado: false, error: true };
      return await r.json();
    } catch (e) {
      return { autenticado: false, error: true };
    }
  };

  /**
   * Sube una foto o un video DIRECTO a Cloudinary con una firma del servidor.
   * Devuelve la evidencia lista para el JSON: {tipo, url, public_id, peso_kb, duracion_seg}.
   */
  COVEPA.subirACloudinary = async function (archivo, tipo) {
    const rf = await fetch(`${COVEPA.cfg.urlFirma}?tipo=${encodeURIComponent(tipo)}`, { credentials: 'same-origin', cache: 'no-store' });
    if (rf.status === 401) throw Object.assign(new Error('Sesión vencida'), { sesion: true });
    if (!rf.ok) throw new Error('No se pudo obtener la autorización de subida.');
    const f = await rf.json();
    const datos = new FormData();
    datos.append('file', archivo);
    datos.append('api_key', f.api_key);
    datos.append('timestamp', f.timestamp);
    datos.append('signature', f.firma);
    datos.append('folder', f.folder);
    datos.append('allowed_formats', f.allowed_formats);
    const ru = await fetch(f.url_subida, { method: 'POST', body: datos });
    if (!ru.ok) {
      let motivo = 'Cloudinary rechazó el archivo.';
      try { motivo = (await ru.json()).error.message || motivo; } catch (e) { /* sin detalle */ }
      throw new Error(motivo);
    }
    const r = await ru.json();
    return {
      tipo,
      url: r.secure_url,
      public_id: r.public_id,
      peso_kb: Math.max(1, Math.ceil((r.bytes || archivo.size) / 1024)),
      duracion_seg: typeof r.duration === 'number' ? r.duration : null,
    };
  };

  // ---------------------------------------------------------------- aviso de conexión
  const aviso = document.getElementById('estado-conexion');
  function actualizarConexion() {
    if (aviso) aviso.classList.toggle('visible', !navigator.onLine);
    document.dispatchEvent(new CustomEvent('covepa:conexion', { detail: { enLinea: navigator.onLine } }));
  }
  window.addEventListener('online', actualizarConexion);
  window.addEventListener('offline', actualizarConexion);
  actualizarConexion();

  // ---------------------------------------------------------------- service worker
  function avisarServiceWorker(mensaje) {
    if (navigator.serviceWorker && navigator.serviceWorker.controller) navigator.serviceWorker.controller.postMessage(mensaje);
  }

  if ('serviceWorker' in navigator) {
    window.addEventListener('load', async () => {
      try {
        const registro = await navigator.serviceWorker.register('/sw.js', { scope: '/' });
        await navigator.serviceWorker.ready;
        // Guarda lo que esta página ya cargó (en la primera visita el SW aún no la controlaba)
        const recursos = performance.getEntriesByType('resource').map((r) => new URL(r.name).pathname).filter((p) => p.startsWith('/static/'));
        const mensaje = { tipo: 'cachear', urls: [...new Set(recursos)] };
        (registro.active || navigator.serviceWorker.controller).postMessage(mensaje);
      } catch (e) {
        console.warn('No se pudo registrar el service worker', e);
      }
    });
  }

  // Al cerrar sesión se borran las páginas guardadas (equipos compartidos). La cola de envío NO se borra.
  document.addEventListener('submit', (ev) => {
    const form = ev.target;
    if (form && form.action && form.action.endsWith('/cuentas/logout/')) avisarServiceWorker({ tipo: 'limpiar' });
  });
})();
