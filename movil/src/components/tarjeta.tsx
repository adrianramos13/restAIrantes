// Tarjeta de restaurante (listas, resultados, «Lo mejor de la semana»). Al tocarla abre su ficha.
import { Image } from 'expo-image';
import { router } from 'expo-router';
import { Pressable, StyleSheet, View } from 'react-native';

import { Texto } from '@/components/ui';
import { Tarjeta } from '@/lib/api';
import { RADIO, useColores } from '@/lib/tema';

export function formatoNota(nota: number | null): string {
  return nota === null ? 'Sin nota' : `★ ${nota.toFixed(1).replace('.', ',')}`;
}

interface Props {
  tarjeta: Tarjeta;
  transporte?: 'En coche' | 'A pie';
  plato?: string;
  visitado?: boolean;
}

export function TarjetaRestaurante({ tarjeta: t, transporte, plato, visitado }: Props) {
  const c = useColores();
  const meta = [t.precio ?? 'Precio ?', `${formatoNota(t.nota)}${t.resenas ? ` (${t.resenas})` : ''}`];
  if (t.minutos !== undefined) meta.push(`${transporte === 'A pie' ? '🚶' : '🚗'} ${t.minutos}'`);
  return (
    <Pressable
      accessibilityRole="button"
      onPress={() => router.push({ pathname: '/restaurante/[id]', params: { id: String(t.id), plato: plato ?? '' } })}
      style={({ pressed }) => [estilos.tarjeta, { backgroundColor: c.fondo2, borderColor: c.borde, opacity: pressed ? 0.85 : 1 }]}>
      <Image source={t.foto ?? undefined} style={[estilos.foto, { backgroundColor: c.borde }]} contentFit="cover" transition={150} />
      <View style={{ flex: 1, gap: 3 }}>
        <Texto tipo="subtitulo" lineas={1} style={{ fontSize: 16 }}>
          {t.nombre}
        </Texto>
        <Texto tipo="suave" lineas={1}>
          {t.cocina}
        </Texto>
        <Texto tipo="suave" lineas={1}>
          {meta.join(' · ')}
        </Texto>
        {t.cerrado ? <Texto tipo="error">{t.cerrado}</Texto> : null}
        {visitado ? <Texto tipo="suave">✓ Has ido</Texto> : null}
        {t.visita ? (
          <Texto tipo="suave" lineas={2}>
            {[t.visita.quien, t.visita.nota !== null ? formatoNota(t.visita.nota) : null, t.visita.comentario]
              .filter(Boolean)
              .join(' · ')}
          </Texto>
        ) : null}
      </View>
    </Pressable>
  );
}

const estilos = StyleSheet.create({
  tarjeta: { flexDirection: 'row', gap: 12, padding: 10, borderRadius: RADIO, borderWidth: 1, alignItems: 'center' },
  foto: { width: 76, height: 76, borderRadius: RADIO - 4 },
});
