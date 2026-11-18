/* Service worker de COVEPA Mantenciones.
   Objetivo: que el técnico abra la app y registre una mantención sin señal (HU-05).
   - Pantallas de terreno: red primero (4 s) y, si falla, la última copia guardada. La app las guarda por adelantado
     (mensaje "paginas") para que abrir la app sin señal no dependa de haberlas visitado antes.
   - /static/: se sirve desde el caché y se actualiza en segundo plano.
   - Nunca guarda /api/, el login, la administración ni respuestas con redirección.
   __VERSION__ se reemplaza en cada despliegue y renueva el caché. */
'use strict';

const VERSION = '__VERSION__';
const CACHE_PAGINAS = `covepa-paginas-${VERSION}`;
const CACHE_ESTATICOS = `covepa-estaticos-${VERSION}`;
const ESPERA_RED_MS = 4000;

// Solo se guardan estas pantallas: lo que el técnico necesita en terreno
const PAGINAS_GUARDABLES = [
  /^\/$/,
  /^\/offline\/$/,
  /^\/mantenciones\/inicio\/$/,
  /^\/mantenciones\/registrar\/$/,
  /^\/mantenciones\/registro\/[0-9a-f-]{36}\/$/,
  /^\/tickets\/\d+\/$/,
];
const NUNCA = [/^\/api\//, /^\/gestion-interna\//, /^\/cuentas\//, /^\/auditoria\//, /^\/salud\//, /^\/cron\//];

const esGuardable = (ruta) => PAGINAS_GUARDABLES.some((r) => r.test(ruta)) && !NUNCA.some((r) => r.test(ruta));

async function respuestaCacheable(respuesta) {
  return respuesta && respuesta.ok && !respuesta.redirected && respuesta.type === 'basic';
}

async function guardarRecursos(urls) {
  const cache = await caches.open(CACHE_ESTATICOS);
  await Promise.all(urls.map(async (u) => {
    try {
      const r = await fetch(u, { credentials: 'same-origin' });
      if (await respuestaCacheable(r)) await cache.put(u, r);
    } catch (e) { /* sin red: se intentará en otra visita */ }
  }));
}

// Guarda pantallas completas (no solo sus archivos) para poder abrirlas sin señal aunque no se hayan visitado antes.
// Solo se guardan respuestas directas: una redirección (p. ej. "/") o un 403 no se guardan.
async function guardarPaginas(rutas) {
  const cache = await caches.open(CACHE_PAGINAS);
  await Promise.all(rutas.map(async (ruta) => {
    try {
      const r = await fetch(ruta, { credentials: 'same-origin' });
      if (await respuestaCacheable(r)) await cache.put(ruta, r);
    } catch (e) { /* sin red: se intentará en la próxima visita */ }
  }));
}

self.addEventListener('install', (evento) => {
  evento.waitUntil((async () => {
    const paginas = await caches.open(CACHE_PAGINAS);
    try {
      const r = await fetch('/offline/', { credentials: 'same-origin' });
      if (await respuestaCacheable(r)) {
        const copia = r.clone();
        await paginas.put('/offline/', r);
        // También sus archivos estáticos (CSS, íconos), para que se vea bien sin señal
        const html = await copia.text();
        const estaticos = [...new Set([...html.matchAll(/(?:href|src)="(\/static\/[^"]+)"/g)].map((m) => m[1]))];
        await guardarRecursos(estaticos);
      }
    } catch (e) { /* instalación sin red: la página sin conexión se guardará en la primera visita */ }
    await guardarRecursos(['/manifest.webmanifest']);
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', (evento) => {
  evento.waitUntil((async () => {
    const vigentes = new Set([CACHE_PAGINAS, CACHE_ESTATICOS]);
    const nombres = await caches.keys();
    await Promise.all(nombres.filter((n) => n.startsWith('covepa-') && !vigentes.has(n)).map((n) => caches.delete(n)));
    await self.clients.claim();
  })());
});

function conTiempoLimite(promesa, ms) {
  return new Promise((resolver, rechazar) => {
    const t = setTimeout(() => rechazar(new Error('tiempo agotado')), ms);
    promesa.then((v) => { clearTimeout(t); resolver(v); }, (e) => { clearTimeout(t); rechazar(e); });
  });
}

async function navegacion(peticion) {
  const url = new URL(peticion.url);
  const cache = await caches.open(CACHE_PAGINAS);
  try {
    const r = await conTiempoLimite(fetch(peticion), ESPERA_RED_MS);
    if (esGuardable(url.pathname) && (await respuestaCacheable(r))) await cache.put(url.pathname, r.clone());
    return r;
  } catch (e) {
    // Sin señal o red muy lenta: la última copia de esa pantalla, o la página de aviso
    // "/" es la dirección con la que se abre la app instalada y siempre redirige: nunca queda guardada tal cual,
    // así que sin señal se entrega la pantalla de inicio del técnico.
    const inicio = url.pathname === '/' ? await cache.match('/mantenciones/inicio/') : null;
    const copia = (await cache.match(url.pathname)) || inicio || (await cache.match('/offline/'));
    if (copia) return copia;
    return new Response('Sin conexión', { status: 503, headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
  }
}

async function estatico(peticion) {
  const cache = await caches.open(CACHE_ESTATICOS);
  const guardado = await cache.match(peticion);
  const red = fetch(peticion).then(async (r) => {
    if (await respuestaCacheable(r)) await cache.put(peticion, r.clone());
    return r;
  }).catch(() => null);
  return guardado || (await red) || new Response('', { status: 504 });
}

self.addEventListener('fetch', (evento) => {
  const peticion = evento.request;
  if (peticion.method !== 'GET') return;
  const url = new URL(peticion.url);
  if (url.origin !== self.location.origin) return; // Cloudinary y otros: directo a la red
  if (NUNCA.some((r) => r.test(url.pathname)) && !url.pathname.startsWith('/cuentas/')) return;
  if (url.pathname === '/sw.js') return;

  if (peticion.mode === 'navigate') {
    if (url.pathname.startsWith('/cuentas/') || NUNCA.some((r) => r.test(url.pathname))) return; // el login siempre va a la red
    evento.respondWith(navegacion(peticion));
    return;
  }
  if (url.pathname.startsWith('/static/') || url.pathname === '/manifest.webmanifest') {
    evento.respondWith(estatico(peticion));
  }
});

self.addEventListener('message', (evento) => {
  const datos = evento.data || {};
  if (datos.tipo === 'cachear' && Array.isArray(datos.urls)) {
    const rutas = datos.urls.filter((u) => typeof u === 'string' && u.startsWith('/static/'));
    evento.waitUntil(guardarRecursos(rutas));
  } else if (datos.tipo === 'paginas' && Array.isArray(datos.urls)) {
    evento.waitUntil(guardarPaginas(datos.urls.filter((u) => typeof u === 'string' && esGuardable(u))));
  } else if (datos.tipo === 'limpiar') {
    // Cierre de sesión: se borran las pantallas guardadas (equipos compartidos). Los estáticos no tienen datos.
    evento.waitUntil(caches.delete(CACHE_PAGINAS));
  }
});
