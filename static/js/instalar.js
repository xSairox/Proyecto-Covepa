/* COVEPA Mantenciones · instalar la app en el celular (PWA).
   Android, Chrome y Edge avisan con "beforeinstallprompt": se muestra el botón "Instalar la app".
   iPhone y iPad (Safari) no tienen ese aviso: se muestran los pasos para "Añadir a pantalla de inicio".
   Si la app ya está instalada y abierta como app, el bloque no aparece. */
(function () {
  'use strict';
  const bloque = document.getElementById('instalar');
  if (!bloque) return;
  const boton = document.getElementById('instalar-boton');
  const ayudaIos = document.getElementById('instalar-ios');

  const comoApp = () => window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
  const esIos = () => /iphone|ipad|ipod/i.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  if (comoApp()) return;

  let aviso = null;

  window.addEventListener('beforeinstallprompt', (evento) => {
    evento.preventDefault();       // el botón decide cuándo mostrar el cuadro del navegador
    aviso = evento;
    bloque.hidden = false;
    boton.hidden = false;
    ayudaIos.hidden = true;
  });

  boton.addEventListener('click', async () => {
    if (!aviso) return;
    aviso.prompt();
    await aviso.userChoice;
    aviso = null;                  // el aviso solo puede usarse una vez
    boton.hidden = true;
  });

  window.addEventListener('appinstalled', () => { bloque.hidden = true; });

  if (esIos()) {
    bloque.hidden = false;
    ayudaIos.hidden = false;
  }
})();
