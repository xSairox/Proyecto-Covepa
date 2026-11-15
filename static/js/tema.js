/* Tema claro / oscuro. Se carga en <head> (sin defer) para aplicar el tema antes de pintar y evitar el parpadeo.
   Si la persona nunca eligió, se usa el tema del sistema y se sigue su cambio en vivo. */
(function () {
  'use strict';
  var CLAVE = 'covepa_tema';
  var raiz = document.documentElement;
  var sistema = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;

  function guardado() {
    try { var v = localStorage.getItem(CLAVE); return v === 'claro' || v === 'oscuro' ? v : null; } catch (e) { return null; }
  }
  function efectivo() { return guardado() || (sistema && sistema.matches ? 'oscuro' : 'claro'); }

  function aplicar(tema) {
    raiz.setAttribute('data-tema', tema);
    var color = tema === 'oscuro' ? '#1E1E1A' : '#FFFFFF';
    var metas = document.querySelectorAll('meta[name="theme-color"]');
    for (var i = 0; i < metas.length; i++) { metas[i].setAttribute('content', color); metas[i].removeAttribute('media'); }
    var botones = document.querySelectorAll('[data-alternar-tema]');
    for (var j = 0; j < botones.length; j++) {
      botones[j].hidden = false;
      var etiqueta = tema === 'oscuro' ? 'Cambiar a tema claro' : 'Cambiar a tema oscuro';
      botones[j].setAttribute('aria-label', etiqueta);
      botones[j].setAttribute('title', etiqueta);
    }
  }

  aplicar(efectivo());

  if (sistema && sistema.addEventListener) {
    sistema.addEventListener('change', function () { if (!guardado()) aplicar(efectivo()); });
  }

  document.addEventListener('DOMContentLoaded', function () {
    aplicar(efectivo()); // ahora existen los botones y las etiquetas meta
    document.addEventListener('click', function (ev) {
      var boton = ev.target.closest ? ev.target.closest('[data-alternar-tema]') : null;
      if (!boton) return;
      var nuevo = efectivo() === 'oscuro' ? 'claro' : 'oscuro';
      try { localStorage.setItem(CLAVE, nuevo); } catch (e) { /* sin almacenamiento: vale solo para esta visita */ }
      aplicar(nuevo);
    });
  });
})();
