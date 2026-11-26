// Sitios de Descubrir: el texto de cada estado de análisis y adónde lleva tocarlos.
import { router } from 'expo-router';

import { Lugar } from './api';

export const ESTADOS: Record<string, string> = {
  analizado: 'Analizado',
  pendiente: 'Análisis en camino',
  procesando: 'Análisis en camino',
  error: 'No se pudo analizar',
  sin_analizar: 'Datos básicos',
  cerrado: 'Ha cerrado',
};

/** Los analizados abren su ficha completa de restaurante; los demás, la del sitio (con «Analizar»). */
export function abrirLugar(l: Lugar): void {
  if (l.estado === 'analizado' && l.restaurante_id) {
    router.push({ pathname: '/restaurante/[id]', params: { id: String(l.restaurante_id) } });
  } else {
    router.push({ pathname: '/lugar/[id]', params: { id: l.id } });
  }
}
