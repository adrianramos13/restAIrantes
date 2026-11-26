// «Food match»: restaurantes que no conoces, de uno en uno. Desliza a la derecha (o ♥) lo que te guste: entra en
// tu lista. A la izquierda (o ✕): no vuelve a salir. El orden lo decide la API con tus gustos (api/social.py).
import { Image } from 'expo-image';
import * as Location from 'expo-location';
import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { Animated, PanResponder, Pressable, StyleSheet, useWindowDimensions, View } from 'react-native';

import { Avatar } from '@/components/persona';
import { formatoNota } from '@/components/tarjeta';
import { Boton, Cargando, Texto } from '@/components/ui';
import { api, CartaMatch, mensaje, Mazo } from '@/lib/api';
import { ESPACIO, RADIO, useColores } from '@/lib/tema';

const UMBRAL = 110;   // px que hay que arrastrar para que cuente

async function ubicacionSinPreguntar(): Promise<{ lat: number; lon: number } | undefined> {
  try {   // solo si ya diste permiso (en Comer hoy); si no, salen sitios de Madrid
    if ((await Location.getForegroundPermissionsAsync()).status !== 'granted') return undefined;
    const pos = await Location.getLastKnownPositionAsync();
    return pos ? { lat: pos.coords.latitude, lon: pos.coords.longitude } : undefined;
  } catch {
    return undefined;
  }
}

function Carta({ carta: t }: { carta: CartaMatch }) {
  const { height } = useWindowDimensions();
  const foto = t.fotos[0] ?? t.foto;
  return (
    <Pressable onPress={() => router.push({ pathname: '/restaurante/[id]', params: { id: String(t.id) } })}
      style={[estilos.carta, { height: height * 0.62 }]}>
      <Image source={foto ?? undefined} style={StyleSheet.absoluteFill} contentFit="cover" transition={150} />
      <View style={estilos.velo}>
        <Texto tipo="titulo" style={estilos.blanco} lineas={2}>{t.nombre}</Texto>
        <Texto style={estilos.blanco} lineas={1}>
          {[t.cocina, t.precio, t.nota !== null ? formatoNota(t.nota) : null].filter(Boolean).join(' · ')}
        </Texto>
        {t.localidad ? <Texto style={estilos.blanco}>{`📍 ${t.localidad}`}</Texto> : null}
        {t.motivo ? <Texto style={estilos.blanco} lineas={2}>{t.motivo}</Texto> : null}
        {t.gusto ? (
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
            {t.gusto.perfiles.map((p) => <Avatar key={p.nombre} persona={p} tam={24} />)}
            <Texto style={[estilos.blanco, { flex: 1 }]} lineas={1}>
              {`También en la lista de ${t.gusto.perfiles.map((p) => p.nombre).join(', ')}${t.gusto.mas ? ` y ${t.gusto.mas} más` : ''}`}
            </Texto>
          </View>
        ) : null}
      </View>
    </Pressable>
  );
}

export default function FoodMatch() {
  const c = useColores();
  const [cartas, setCartas] = useState<CartaMatch[] | null>(null);
  const [fin, setFin] = useState(false);
  const [conZona, setConZona] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [decididas, setDecididas] = useState<number[]>([]);   // ya deslizadas aunque la API aún no haya contestado
  const [pos] = useState(() => new Animated.ValueXY());

  // ponytail: si dos respuestas llegan desordenadas, una carta ya deslizada podría volver; la API ignora la decisión repetida
  function aplicar(m: Mazo, yaDecididas: number[]) {
    setCartas(m.tarjetas.filter((t) => !yaDecididas.includes(t.id)));
    setFin(m.fin);
    setConZona(m.con_zona);
  }

  useEffect(() => {
    ubicacionSinPreguntar()
      .then((u) => api<Mazo>('GET', '/deslizar', undefined, u))
      .then((m) => aplicar(m, []))
      .catch((e: unknown) => setError(mensaje(e)));
  }, []);

  async function decidir(gusta: boolean) {
    const primera = cartas?.[0];
    if (!primera) return;
    const ahora = [...decididas, primera.id];
    setDecididas(ahora);
    setCartas((antes) => (antes ?? []).filter((t) => t.id !== primera.id));
    setAviso(gusta ? `${primera.nombre}: añadido a tu lista` : null);
    try {
      aplicar(await api<Mazo>('POST', '/deslizar', { id: primera.id, gusta }), ahora);
    } catch (e) {
      setError(mensaje(e));
    }
  }

  const arrastre = PanResponder.create({
      onMoveShouldSetPanResponder: (_, g) => Math.abs(g.dx) > 8,
      onPanResponderMove: Animated.event([null, { dx: pos.x, dy: pos.y }], { useNativeDriver: false }),
      onPanResponderRelease: (_, g) => {
        if (Math.abs(g.dx) < UMBRAL) {
          Animated.spring(pos, { toValue: { x: 0, y: 0 }, useNativeDriver: false }).start();
          return;
        }
        Animated.timing(pos, { toValue: { x: Math.sign(g.dx) * 600, y: g.dy }, duration: 180, useNativeDriver: false })
          .start(() => {
            pos.setValue({ x: 0, y: 0 });
            decidir(g.dx > 0);
          });
      },
  });
  const giro = pos.x.interpolate({ inputRange: [-300, 0, 300], outputRange: ['-12deg', '0deg', '12deg'] });

  const primera = cartas?.[0];
  return (
    <View style={{ flex: 1, backgroundColor: c.fondo, padding: ESPACIO, gap: 14 }}>
      {!conZona ? <Texto tipo="suave">Salen sitios de Madrid: pon «De dónde eres» en Ajustes para ver también los de tu zona.</Texto> : null}
      {error ? <Texto tipo="error">{error}</Texto> : null}
      {cartas === null && !error ? <Cargando /> : null}
      {cartas !== null && !primera ? (
        fin ? <Texto>¡Has visto todos los restaurantes que tenemos! Cada día se analizan sitios nuevos: vuelve en unos días.</Texto> : <Cargando />
      ) : null}
      {primera ? (
        <>
          <View>
            {cartas?.[1] ? <View style={StyleSheet.absoluteFill}><Carta carta={cartas[1]} /></View> : null}
            <Animated.View {...arrastre.panHandlers}
              style={{ transform: [{ translateX: pos.x }, { translateY: pos.y }, { rotate: giro }] }}>
              <Carta key={primera.id} carta={primera} />
            </Animated.View>
          </View>
          <View style={{ flexDirection: 'row', gap: 12 }}>
            <View style={{ flex: 1 }}><Boton texto="✕  No" tipo="secundario" alPulsar={() => decidir(false)} /></View>
            <View style={{ flex: 1 }}><Boton texto="♥  Me gusta" alPulsar={() => decidir(true)} /></View>
          </View>
        </>
      ) : null}
      {aviso ? <Texto tipo="suave" style={{ textAlign: 'center' }}>{aviso}</Texto> : null}
    </View>
  );
}

const estilos = StyleSheet.create({
  carta: { borderRadius: RADIO * 1.5, overflow: 'hidden', justifyContent: 'flex-end', backgroundColor: '#3A332B' },
  velo: { padding: ESPACIO, gap: 4, backgroundColor: 'rgba(0,0,0,0.45)' },
  blanco: { color: '#fff' },
});
