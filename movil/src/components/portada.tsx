// La portada de Streamlit (app.mostrar_portada + componentes/portada.css): cinta de fotos redondas que se desliza,
// el «momento» en mayúsculas terracota, el título «¿Dónde comemos?» y el subtítulo.
import { Image } from 'expo-image';
import { useEffect, useState } from 'react';
import { Animated, Easing, StyleSheet, Text, View } from 'react-native';
import Svg, { Defs, LinearGradient, Rect, Stop } from 'react-native-svg';

import { Texto } from '@/components/ui';
import { ESPACIO, LETRA, useColores } from '@/lib/tema';

const LADO = 64;
const HUECO = 10;
const VUELTA_MS = 55000;

/** El difuminado de los bordes (mask-image de portada.css: transparente → opaco en el 12 % de cada lado). */
function Bordes() {
  const c = useColores();
  return (
    <Svg style={StyleSheet.absoluteFill} pointerEvents="none">
      <Defs>
        <LinearGradient id="bordes" x1="0" y1="0" x2="1" y2="0">
          <Stop offset="0" stopColor={c.fondo} stopOpacity="1" />
          <Stop offset="0.12" stopColor={c.fondo} stopOpacity="0" />
          <Stop offset="0.88" stopColor={c.fondo} stopOpacity="0" />
          <Stop offset="1" stopColor={c.fondo} stopOpacity="1" />
        </LinearGradient>
      </Defs>
      <Rect width="100%" height="100%" fill="url(#bordes)" />
    </Svg>
  );
}

function Cinta({ fotos, sinMargen = false }: { fotos: string[]; sinMargen?: boolean }) {
  const [x] = useState(() => new Animated.Value(0));
  const mitad = fotos.length * (LADO + HUECO);
  useEffect(() => {
    if (!mitad) return;
    const vuelta = Animated.loop(Animated.timing(x, {
      toValue: -mitad, duration: VUELTA_MS, easing: Easing.linear, useNativeDriver: true,
    }));
    vuelta.start();
    return () => vuelta.stop();
  }, [x, mitad]);
  // La lista va dos veces seguidas: al desplazarse la mitad, vuelve al principio sin salto.
  return (
    <View style={[estilos.cinta, sinMargen && { marginBottom: 0 }]} accessibilityElementsHidden importantForAccessibility="no-hide-descendants">
      <Animated.View style={[estilos.pista, { transform: [{ translateX: x }] }]}>
        {[...fotos, ...fotos].map((f, i) => (
          <Image key={i} source={f} contentFit="cover"
            style={[estilos.foto, i % 2 === 1 && { transform: [{ translateY: 10 }] }]} />
        ))}
      </Animated.View>
      <Bordes />
    </View>
  );
}

interface Props {
  fotos: string[];
  momento?: string;
  subtitulo?: string;
  soloCinta?: boolean;   // Buscar: solo la cinta, y lo de debajo sube (portada.css: .solo-cinta)
}

export function Portada({ fotos, momento = '', subtitulo = '', soloCinta = false }: Props) {
  const c = useColores();
  if (soloCinta) {
    return <View style={{ marginBottom: -26.25 }}>{fotos.length ? <Cinta fotos={fotos} sinMargen /> : null}</View>;
  }
  return (
    <View>
      {fotos.length ? <Cinta fotos={fotos} /> : null}
      <Text style={[estilos.momento, { color: c.primario }]}>{momento.toUpperCase()}</Text>
      <Texto tipo="titulo" style={estilos.titulo}>¿Dónde comemos?</Texto>
      <Texto style={{ opacity: 0.72 }}>{subtitulo}</Texto>
    </View>
  );
}

const estilos = StyleSheet.create({
  // 64 + 4 + 4 de alto, como en la web: las fotos bajadas 10 px quedan cortadas por abajo
  cinta: { overflow: 'hidden', marginHorizontal: -ESPACIO, marginBottom: 18, paddingVertical: 4, height: LADO + 8 },
  pista: { flexDirection: 'row', gap: HUECO },
  foto: {
    width: LADO, height: LADO, borderRadius: LADO / 2,
    shadowColor: '#1F1A14', shadowOpacity: 0.18, shadowRadius: 4, shadowOffset: { width: 0, height: 2 },
  },
  momento: { fontFamily: LETRA.semi, fontSize: 12.75, letterSpacing: 0.51, lineHeight: 20.4 },
  titulo: { marginTop: 2, marginBottom: 6 },
});
