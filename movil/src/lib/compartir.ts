// Compartir por WhatsApp (o lo que elija el usuario en el menú del móvil): tu perfil o un restaurante.
// WhatsApp solo hace pulsables los enlaces http(s), así que se comparte la página /abrir/… de la API, que manda a la
// app (dondecomemos://…; en Expo Go, exp://…/--/…, que solo va con el PC de desarrollo en la misma wifi).
// ponytail: con la API publicada en https, estos enlaces valdrán para todos; sin la app instalada, aún no llevan a la tienda.
import * as Linking from 'expo-linking';
import { Share } from 'react-native';

import { BASE } from '@/lib/api';

/** Enlace pulsable (http) que abre esa pantalla de la app. */
function enlace(ruta: 'restaurante' | 'persona', valor: string | number): string {
  return `${BASE}/abrir/${ruta}/${valor}?app=${encodeURIComponent(Linking.createURL(`/${ruta}/${valor}`))}`;
}

export function compartirPerfil(alias: string): Promise<unknown> {
  return Share.share({ message: `¡Añádeme en ¿Dónde comemos?! Soy @${alias}: ${enlace('persona', alias)}` });
}

export function compartirRestaurante(id: number, nombre: string, lat: number | null, lon: number | null): Promise<unknown> {
  // la ficha en la app y, para quien no la tenga, el sitio en Google Maps
  const mapa = lat !== null && lon !== null
    ? `https://www.google.com/maps/search/?api=1&query=${lat},${lon}`
    : `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${nombre} Madrid`)}`;
  return Share.share({ message: `¿Vamos a ${nombre}? Míralo en ¿Dónde comemos?: ${enlace('restaurante', id)}
En Google Maps: ${mapa}` });
}
