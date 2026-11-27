// El mazo del «Food match»: la primera vez la API tarda unos segundos en prepararlo, así que Comer hoy lo pide al
// abrirse (precargarMazo) y la pantalla del Food match se queda con esa misma petición (cogerMazo).
import * as Location from 'expo-location';

import { api, Mazo } from '@/lib/api';

let pendiente: Promise<Mazo> | null = null;

async function ubicacionSinPreguntar(): Promise<{ lat: number; lon: number } | undefined> {
  try {   // solo si ya diste permiso (en Comer hoy); si no, salen sitios de Madrid
    if ((await Location.getForegroundPermissionsAsync()).status !== 'granted') return undefined;
    const pos = await Location.getLastKnownPositionAsync();
    return pos ? { lat: pos.coords.latitude, lon: pos.coords.longitude } : undefined;
  } catch {
    return undefined;
  }
}

function pedir(): Promise<Mazo> {
  return ubicacionSinPreguntar().then((u) => api<Mazo>('GET', '/deslizar', undefined, u));
}

/** Empieza a preparar el mazo (si falla, no pasa nada: la pantalla lo vuelve a pedir). */
export function precargarMazo(): void {
  if (pendiente) return;
  const p = pedir();
  pendiente = p;
  p.catch(() => { if (pendiente === p) pendiente = null; });
}

/** El mazo precargado (si lo hay) o uno recién pedido; se gasta: la próxima vez se pide otra vez. */
export function cogerMazo(): Promise<Mazo> {
  const p = pendiente ?? pedir();
  pendiente = null;
  return p;
}
