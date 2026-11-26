// Buscar → Descubrir: cualquier sitio de Madrid (tabla lugares, de Overture) por nombre, cerca de ti o en una zona,
// con su ficha rápida (nota de Google, cocina, foto), filtros (cocina, nota) y mapa. Los analizados abren su ficha
// completa; los demás, la del sitio. Arriba, «Personas» lleva a buscar amigos.
import { Image } from 'expo-image';
import * as Location from 'expo-location';
import { router } from 'expo-router';
import { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import MapView, { Callout, Marker } from 'react-native-maps';

import { CampoDireccion, Punto } from '@/components/direccion';
import { formatoNota } from '@/components/tarjeta';
import { Boton, Campo, Cargando, Chips, Pantalla, Texto } from '@/components/ui';
import { api, Lugar, mensaje } from '@/lib/api';
import { abrirLugar, ESTADOS } from '@/lib/lugares';
import { RADIO, useColores } from '@/lib/tema';

function FilaLugar({ lugar: l }: { lugar: Lugar }) {
  const c = useColores();
  return (
    <Pressable
      accessibilityRole="button"
      onPress={() => abrirLugar(l)}
      style={({ pressed }) => [estilos.fila, { backgroundColor: c.fondo2, borderColor: c.borde, opacity: pressed ? 0.85 : 1 }]}>
      <Image source={l.foto ?? undefined} style={[estilos.foto, { backgroundColor: c.borde }]} contentFit="cover" />
      <View style={{ flex: 1, gap: 2 }}>
        <Texto tipo="subtitulo" lineas={1} style={{ fontSize: 16 }}>
          {l.nombre}
        </Texto>
        <Texto tipo="suave" lineas={1}>
          {[l.cocina, l.nota !== null ? formatoNota(l.nota) : null].filter(Boolean).join(' · ')}
        </Texto>
        <Texto tipo="suave" lineas={1}>
          {[l.estado ? ESTADOS[l.estado] : null, l.ciudad].filter(Boolean).join(' · ')}
        </Texto>
      </View>
    </Pressable>
  );
}

export default function Buscar() {
  const [texto, setTexto] = useState('');
  const [cerca, setCerca] = useState<{ lat: number; lon: number } | null>(null);
  const [lugares, setLugares] = useState<Lugar[] | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [zona, setZona] = useState('');
  const [cocinas, setCocinas] = useState<string[]>([]);
  const [notaMin, setNotaMin] = useState(0);
  const [verMapa, setVerMapa] = useState(false);

  async function buscar(origen = cerca) {
    setError(null);
    setOcupado(true);
    try {
      const r = await api<{ lugares: Lugar[] }>('GET', '/lugares', undefined, {
        q: texto.trim(), lat: origen?.lat, lon: origen?.lon,
      });
      setLugares(r.lugares);
      setCocinas([]);
    } catch (e) {
      setError(mensaje(e));
    } finally {
      setOcupado(false);
    }
  }

  async function cercaDeMi() {
    setError(null);
    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== 'granted') throw new Error('Sin permiso para ver tu ubicación.');
      const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
      const origen = { lat: pos.coords.latitude, lon: pos.coords.longitude };
      setCerca(origen);
      await buscar(origen);
    } catch (e) {
      setError(mensaje(e));
    }
  }

  const visibles = (lugares ?? []).filter((l) =>
    (!cocinas.length || (l.cocina !== null && cocinas.includes(l.cocina))) && (l.nota ?? 0) >= notaMin);

  return (
    <Pantalla>
      <View style={{ flexDirection: 'row', alignItems: 'center' }}>
        <Texto tipo="titulo" style={{ flex: 1 }}>Descubrir</Texto>
        <Boton texto="👥 Personas" tipo="texto" alPulsar={() => router.push('/amigos')} />
      </View>
      <Campo placeholder="Nombre del sitio" value={texto} onChangeText={setTexto} returnKeyType="search"
        onSubmitEditing={() => buscar()} autoCorrect={false} />
      <View style={{ flexDirection: 'row', gap: 10 }}>
        <View style={{ flex: 1 }}>
          <Boton texto="Buscar" cargando={ocupado} alPulsar={() => buscar()} />
        </View>
        <View style={{ flex: 1 }}>
          <Boton texto={cerca ? '✓ Cerca de mí' : 'Cerca de mí'} tipo="secundario" alPulsar={cercaDeMi} />
        </View>
      </View>
      <CampoDireccion valor={zona} alEscribir={setZona} placeholder="O busca en una zona: barrio, calle o pueblo"
        alElegir={(p: Punto) => { setCerca({ lat: p.lat, lon: p.lon }); buscar({ lat: p.lat, lon: p.lon }); }} />
      {error ? <Texto tipo="error">{error}</Texto> : null}
      {ocupado && !lugares ? <Cargando /> : null}
      {lugares && !lugares.length ? <Texto tipo="suave">No hay sitios con ese nombre por aquí.</Texto> : null}
      {lugares?.length ? (
        <>
          <Chips opciones={[...new Set(lugares.map((l) => l.cocina).filter((x): x is string => !!x))].sort()}
            elegidas={cocinas} alElegir={(x) => setCocinas(cocinas.includes(x) ? cocinas.filter((y) => y !== x) : [...cocinas, x])} />
          <Chips opciones={[0, 4, 4.5] as const} elegidas={[notaMin]} alElegir={setNotaMin}
            etiqueta={(n) => (n ? `★ ${String(n).replace('.', ',')}+` : 'Cualquier nota')} />
          <Chips opciones={['lista', 'mapa'] as const} elegidas={[verMapa ? 'mapa' : 'lista']}
            alElegir={(x) => setVerMapa(x === 'mapa')} etiqueta={(x) => (x === 'lista' ? 'Lista' : 'Mapa')} />
        </>
      ) : null}
      {visibles.length && verMapa ? (
        <MapView style={{ height: 420, borderRadius: RADIO }} showsUserLocation
          initialRegion={{ latitude: visibles[0].lat, longitude: visibles[0].lon, latitudeDelta: 0.03, longitudeDelta: 0.03 }}>
          {visibles.map((l) => (
            <Marker key={l.id} coordinate={{ latitude: l.lat, longitude: l.lon }}>
              <Callout onPress={() => abrirLugar(l)}>
                <Texto>{l.nombre}</Texto>
                <Texto tipo="suave">{[l.cocina, l.nota !== null ? formatoNota(l.nota) : null].filter(Boolean).join(' · ')}</Texto>
              </Callout>
            </Marker>
          ))}
        </MapView>
      ) : null}
      {lugares?.length && !visibles.length ? <Texto tipo="suave">Ninguno cumple esos filtros.</Texto> : null}
      {verMapa ? null : visibles.map((l) => <FilaLugar key={l.id} lugar={l} />)}
    </Pantalla>
  );
}

const estilos = StyleSheet.create({
  fila: { flexDirection: 'row', gap: 12, padding: 10, borderRadius: RADIO, borderWidth: 1, alignItems: 'center' },
  foto: { width: 60, height: 60, borderRadius: 30 },
});
