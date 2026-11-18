/* Almacenamiento local (IndexedDB): paquete de datos y cola de formularios pendientes. */
(function () {
  'use strict';
  const COVEPA = (window.COVEPA = window.COVEPA || {});
  const NOMBRE = 'covepa';
  const VERSION = 1;

  function abrir() {
    return new Promise((resolver, rechazar) => {
      const pedido = indexedDB.open(NOMBRE, VERSION);
      pedido.onupgradeneeded = () => {
        const bd = pedido.result;
        if (!bd.objectStoreNames.contains('meta')) bd.createObjectStore('meta', { keyPath: 'clave' });
        if (!bd.objectStoreNames.contains('cola')) bd.createObjectStore('cola', { keyPath: 'id' });
      };
      pedido.onsuccess = () => resolver(pedido.result);
      pedido.onerror = () => rechazar(pedido.error);
    });
  }

  let promesaBd = null;
  const bd = () => (promesaBd = promesaBd || abrir());

  async function transaccion(almacen, modo, accion) {
    const base = await bd();
    return new Promise((resolver, rechazar) => {
      const tx = base.transaction(almacen, modo);
      const resultado = accion(tx.objectStore(almacen));
      tx.oncomplete = () => resolver(resultado && 'result' in resultado ? resultado.result : undefined);
      tx.onerror = () => rechazar(tx.error);
      tx.onabort = () => rechazar(tx.error);
    });
  }

  COVEPA.db = {
    obtener: (almacen, clave) => transaccion(almacen, 'readonly', (s) => s.get(clave)),
    guardar: (almacen, valor) => transaccion(almacen, 'readwrite', (s) => s.put(valor)),
    borrar: (almacen, clave) => transaccion(almacen, 'readwrite', (s) => s.delete(clave)),
    todos: (almacen) => transaccion(almacen, 'readonly', (s) => s.getAll()),
  };
})();
