// Compartir por WhatsApp (o lo que elija el usuario en el menú del móvil): tu perfil o un restaurante.
// El enlace abre la app en el perfil (dondecomemos://persona/<alias>; en Expo Go, exp://…/--/persona/<alias>).
// ponytail: cuando haya web propia, cambiarlo por un enlace https (universal link) que funcione sin la app.
import * as Linking from 'expo-linking';
import { Share } from 'react-native';

export function compartirPerfil(alias: string): Promise<unknown> {
  const enlace = Linking.createURL(`/persona/${alias}`);
  return Share.share({ message: `¡Añádeme en ¿Dónde comemos?! Soy @${alias}: ${enlace}` });
}

export function compartirRestaurante(nombre: string, lat: number | null, lon: number | null): Promise<unknown> {
  const mapa = lat !== null && lon !== null
    ? `https://www.google.com/maps/search/?api=1&query=${lat},${lon}`
    : `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${nombre} Madrid`)}`;
  return Share.share({ message: `¿Vamos a ${nombre}? ${mapa}` });
}
