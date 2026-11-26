// La nota de «He ido» (componentes/estrellas.*): cinco estrellas grandes grises con las doradas encima hasta la
// nota. Se toca donde se quiera: la mitad izquierda de una estrella es media (de 0,5 a 5).
import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { useColores } from '@/lib/tema';

interface Props {
  valor: number | null;
  alCambiar: (valor: number) => void;
}

const TAM = 32;

export function Estrellas({ valor, alCambiar }: Props) {
  const c = useColores();
  const [ancho, setAncho] = useState(0);
  const desdeX = (x: number) => Math.min(5, Math.max(0.5, Math.ceil((x / Math.max(ancho, 1)) * 10) / 2));
  return (
    <View style={{ flexDirection: 'row' }}>
      <Pressable
        accessibilityRole="adjustable"
        accessibilityLabel="Tu nota"
        accessibilityValue={{ text: valor ? `${String(valor).replace('.', ',')} de 5 estrellas` : 'Sin nota' }}
        accessibilityActions={[{ name: 'increment' }, { name: 'decrement' }]}
        onAccessibilityAction={(e) => {
          const paso = e.nativeEvent.actionName === 'increment' ? 0.5 : -0.5;
          alCambiar(Math.min(5, Math.max(0.5, (valor ?? 0) + paso)));
        }}
        onLayout={(e) => setAncho(e.nativeEvent.layout.width)}
        onPress={(e) => alCambiar(desdeX(e.nativeEvent.locationX))}>
        <Text style={{ fontSize: TAM, lineHeight: TAM + 2, color: c.borde }}>★★★★★</Text>
        <View pointerEvents="none" style={[StyleSheet.absoluteFill, { width: `${((valor ?? 0) / 5) * 100}%`, overflow: 'hidden' }]}>
          <Text style={{ fontSize: TAM, lineHeight: TAM + 2, color: c.estrella, width: ancho || TAM * 5 }}>★★★★★</Text>
        </View>
      </Pressable>
    </View>
  );
}
