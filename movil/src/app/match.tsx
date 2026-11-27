// «Food match», copia de deslizar.pantalla + componentes/deslizar.*: «Volver», el título y la explicación; la pila de
// tarjetas 3:4 (fotos que se pasan tocando, con sus rayitas; abajo, sobre un degradado, nombre, «📍 localidad», datos
// y el porqué; un mapa pequeño en la esquina que se amplía), arrastrar a la derecha (♥, entra en tu lista) o a la
// izquierda (✕, no vuelve a salir) con los sellos «ME GUSTA» / «PASO», y al dar «me gusta», «✓ Añadido a tu lista»
// con los amigos que también lo tienen.
import { Image } from 'expo-image';
import { router } from 'expo-router';
import { useEffect, useLayoutEffect, useState } from 'react';
import {
  Animated, Modal, PanResponder, Pressable, StyleSheet, Text, useWindowDimensions, View,
} from 'react-native';
import Svg, { Defs, LinearGradient, Rect, Stop } from 'react-native-svg';

import MapView, { Marker } from '@/components/mapa';
import { Boton, Cargando, Info, Pantalla, Texto } from '@/components/ui';
import { api, CartaMatch, mensaje, Mazo } from '@/lib/api';
import { cogerMazo } from '@/lib/mazo';
import { LETRA, useColores } from '@/lib/tema';
import { olvidarVisitados } from '@/lib/visitados';

const UMBRAL_PX = 100;   // lo que hay que arrastrar para que cuente
const TOQUE_PX = 8;      // moverse menos al soltar = tocar la foto (pasa a la siguiente)
const ANADIDO_MS = 4000; // lo que dura «Añadido a tu lista»
const MAPA_MS = 400;     // el mapa pequeño se monta un poco después: montarlo a la vez que la tarjeta da tirones
const PRECARGAR = 4;     // tarjetas cuyas fotos se bajan antes de que salgan

const fotosDe = (t: CartaMatch) => (t.fotos.length ? t.fotos : t.foto ? [t.foto] : []);

/** app.tarjeta_deslizar: «Cocina · 20-30 € · ⭐ 4,5». */
function meta(t: CartaMatch): string {
  return [t.cocina, t.precio, t.nota !== null ? `⭐ ${t.nota.toFixed(1).replace('.', ',')}` : null]
    .filter((p) => p && p !== 'N/D').join(' · ');
}

function Degradado() {
  return (
    <Svg style={StyleSheet.absoluteFill} pointerEvents="none">
      <Defs>
        <LinearGradient id="dzinfo" x1="0" y1="1" x2="0" y2="0">
          <Stop offset="0" stopColor="#000" stopOpacity="0.82" />
          <Stop offset="0.55" stopColor="#000" stopOpacity="0.82" />
          <Stop offset="1" stopColor="#000" stopOpacity="0" />
        </LinearGradient>
      </Defs>
      <Rect width="100%" height="100%" fill="url(#dzinfo)" />
    </Svg>
  );
}

interface CartaProps {
  carta: CartaMatch;
  arriba?: boolean;
  si?: Animated.AnimatedInterpolation<number>;
  no?: Animated.AnimatedInterpolation<number>;
  conMapa?: boolean;
}

/** .dz-tarjeta: la foto (tocar el tercio izquierdo = la anterior; el resto = la siguiente), las rayitas, el mapa y la info. */
function Carta({ carta: r, arriba = false, si, no, conMapa = true }: CartaProps) {
  const c = useColores();
  const fotos = fotosDe(r);
  const [actual, setActual] = useState(0);
  const [mapaGrande, setMapaGrande] = useState(false);
  const [mapaListo, setMapaListo] = useState(false);
  const [ancho, setAncho] = useState(1);
  useEffect(() => {
    if (!arriba) return undefined;
    const t = setTimeout(() => setMapaListo(true), MAPA_MS);
    return () => clearTimeout(t);
  }, [arriba]);
  const hayMapa = conMapa && arriba && mapaListo && r.lat !== null && r.lon !== null;

  return (
    <View style={[estilos.tarjeta, { backgroundColor: c.fondo2, borderColor: c.borde }]} onLayout={(e) => setAncho(e.nativeEvent.layout.width)}>
      {fotos.length ? (
        <Pressable style={StyleSheet.absoluteFill} accessibilityLabel={fotos.length > 1 ? `Foto ${actual + 1} de ${fotos.length}` : r.nombre}
          onPress={(e) => fotos.length > 1 && setActual((actual + (e.nativeEvent.locationX < ancho / 3 ? -1 : 1) + fotos.length) % fotos.length)}>
          <Image source={fotos[actual]} style={StyleSheet.absoluteFill} contentFit="cover" transition={120} />
        </Pressable>
      ) : (
        <View style={[StyleSheet.absoluteFill, { alignItems: 'center', justifyContent: 'center', backgroundColor: c.primario, opacity: 0.85 }]}>
          <Text style={{ fontFamily: LETRA.negrita, fontSize: 96, color: c.fondo }}>{(r.nombre.trim()[0] ?? '?').toUpperCase()}</Text>
        </View>
      )}
      {fotos.length > 1 && !mapaGrande ? (
        <View pointerEvents="none" style={estilos.barras}>
          {fotos.map((f, i) => <View key={f} style={[estilos.barra, { backgroundColor: i === actual ? '#FFFFFF' : 'rgba(255,255,255,0.45)' }]} />)}
        </View>
      ) : null}
      {hayMapa ? (
        <View style={mapaGrande ? [StyleSheet.absoluteFill, { bottom: 56 }] : estilos.mapa}>
          <MapView style={{ flex: 1 }} scrollEnabled={mapaGrande} zoomEnabled={mapaGrande} pitchEnabled={false} rotateEnabled={false}
            region={{ latitude: r.lat as number, longitude: r.lon as number, latitudeDelta: mapaGrande ? 0.006 : 0.03, longitudeDelta: mapaGrande ? 0.006 : 0.03 }}>
            <Marker coordinate={{ latitude: r.lat as number, longitude: r.lon as number }} pinColor="#DC2626" />
          </MapView>
          {mapaGrande ? (
            <Pressable accessibilityRole="button" accessibilityLabel="Cerrar el mapa" onPress={() => setMapaGrande(false)} style={estilos.cerrarMapa}>
              <Text style={{ color: '#fff', fontFamily: LETRA.negrita, fontSize: 18 }}>✕</Text>
            </Pressable>
          ) : (
            <Pressable accessibilityRole="button" accessibilityLabel="Ver el mapa en grande" style={StyleSheet.absoluteFill}
              onPress={() => setMapaGrande(true)} />
          )}
        </View>
      ) : null}
      <View pointerEvents="none" style={[estilos.info, mapaGrande && { height: 56, paddingTop: 0, paddingBottom: 0, justifyContent: 'center', backgroundColor: 'rgba(0,0,0,0.82)' }]}>
        {mapaGrande ? null : <Degradado />}
        <Text style={[estilos.nombre, mapaGrande && { fontSize: 17.25 }]} numberOfLines={mapaGrande ? 1 : undefined}>{r.nombre}</Text>
        {!mapaGrande && r.localidad ? <Text style={estilos.localidad}>{`📍 ${r.localidad}`}</Text> : null}
        {!mapaGrande && meta(r) ? <Text style={estilos.meta}>{meta(r)}</Text> : null}
        {!mapaGrande && r.motivo ? <Text style={estilos.motivo}>{r.motivo}</Text> : null}
      </View>
      {si && no ? (
        <>
          <Animated.Text pointerEvents="none" style={[estilos.sello, estilos.selloSi, { opacity: si }]}>ME GUSTA</Animated.Text>
          <Animated.Text pointerEvents="none" style={[estilos.sello, estilos.selloNo, { opacity: no }]}>PASO</Animated.Text>
        </>
      ) : null}
    </View>
  );
}

/** .dz-anadido: la tarjeta, «✓ Añadido a tu lista» y, si algún amigo también lo tiene, «Tienes el mismo gusto que». */
function Anadido({ carta, alCerrar }: { carta: CartaMatch; alCerrar: () => void }) {
  const c = useColores();
  const { height } = useWindowDimensions();
  const [tiempo] = useState(() => new Animated.Value(1));
  useEffect(() => {
    Animated.timing(tiempo, { toValue: 0, duration: ANADIDO_MS, useNativeDriver: true }).start();
    const t = setTimeout(alCerrar, ANADIDO_MS);
    return () => clearTimeout(t);
  }, [tiempo, alCerrar]);
  const gusto = carta.gusto;
  return (
    <Modal visible transparent animationType="fade" onRequestClose={alCerrar}>
      <Pressable accessibilityRole="button" accessibilityLabel="Añadido a tu lista. Cerrar" onPress={alCerrar}
        style={{ flex: 1, padding: 16, alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(0,0,0,0.6)' }}>
        <View style={{ width: '100%', maxWidth: 340, alignItems: 'center', gap: 12 }}>
          <View style={{ width: '100%', aspectRatio: 3 / 4, maxHeight: height * 0.52 }}>
            <Carta carta={carta} conMapa={false} />
          </View>
          <Text style={estilos.ok}>✓ Añadido a tu lista</Text>
          {gusto?.perfiles.length ? (
            <View style={[estilos.gusto, { backgroundColor: c.fondo }]}>
              <Text style={{ fontFamily: LETRA.negrita, fontSize: 15.75, color: c.texto, textAlign: 'center' }}>
                <Text style={{ color: '#E11D48' }}>❤</Text> Tienes el mismo gusto que
              </Text>
              <View style={{ flexDirection: 'row', justifyContent: 'center', alignItems: 'flex-start', gap: 16, marginTop: 10 }}>
                {gusto.perfiles.map((p) => (
                  <View key={p.nombre} style={{ alignItems: 'center', gap: 4, maxWidth: 88 }}>
                    <View style={[estilos.avatar, { backgroundColor: p.color, borderColor: c.fondo }]}>
                      <Text style={{ fontFamily: LETRA.negrita, fontSize: 24, color: '#fff' }}>{p.inicial}</Text>
                      {p.foto ? <Image source={p.foto} style={StyleSheet.absoluteFill} contentFit="cover" /> : null}
                    </View>
                    <Text style={{ fontFamily: LETRA.normal, fontSize: 12, color: c.texto }} numberOfLines={1}>{p.nombre}</Text>
                  </View>
                ))}
                {gusto.mas > 0 ? (
                  <View style={[estilos.avatar, { backgroundColor: c.fondo2, borderColor: c.fondo }]} accessibilityLabel={`y ${gusto.mas} más`}>
                    <Text style={{ fontFamily: LETRA.negrita, fontSize: 18, color: c.texto }}>{`+${gusto.mas}`}</Text>
                  </View>
                ) : null}
              </View>
            </View>
          ) : null}
          <Animated.View style={{ width: '60%', height: 4, borderRadius: 2, backgroundColor: 'rgba(255,255,255,0.85)', transform: [{ scaleX: tiempo }] }} />
        </View>
      </Pressable>
    </Modal>
  );
}

export default function FoodMatch() {
  const c = useColores();
  const { height } = useWindowDimensions();
  const [cartas, setCartas] = useState<CartaMatch[] | null>(null);
  const [fin, setFin] = useState(false);
  const [conZona, setConZona] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [anadida, setAnadida] = useState<CartaMatch | null>(null);
  const [decididas, setDecididas] = useState<number[]>([]);   // ya deslizadas aunque la API aún no haya contestado
  const [pos] = useState(() => new Animated.Value(0));

  function aplicar(m: Mazo, yaDecididas: number[]) {
    setCartas(m.tarjetas.filter((t) => !yaDecididas.includes(t.id)));
    setFin(m.fin);
    setConZona(m.con_zona);
  }

  useEffect(() => {
    cogerMazo().then((m) => aplicar(m, [])).catch((e: unknown) => setError(mensaje(e)));
  }, []);

  // las fotos de las próximas tarjetas, ya bajadas cuando les toque
  const proximas = (cartas ?? []).slice(0, PRECARGAR).flatMap(fotosDe).join(' ');
  useEffect(() => { if (proximas) Image.prefetch(proximas.split(' ')); }, [proximas]);

  // la nueva de arriba (la que estaba debajo, sin volver a montarse) empieza en el centro, antes de pintarse
  const idArriba = cartas?.[0]?.id;
  useLayoutEffect(() => { pos.setValue(0); }, [idArriba, pos]);

  async function decidir(gusta: boolean) {
    const primera = cartas?.[0];
    if (!primera) return;
    const ahora = [...decididas, primera.id];
    setDecididas(ahora);
    setCartas((antes) => (antes ?? []).filter((t) => t.id !== primera.id));
    if (gusta) setAnadida(primera);
    try {
      aplicar(await api<Mazo>('POST', '/deslizar', { id: primera.id, gusta }), ahora);
      if (gusta) olvidarVisitados();
    } catch {
      setError('No se ha podido guardar ahora mismo. Prueba en un momento.');
    }
  }

  function irse(gusta: boolean) {
    Animated.timing(pos, { toValue: gusta ? 600 : -600, duration: 250, useNativeDriver: true }).start(() => decidir(gusta));
  }

  const [arrastrando, setArrastrando] = useState(false);
  const volver = () => Animated.spring(pos, { toValue: 0, useNativeDriver: true }).start();   // vuelve a su sitio
  const arrastre = PanResponder.create({
    onStartShouldSetPanResponder: () => false,
    onMoveShouldSetPanResponder: (_, g) => Math.abs(g.dx) > TOQUE_PX && Math.abs(g.dx) > Math.abs(g.dy),
    onPanResponderGrant: () => setArrastrando(true),
    onPanResponderMove: (_, g) => pos.setValue(g.dx),
    onPanResponderTerminationRequest: () => false,   // una vez cogida, el scroll de la pantalla no se la lleva
    onPanResponderRelease: (_, g) => {
      setArrastrando(false);
      if (Math.abs(g.dx) >= UMBRAL_PX) irse(g.dx > 0);
      else volver();
    },
    onPanResponderTerminate: () => { setArrastrando(false); volver(); },
  });
  const giro = pos.interpolate({ inputRange: [-180, 0, 180], outputRange: ['-10deg', '0deg', '10deg'] });
  const si = pos.interpolate({ inputRange: [0, UMBRAL_PX], outputRange: [0, 1], extrapolate: 'clamp' });
  const no = pos.interpolate({ inputRange: [-UMBRAL_PX, 0], outputRange: [1, 0], extrapolate: 'clamp' });

  const primera = cartas?.[0];
  const segunda = cartas?.[1];
  const altoMazo = Math.max(280, height - 440);
  return (
    <View style={{ flex: 1, backgroundColor: c.fondo }}>
      <Pantalla desplazable={!arrastrando}>
        <Boton texto="Volver" tipo="texto" icono="arrow_back" ancho="contenido" alPulsar={() => router.back()} />
        <Texto tipo="subtitulo">Food match</Texto>
        <Texto tipo="suave">
          {`Desliza a la derecha lo que te guste (se añade a tu lista) y a la izquierda lo que no. ${conZona
            ? 'Salen sitios de tu zona y de Madrid.'
            : 'Salen sitios de Madrid: pon «De dónde eres» en tus ajustes para ver también los de tu zona.'}`}
        </Texto>
        {error ? <Info tipo="error">{error}</Info> : null}
        {cartas === null && !error ? <Cargando /> : null}
        {cartas !== null && !primera ? (
          fin ? <Info>¡Has visto todos los restaurantes que tenemos! Cada día se analizan sitios nuevos: vuelve en unos días.</Info> : <Cargando />
        ) : null}
        {primera ? (
          <View style={{ alignItems: 'center', gap: 14 }}>
            <View style={{ width: '100%', maxWidth: 420, aspectRatio: 3 / 4, maxHeight: altoMazo, minHeight: 280 }}>
              {/* las dos con su id como clave y en el mismo sitio: la de debajo, al subir, no se vuelve a montar */}
              {(segunda ? [segunda, primera] : [primera]).map((t) => (t === primera ? (
                <Animated.View key={t.id} {...arrastre.panHandlers}
                  style={[StyleSheet.absoluteFill, { transform: [{ translateX: pos }, { rotate: giro }] }]}>
                  <Carta carta={t} arriba si={si} no={no} />
                </Animated.View>
              ) : (
                <Animated.View key={t.id} style={[StyleSheet.absoluteFill, { transform: [{ scale: 0.96 }, { translateY: 10 }] }]}>
                  <Carta carta={t} />
                </Animated.View>
              )))}
            </View>
            <View style={{ flexDirection: 'row', gap: 28 }}>
              <Pressable accessibilityRole="button" accessibilityLabel="No me gusta" onPress={() => irse(false)}
                style={({ pressed }) => [estilos.botonRedondo, { backgroundColor: c.fondo2, borderColor: '#DC2626', transform: [{ scale: pressed ? 0.92 : 1 }] }]}>
                <Text style={{ fontSize: 28, fontFamily: LETRA.negrita, color: '#DC2626' }}>✕</Text>
              </Pressable>
              <Pressable accessibilityRole="button" accessibilityLabel="Me gusta: añadir a mi lista" onPress={() => irse(true)}
                style={({ pressed }) => [estilos.botonRedondo, { backgroundColor: c.fondo2, borderColor: '#16A34A', transform: [{ scale: pressed ? 0.92 : 1 }] }]}>
                <Text style={{ fontSize: 28, fontFamily: LETRA.negrita, color: '#16A34A' }}>♥</Text>
              </Pressable>
            </View>
          </View>
        ) : null}
      </Pantalla>
      {anadida ? <Anadido carta={anadida} alCerrar={() => setAnadida(null)} /> : null}
    </View>
  );
}

const estilos = StyleSheet.create({
  tarjeta: {
    flex: 1, borderRadius: 20, overflow: 'hidden', borderWidth: 1,
    shadowColor: '#000', shadowOpacity: 0.14, shadowRadius: 12, shadowOffset: { width: 0, height: 8 }, elevation: 6,
  },
  barras: { position: 'absolute', zIndex: 1, top: 8, left: 10, right: 10, flexDirection: 'row', gap: 4 },
  barra: { flex: 1, height: 4, borderRadius: 2 },
  mapa: {
    position: 'absolute', zIndex: 1, top: 22, right: 12, width: 96, height: 96, borderRadius: 14, overflow: 'hidden',
    borderWidth: 2, borderColor: '#FFFFFF',
  },
  cerrarMapa: {
    position: 'absolute', top: 12, right: 12, width: 36, height: 36, borderRadius: 18, alignItems: 'center',
    justifyContent: 'center', backgroundColor: 'rgba(0,0,0,0.6)',
  },
  info: { position: 'absolute', left: 0, right: 0, bottom: 0, paddingTop: 48, paddingHorizontal: 18, paddingBottom: 16, gap: 4 },
  nombre: { fontFamily: LETRA.titulo, fontSize: 24, lineHeight: 27.6, color: '#FFFFFF' },
  localidad: { fontFamily: LETRA.semi, fontSize: 15, color: '#FFFFFF' },
  meta: { fontFamily: LETRA.normal, fontSize: 14.25, color: '#FFFFFF', opacity: 0.92 },
  motivo: {
    alignSelf: 'flex-start', marginTop: 4, paddingVertical: 3, paddingHorizontal: 10, borderRadius: 999, overflow: 'hidden',
    fontFamily: LETRA.normal, fontSize: 12.3, color: '#FFFFFF', backgroundColor: 'rgba(255, 255, 255, 0.18)',
  },
  sello: {
    position: 'absolute', zIndex: 3, top: 26, paddingVertical: 4, paddingHorizontal: 12, borderWidth: 3, borderRadius: 10,
    fontFamily: LETRA.negrita, fontSize: 22.5, letterSpacing: 1.35, backgroundColor: 'rgba(255, 255, 255, 0.85)', overflow: 'hidden',
  },
  selloSi: { left: 18, color: '#15803D', borderColor: '#15803D', transform: [{ rotate: '-12deg' }] },
  selloNo: { right: 18, color: '#B91C1C', borderColor: '#B91C1C', transform: [{ rotate: '12deg' }] },
  botonRedondo: {
    width: 64, height: 64, borderRadius: 32, borderWidth: 2, alignItems: 'center', justifyContent: 'center',
    shadowColor: '#000', shadowOpacity: 0.12, shadowRadius: 6, shadowOffset: { width: 0, height: 4 }, elevation: 3,
  },
  ok: {
    paddingVertical: 6, paddingHorizontal: 16, borderRadius: 999, overflow: 'hidden', fontFamily: LETRA.negrita, color: '#FFFFFF',
    backgroundColor: '#16A34A',
  },
  gusto: {
    width: '100%', paddingTop: 12, paddingHorizontal: 16, paddingBottom: 14, borderRadius: 18,
    shadowColor: '#000', shadowOpacity: 0.25, shadowRadius: 12, shadowOffset: { width: 0, height: 8 }, elevation: 8,
  },
  avatar: {
    width: 56, height: 56, borderRadius: 28, overflow: 'hidden', alignItems: 'center', justifyContent: 'center',
    borderWidth: 3, shadowColor: '#E11D48', shadowOpacity: 1, shadowRadius: 0, shadowOffset: { width: 0, height: 0 },
  },
});
