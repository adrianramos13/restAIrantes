// Comer hoy: desde dónde salís, cómo vais, cuánto tiempo, cocina, presupuesto y plato -> los sitios que cumplen
// TODO (nunca se rellena con otros). Resultados en lista o mapa, ordenados por nota o cercanía, «Ver más».
import * as Location from 'expo-location';
import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { View } from 'react-native';
import MapView, { Marker } from 'react-native-maps';

import { CampoDireccion } from '@/components/direccion';
import { TarjetaRestaurante } from '@/components/tarjeta';
import { Boton, Caja, Campo, Chips, Pantalla, Seccion, Texto } from '@/components/ui';
import { api, mensaje, Tarjeta, Yo } from '@/lib/api';
import { useCarga } from '@/lib/carga';
import { RADIO, useColores } from '@/lib/tema';

type Transporte = 'En coche' | 'A pie';
type Fuente = 'lista' | 'todos';
type Orden = 'nota' | 'cerca';

const MINUTOS = [10, 15, 20, 30, 45, 60] as const;
const DESDE = [0, 10, 20, 30] as const;
const HASTA = [15, 20, 30, 40, 60, 100] as const;   // 100 = sin tope (PRESUPUESTO_SIN_LIMITE)
const PRIMEROS = 5;

/** Las opciones de siempre más la que venga de tus preferencias (p. ej. 25 min), para que salga marcada. */
function conValor(opciones: readonly number[], valor: number): number[] {
  return [...new Set([...opciones, valor])].sort((a, b) => a - b);
}
const MAXIMO = 10;

interface Ubicacion {
  lat: number;
  lon: number;
  texto: string;
}

interface Resultado {
  resultados: Tarjeta[];
  aviso: string | null;
  vacio: boolean;
}

interface Pedido {
  ubicacion: Ubicacion;
  transporte: Transporte;
  minutos: number;
  cocina: string;
  desde: number;
  hasta: number;
  plato: string;
  fuente: Fuente;
}

export default function ComerHoy() {
  const c = useColores();
  const yo = useCarga(() => api<Yo>('GET', '/yo'), []);
  const [fuente, setFuente] = useState<Fuente>('lista');
  const cocinas = useCarga(() => api<{ cocinas: string[] }>('GET', '/cocinas', undefined, { fuente }), [fuente]);

  const [ubicacion, setUbicacion] = useState<Ubicacion | null>(null);
  const [direccion, setDireccion] = useState('');
  const [transporte, setTransporte] = useState<Transporte>('En coche');
  const [minutos, setMinutos] = useState(20);
  const [cocina, setCocina] = useState('');
  const [desde, setDesde] = useState(0);
  const [hasta, setHasta] = useState(30);
  const [plato, setPlato] = useState('');

  const [pedido, setPedido] = useState<Pedido | null>(null);
  const [resultado, setResultado] = useState<Resultado | null>(null);
  const [orden, setOrden] = useState<Orden>('nota');
  const [verMapa, setVerMapa] = useState(false);
  const [mostrados, setMostrados] = useState(PRIMEROS);
  const [ocupado, setOcupado] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // «Food match» tarda en preparar el mazo la primera vez (baja los restaurantes de tu zona): se pide ya, sin
  // esperar, y la API lo guarda media hora (como deslizar.preparar en la web)
  const conFoodMatch = !!yo.datos?.food_match;
  useEffect(() => {
    if (conFoodMatch) api('GET', '/deslizar').catch(() => undefined);
  }, [conFoodMatch]);

  // Las preferencias del Perfil son los valores iniciales del buscador (se aplican al llegar, al dibujar)
  const preferencias = yo.datos?.preferencias;
  const [aplicadas, setAplicadas] = useState<Yo['preferencias'] | null>(null);
  if (preferencias && preferencias !== aplicadas) {
    setAplicadas(preferencias);
    setTransporte(preferencias.transporte);
    setMinutos(preferencias.tiempo);
    setDesde(preferencias.presupuesto[0]);
    setHasta(preferencias.presupuesto[1]);
  }

  async function usarMiUbicacion() {
    setError(null);
    setOcupado('ubicacion');
    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== 'granted') throw new Error('Sin permiso para ver tu ubicación: escribe la dirección.');
      const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High });
      const precision = pos.coords.accuracy ? ` · ±${Math.round(pos.coords.accuracy)} m` : '';
      setUbicacion({ lat: pos.coords.latitude, lon: pos.coords.longitude, texto: `Tu ubicación${precision}` });
    } catch (e) {
      setError(mensaje(e));
    } finally {
      setOcupado(null);
    }
  }

  async function buscar(cambios: Partial<Pedido> = {}) {
    setError(null);
    setOcupado('buscar');
    try {
      let origen = cambios.ubicacion ?? ubicacion;
      if (!origen) {
        if (!direccion.trim()) throw new Error('Dinos desde dónde salís (o usa tu ubicación).');
        const g = await api<{ lat: number; lon: number; direccion: string }>('GET', '/geocodificar', undefined, {
          q: direccion.trim(),
        });
        origen = { lat: g.lat, lon: g.lon, texto: g.direccion };
      }
      const p: Pedido = { ubicacion: origen, transporte, minutos, cocina, desde, hasta, plato: plato.trim(), fuente, ...cambios };
      const r = await api<Resultado>('POST', '/buscar', {
        lat: p.ubicacion.lat, lon: p.ubicacion.lon, transporte: p.transporte, minutos: p.minutos, cocina: p.cocina,
        presupuesto_min: p.desde, presupuesto_max: p.hasta, plato: p.plato, fuente: p.fuente,
      });
      setPedido(p);
      setResultado(r);
      setMostrados(PRIMEROS);
      setOrden('nota');
    } catch (e) {
      setError(mensaje(e));
    } finally {
      setOcupado(null);
    }
  }

  // ----------------------- resultados -----------------------
  if (resultado && pedido) {
    const ordenados =
      orden === 'cerca'
        ? [...resultado.resultados].sort((a, b) => (a.minutos ?? 0) - (b.minutos ?? 0) || (b.puntuacion ?? 0) - (a.puntuacion ?? 0))
        : resultado.resultados;
    const top = ordenados.slice(0, Math.min(mostrados, MAXIMO));
    const quedan = Math.min(MAXIMO, ordenados.length) - top.length;
    const modo = pedido.transporte === 'En coche' ? 'en coche' : 'andando';
    return (
      <Pantalla>
        <Boton texto="← Cambiar la búsqueda" tipo="texto" alPulsar={() => setResultado(null)} />
        <Texto tipo="suave">
          {`Desde ${pedido.ubicacion.texto} · ${pedido.minutos} min ${modo}${pedido.cocina ? ` · ${pedido.cocina}` : ''}${pedido.plato ? ` · «${pedido.plato}»` : ''}`}
        </Texto>
        {resultado.aviso ? <Texto tipo="suave">{resultado.aviso}</Texto> : null}

        {resultado.vacio ? (
          <Caja>
            <Texto>Todavía no hay restaurantes {pedido.fuente === 'todos' ? 'analizados por esa zona' : 'en tu lista'}.</Texto>
          </Caja>
        ) : !ordenados.length ? (
          <Caja>
            <Texto tipo="subtitulo">Nada por aquí</Texto>
            <Texto>{`No hay ningún restaurante a menos de ${pedido.minutos} min ${modo} que cumpla lo que habéis pedido.`}</Texto>
            {pedido.minutos < 60 ? (
              <Boton
                texto={`Ampliar a ${Math.min(60, pedido.minutos + 10)} min`}
                tipo="secundario"
                cargando={ocupado === 'buscar'}
                alPulsar={() => buscar({ ...pedido, minutos: Math.min(60, pedido.minutos + 10) })}
              />
            ) : null}
            {pedido.cocina ? <Boton texto="Cualquier cocina" tipo="secundario" alPulsar={() => buscar({ ...pedido, cocina: '' })} /> : null}
            {pedido.plato ? <Boton texto="Sin plato concreto" tipo="secundario" alPulsar={() => buscar({ ...pedido, plato: '' })} /> : null}
          </Caja>
        ) : (
          <>
            {ordenados.length < PRIMEROS ? (
              <Texto tipo="subtitulo">{ordenados.length === 1 ? 'Solo hay 1 sitio que encaja' : `Solo hay ${ordenados.length} que encajan`}</Texto>
            ) : null}
            <Chips opciones={['nota', 'cerca'] as const} elegidas={[orden]} alElegir={setOrden}
              etiqueta={(o) => (o === 'nota' ? 'Mejor valorados' : 'Más cerca')} />
            <Chips opciones={['lista', 'mapa'] as const} elegidas={[verMapa ? 'mapa' : 'lista']}
              alElegir={(v) => setVerMapa(v === 'mapa')} etiqueta={(v) => (v === 'lista' ? 'Lista' : 'Mapa')} />
            {verMapa ? (
              <View style={{ height: 320, borderRadius: RADIO, overflow: 'hidden', borderWidth: 1, borderColor: c.borde }}>
                <MapView
                  style={{ flex: 1 }}
                  initialRegion={{ latitude: pedido.ubicacion.lat, longitude: pedido.ubicacion.lon, latitudeDelta: 0.06, longitudeDelta: 0.06 }}>
                  <Marker coordinate={{ latitude: pedido.ubicacion.lat, longitude: pedido.ubicacion.lon }} title="Desde aquí" pinColor="blue" />
                  {top.filter((t) => t.lat !== null && t.lon !== null).map((t) => (
                    <Marker
                      key={t.id}
                      coordinate={{ latitude: t.lat as number, longitude: t.lon as number }}
                      title={t.nombre}
                      description={`${t.cocina} · ${t.minutos}'`}
                      pinColor={c.primario}
                      onCalloutPress={() => router.push({ pathname: '/restaurante/[id]', params: { id: String(t.id), plato: pedido.plato } })}
                    />
                  ))}
                </MapView>
              </View>
            ) : null}
            {top.map((t) => (
              <TarjetaRestaurante key={t.id} tarjeta={t} transporte={pedido.transporte} plato={pedido.plato} />
            ))}
            {quedan > 0 ? (
              <Boton texto={`Ver ${Math.min(5, quedan)} más`} tipo="secundario" alPulsar={() => setMostrados(mostrados + 5)} />
            ) : null}
          </>
        )}
        {error ? <Texto tipo="error">{error}</Texto> : null}
      </Pantalla>
    );
  }

  // ----------------------- buscador -----------------------
  return (
    <Pantalla>
      <Texto tipo="titulo">¿Dónde comemos hoy?</Texto>
      <Chips opciones={['lista', 'todos'] as const} elegidas={[fuente]}
        alElegir={(f) => { setFuente(f); setCocina(''); }}
        etiqueta={(f) => (f === 'lista' ? 'Mi lista' : 'Todos los restaurantes')} />

      <Seccion titulo="¿Desde dónde salís?">
        {ubicacion ? (
          <Caja>
            <Texto>✓ {ubicacion.texto}</Texto>
            <Boton texto="Quitar" tipo="texto" alPulsar={() => setUbicacion(null)} />
          </Caja>
        ) : (
          <>
            <CampoDireccion valor={direccion} alEscribir={setDireccion} alElegir={setUbicacion} placeholder="Calle, barrio o sitio" />
            <Boton texto="Usar mi ubicación" tipo="secundario" cargando={ocupado === 'ubicacion'} alPulsar={usarMiUbicacion} />
          </>
        )}
      </Seccion>

      <Seccion titulo="¿Cómo vais?">
        <Chips opciones={['En coche', 'A pie'] as const} elegidas={[transporte]} alElegir={setTransporte}
          etiqueta={(t) => (t === 'En coche' ? '🚗 Coche' : '🚶 A pie')} />
      </Seccion>

      <Seccion titulo="Tiempo máximo">
        <Chips opciones={conValor(MINUTOS, minutos)} elegidas={[minutos]} alElegir={setMinutos} etiqueta={(m) => `${m} min`} />
      </Seccion>

      <Seccion titulo="Cocina">
        <Chips opciones={['', ...(cocinas.datos?.cocinas ?? [])]} elegidas={[cocina]} alElegir={setCocina}
          etiqueta={(x) => x || 'Cualquiera'} />
      </Seccion>

      <Seccion titulo="Presupuesto por persona">
        <Texto tipo="suave">Desde</Texto>
        <Chips opciones={conValor(DESDE, desde)} elegidas={[desde]} alElegir={(d) => { setDesde(d); if (d > hasta) setHasta(100); }}
          etiqueta={(d) => `${d} €`} />
        <Texto tipo="suave">Hasta</Texto>
        <Chips opciones={conValor(HASTA, hasta)} elegidas={[hasta]} alElegir={(h) => { setHasta(h); if (h < desde) setDesde(0); }}
          etiqueta={(h) => (h === 100 ? 'Sin tope' : `${h} €`)} />
      </Seccion>

      <Campo etiqueta="¿Algún plato concreto?" placeholder="Ej. sushi" value={plato} onChangeText={setPlato} maxLength={60} />

      {error ? <Texto tipo="error">{error}</Texto> : null}
      <Boton texto="Buscar restaurantes" cargando={ocupado === 'buscar'} alPulsar={() => buscar()} />
      {yo.datos?.food_match ? (
        <Boton texto="🔥 Food match: descubre sitios nuevos" tipo="secundario" alPulsar={() => router.push('/match')} />
      ) : null}
    </Pantalla>
  );
}
