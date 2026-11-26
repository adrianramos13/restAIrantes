// El mapa de la web (componentes/mapa.*): tú como punto azul y cada sitio como su foto redonda con borde blanco,
// punta y el número de su posición (el 1.º en dorado). Tocar una foto abre su ficha. Alto: 60 % de la pantalla
// (mín. 300, máx. 560), con borde y esquinas redondeadas.
import { Image } from 'expo-image';
import { useRef } from 'react';
import { Text, useWindowDimensions, View } from 'react-native';

import MapView, { Marker } from '@/components/mapa';
import { LETRA, RADIO, useColores } from '@/lib/tema';

export interface PuntoMapa {
  id: number | string;
  n?: number;
  nombre: string;
  lat: number;
  lon: number;
  foto: string | null;
  analizado?: boolean;   // Descubrir: con ficha completa (borde verde)
}

const MADRID = { latitude: 40.4168, longitude: -3.7038 };

function Pin({ p }: { p: PuntoMapa }) {
  const c = useColores();
  const borde = p.analizado ? '#16A34A' : '#FFFFFF';
  const top = p.n === 1 && p.analizado === undefined;
  return (
    <View style={{ width: 46, height: 56 }}>
      <View style={{ position: 'absolute', left: 0, top: 0, width: 40, height: 40, borderRadius: 20, borderWidth: 3,
        borderColor: borde, overflow: 'hidden', backgroundColor: '#E6E6EA', alignItems: 'center', justifyContent: 'center',
        shadowColor: '#000', shadowOpacity: 0.4, shadowRadius: 2.5, shadowOffset: { width: 0, height: 1 }, elevation: 4 }}>
        {p.foto ? <Image source={p.foto} style={{ width: '100%', height: '100%' }} contentFit="cover" /> : <Text style={{ fontSize: 20 }}>🍽️</Text>}
      </View>
      <View style={{ position: 'absolute', left: 12, top: 38, width: 0, height: 0, borderLeftWidth: 8, borderRightWidth: 8,
        borderTopWidth: 12, borderLeftColor: 'transparent', borderRightColor: 'transparent', borderTopColor: borde }} />
      {p.n ? (
        <View style={{ position: 'absolute', left: 27, top: -7, minWidth: 20, height: 20, paddingHorizontal: 4, borderRadius: 10,
          backgroundColor: top ? '#F5B301' : c.primario, borderWidth: 2, borderColor: '#FFFFFF', alignItems: 'center', justifyContent: 'center' }}>
          <Text style={{ fontFamily: LETRA.negrita, fontSize: 11, color: top ? '#3B2A00' : c.fondo }}>{p.n}</Text>
        </View>
      ) : null}
    </View>
  );
}

function Yo() {
  return (
    <View style={{ width: 18, height: 18, borderRadius: 9, borderWidth: 3, borderColor: '#FFFFFF', backgroundColor: '#1A73E8',
      shadowColor: '#000', shadowOpacity: 0.45, shadowRadius: 1.5, elevation: 3 }} />
  );
}

interface Props {
  usuario?: { lat: number; lon: number } | null;
  puntos: PuntoMapa[];
  alTocar: (p: PuntoMapa) => void;
}

export function MapaFotos({ usuario, puntos, alTocar }: Props) {
  const c = useColores();
  const { height } = useWindowDimensions();
  const mapa = useRef<MapView>(null);
  const centro = usuario ? { latitude: usuario.lat, longitude: usuario.lon } : MADRID;
  const coordenadas = [...puntos.map((p) => ({ latitude: p.lat, longitude: p.lon })), ...(usuario ? [centro] : [])];
  return (
    <View style={{ height: Math.min(560, Math.max(300, height * 0.6)), borderRadius: RADIO, overflow: 'hidden', borderWidth: 1, borderColor: c.borde }}>
      <MapView
        ref={mapa}
        style={{ flex: 1 }}
        initialRegion={{ ...centro, latitudeDelta: usuario ? 0.01 : 0.15, longitudeDelta: usuario ? 0.01 : 0.15 }}
        onMapReady={() => {
          // como fitBounds de la web: que se vean todos, sin acercarse demasiado
          if (coordenadas.length > 1) {
            mapa.current?.fitToCoordinates(coordenadas, { edgePadding: { top: 75, right: 40, bottom: 35, left: 40 }, animated: false });
          }
        }}>
        {usuario ? <Marker coordinate={centro} anchor={{ x: 0.5, y: 0.5 }} tracksViewChanges={false}><Yo /></Marker> : null}
        {puntos.map((p) => (
          <Marker key={p.id} coordinate={{ latitude: p.lat, longitude: p.lon }} anchor={{ x: 0.43, y: 1 }}
            accessibilityLabel={`${p.n ? `${p.n}. ` : ''}${p.nombre}`} onPress={() => alTocar(p)}>
            <Pin p={p} />
          </Marker>
        ))}
      </MapView>
    </View>
  );
}
