// Los restaurantes a los que has ido (app.mis_visitas): todas las tarjetas los marcan con «✓ Has ido» y borde verde.
// Se piden una vez y se comparten; olvidarVisitados() tras guardar o quitar un «He ido».
import { useSyncExternalStore } from 'react';

import { api, Visita } from './api';

let ids: ReadonlySet<number> = new Set();
let pedido: Promise<void> | null = null;
const oyentes = new Set<() => void>();

function avisar() {
  oyentes.forEach((f) => f());
}

function pedir() {
  pedido ??= api<{ visitas: Visita[] }>('GET', '/visitas')
    .then((r) => {
      ids = new Set(r.visitas.map((v) => v.restaurante_id));
      avisar();
    })
    .catch(() => {
      pedido = null;   // sin conexión: sin marcas, y se vuelve a intentar la próxima vez
    });
}

export function olvidarVisitados(): void {
  pedido = null;
  pedir();
}

function suscribir(f: () => void) {
  oyentes.add(f);
  pedir();
  return () => {
    oyentes.delete(f);
  };
}

export function useVisitados(): ReadonlySet<number> {
  return useSyncExternalStore(suscribir, () => ids, () => ids);
}
