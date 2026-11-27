// Comer hoy, copia del buscador de app.py: portada, «Buscar en», Food match, desde dónde salís (+ «Usar mi
// ubicación»), cómo vais, tiempo máximo, cocina, presupuesto, «Más opciones» (plato) y el botón fijo de abajo.
// Resultados: «Cambiar» + Lista/Mapa, el resumen, el orden, las tarjetas y «Ver más». Solo los que cumplen todo.
import * as Location from 'expo-location';
import { router, useLocalSearchParams } from 'expo-router';
import { ReactNode, useEffect, useState } from 'react';
import { StyleSheet, View } from 'react-native';
import Svg, { Defs, LinearGradient, Rect, Stop } from 'react-native-svg';

import { CampoDireccion, Punto } from '@/components/direccion';
import { MapaFotos } from '@/components/mapa_fotos';
import { Portada } from '@/components/portada';
import { TarjetaRestaurante } from '@/components/tarjeta';
import {
  Boton, Caja, Campo, Deslizador, Desplegable, Info, Pantalla, Segmentado, Selector, Texto,
} from '@/components/ui';
import { api, InicioDatos, mensaje, Tarjeta, Yo } from '@/lib/api';
import { useCarga } from '@/lib/carga';
import { precargarMazo } from '@/lib/mazo';
import { HUECO, useColores } from '@/lib/tema';

type Transporte = 'En coche' | 'A pie';
type Fuente = 'Mi lista' | 'Todos los restaurantes';
type Orden = 'Mejor valorados' | 'Más cerca';

const ETIQUETAS_TRANSPORTE: Record<Transporte, string> = { 'En coche': '🚗 Coche', 'A pie': '🚶 A pie' };
const TOP_N = 5;
const TOP_N_MAX = 10;
const CUALQUIERA = 'Cualquiera';
const SUBTITULO = 'Decid desde dónde salís y qué os apetece, y os digo cuál.';

interface Ubicacion extends Punto {
  precision?: number | null;   // solo la del GPS
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
  presupuesto: number[];
  plato: string;
  fuente: Fuente;
}

function textoPresupuesto(min: number, max: number | null): string {
  if (max === null) return min ? `Desde ${min} €` : 'Cualquier precio';
  return `${min}–${max} €`;
}

/** app.resumen_busqueda: «Calle, barrio · Cocina · 🚗 ≤20' · 0–30 €». */
function resumen(p: Pedido, sinTope: number): string {
  const lugar = p.ubicacion.texto.split(',').slice(0, 2).map((x) => x.trim()).join(', ');
  const max = p.presupuesto[1] >= sinTope ? null : p.presupuesto[1];
  return [lugar, p.cocina || 'Cualquier cocina', `${p.transporte === 'En coche' ? '🚗' : '🚶'} ≤${p.minutos}'`,
    textoPresupuesto(p.presupuesto[0], max)].join(' · ');
}

/** .st-key-boton_buscar de global.css: fijo justo encima de la barra, con un degradado del color del fondo. */
function BotonFijo({ children }: { children: ReactNode }) {
  const c = useColores();
  return (
    <View style={estilos.fijo} pointerEvents="box-none">
      <Svg style={StyleSheet.absoluteFill} pointerEvents="none">
        <Defs>
          <LinearGradient id="fondoBoton" x1="0" y1="1" x2="0" y2="0">
            <Stop offset="0" stopColor={c.fondo} stopOpacity="1" />
            <Stop offset="0.75" stopColor={c.fondo} stopOpacity="1" />
            <Stop offset="1" stopColor={c.fondo} stopOpacity="0" />
          </LinearGradient>
        </Defs>
        <Rect width="100%" height="100%" fill="url(#fondoBoton)" />
      </Svg>
      {children}
    </View>
  );
}

export default function ComerHoy() {
  const c = useColores();
  const params = useLocalSearchParams<{ plato?: string }>();
  const yo = useCarga(() => api<Yo>('GET', '/yo'), []);
  const hayMatch = !!yo.datos?.food_match;
  useEffect(() => { if (hayMatch) precargarMazo(); }, [hayMatch]);   // para que al tocar «Food match» ya esté
  const portada = useCarga(() => api<InicioDatos>('GET', '/inicio'), []);
  const [fuente, setFuente] = useState<Fuente>('Mi lista');
  const todos = fuente === 'Todos los restaurantes';
  const cocinas = useCarga(() => api<{ cocinas: string[]; total: number }>('GET', '/cocinas', undefined,
    { fuente: todos ? 'todos' : 'lista' }), [todos]);
  const sinTope = yo.datos?.presupuesto_sin_limite ?? 100;

  const [actual, setActual] = useState<Ubicacion | null>(null);      // «Usar mi ubicación»
  const [sugerida, setSugerida] = useState<Ubicacion | null>(null);  // una sugerencia de la caja
  const [errorUbicacion, setErrorUbicacion] = useState<string | null>(null);
  const [direccion, setDireccion] = useState('');
  const [transporte, setTransporte] = useState<Transporte>('En coche');
  const [minutos, setMinutos] = useState(20);
  const [cocina, setCocina] = useState(CUALQUIERA);
  const [presupuesto, setPresupuesto] = useState<number[]>([0, 30]);
  const [plato, setPlato] = useState('');

  const [pedido, setPedido] = useState<Pedido | null>(null);
  const [resultado, setResultado] = useState<Resultado | null>(null);
  const [verResultados, setVerResultados] = useState(false);
  const [orden, setOrden] = useState<Orden>('Mejor valorados');
  const [vista, setVista] = useState<'Lista' | 'Mapa'>('Lista');
  const [mostrados, setMostrados] = useState(TOP_N);
  const [ocupado, setOcupado] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Las preferencias del Perfil son los valores iniciales del buscador (se aplican al llegar, al dibujar)
  const preferencias = yo.datos?.preferencias;
  const [aplicadas, setAplicadas] = useState<Yo['preferencias'] | null>(null);
  if (preferencias && preferencias !== aplicadas) {
    setAplicadas(preferencias);
    setTransporte(preferencias.transporte);
    setMinutos(preferencias.tiempo);
    setPresupuesto([...preferencias.presupuesto]);
  }
  // «Más sitios con X» de Inicio: el plato ya puesto y de vuelta al buscador (app.buscar_sitios_con)
  const [platoRecibido, setPlatoRecibido] = useState<string | undefined>(undefined);
  if (params.plato && params.plato !== platoRecibido) {
    setPlatoRecibido(params.plato);
    setPlato(params.plato);
    setVerResultados(false);
  }

  async function usarMiUbicacion() {
    setErrorUbicacion(null);
    setOcupado('ubicacion');
    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== 'granted') throw new Error('No has dado permiso para ver tu ubicación. Escribe la dirección.');
      const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High });
      setActual({ lat: pos.coords.latitude, lon: pos.coords.longitude, texto: 'Tu ubicación', precision: pos.coords.accuracy });
    } catch (e) {
      setErrorUbicacion(mensaje(e));
    } finally {
      setOcupado(null);
    }
  }

  async function buscar(cambios: Partial<Pedido> = {}) {
    setError(null);
    setOcupado('buscar');
    try {
      let origen = cambios.ubicacion ?? actual ?? sugerida;
      if (!origen) {
        if (!direccion.trim()) throw new Error('Dinos desde dónde salís (o usa tu ubicación).');
        const g = await api<{ lat: number; lon: number; direccion: string }>('GET', '/geocodificar', undefined, { q: direccion.trim() });
        origen = { lat: g.lat, lon: g.lon, texto: g.direccion };
      }
      const p: Pedido = {
        ubicacion: origen, transporte, minutos, cocina: cocina === CUALQUIERA ? '' : cocina, presupuesto, plato: plato.trim(),
        fuente, ...cambios,
      };
      const r = await api<Resultado>('POST', '/buscar', {
        lat: p.ubicacion.lat, lon: p.ubicacion.lon, transporte: p.transporte, minutos: p.minutos, cocina: p.cocina,
        presupuesto_min: p.presupuesto[0], presupuesto_max: p.presupuesto[1], plato: p.plato,
        fuente: p.fuente === 'Mi lista' ? 'lista' : 'todos',
      });
      if (r.vacio) throw new Error('Todavía no hay restaurantes analizados por esa zona. Prueba en Buscar → Descubrir.');
      setPedido(p);
      setResultado(r);
      setMostrados(TOP_N);
      setVerResultados(true);
    } catch (e) {
      setError(mensaje(e));
      setVerResultados(false);   // fallar_busqueda: el error se ve en el buscador
    } finally {
      setOcupado(null);
    }
  }

  // «Ampliar a…», «Cualquier cocina», «Sin plato concreto»: cambian el filtro y repiten la búsqueda (buscar_con)
  function buscarCon(cambios: Partial<Pedido>) {
    if (cambios.minutos !== undefined) setMinutos(cambios.minutos);
    if (cambios.cocina !== undefined) setCocina(CUALQUIERA);
    if (cambios.plato !== undefined) setPlato('');
    buscar({ ...pedido, ...cambios });
  }

  const abrirFicha = (id: number | string) =>
    router.push({ pathname: '/restaurante/[id]', params: { id: String(id), plato: pedido?.plato ?? '' } });

  // ----------------------- resultados -----------------------
  if (verResultados && resultado && pedido) {
    const ordenados = orden === 'Más cerca'
      ? [...resultado.resultados].sort((a, b) => (a.minutos ?? 0) - (b.minutos ?? 0) || (b.puntuacion ?? 0) - (a.puntuacion ?? 0))
      : resultado.resultados;
    const top = ordenados.slice(0, Math.min(mostrados, TOP_N_MAX));
    const quedan = Math.min(TOP_N_MAX, ordenados.length) - top.length;
    const modo = pedido.transporte === 'En coche' ? 'en coche' : 'andando';
    const usuario = { lat: pedido.ubicacion.lat, lon: pedido.ubicacion.lon };
    const cabecera = (
      <>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: HUECO }}>
          <Boton texto="Cambiar" tipo="texto" icono="arrow_back" ancho="contenido" style={{ alignSelf: 'center' }}
            alPulsar={() => setVerResultados(false)} />
          <Segmentado opciones={['Lista', 'Mapa'] as const} elegidas={[vista]} alElegir={setVista} estirar={false} />
        </View>
        <Texto tipo="suave">{resumen(pedido, sinTope)}</Texto>
        {resultado.aviso ? <Info tipo="aviso">{resultado.aviso}</Info> : null}
      </>
    );

    if (!ordenados.length) {
      return (
        <Pantalla>
          {cabecera}
          <Caja>
            <Texto tipo="subtitulo">Nada por aquí</Texto>
            <Texto>{`No hay ningún restaurante a menos de ${pedido.minutos} min ${modo} que cumpla lo que habéis pedido.`}</Texto>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: HUECO }}>
              {pedido.minutos < 60 ? (
                <Boton texto={`Ampliar a ${Math.min(60, pedido.minutos + 10)} min`} ancho="contenido" cargando={ocupado === 'buscar'}
                  alPulsar={() => buscarCon({ minutos: Math.min(60, pedido.minutos + 10) })} />
              ) : null}
              {pedido.cocina ? <Boton texto="Cualquier cocina" ancho="contenido" alPulsar={() => buscarCon({ cocina: '' })} /> : null}
              {pedido.plato ? <Boton texto="Sin plato concreto" ancho="contenido" alPulsar={() => buscarCon({ plato: '' })} /> : null}
            </View>
          </Caja>
          <MapaFotos usuario={usuario} puntos={[]} alTocar={() => undefined} />
          <Texto tipo="suave">🔵 Tú — comprueba que el mapa te sitúa donde esperabas.</Texto>
        </Pantalla>
      );
    }

    return (
      <Pantalla>
        {cabecera}
        <Segmentado opciones={['Mejor valorados', 'Más cerca'] as const} elegidas={[orden]} alElegir={setOrden} estirar={false} />
        {ordenados.length === 1 ? <Texto tipo="negrita">Solo hay 1 sitio que encaja</Texto>
          : ordenados.length < TOP_N ? <Texto tipo="negrita">{`Solo hay ${ordenados.length} que encajan`}</Texto> : null}
        {vista === 'Mapa' ? (
          <>
            <MapaFotos usuario={usuario} alTocar={(p) => abrirFicha(p.id)}
              puntos={top.filter((t) => t.lat !== null && t.lon !== null).map((t, i) => ({
                id: t.id, n: i + 1, nombre: t.nombre, lat: t.lat as number, lon: t.lon as number, foto: t.foto,
              }))} />
            <Texto tipo="suave">🔵 Tú · Toca una foto para ver la ficha.</Texto>
          </>
        ) : null}
        <View style={{ gap: 8 }}>
          {top.map((t, i) => <TarjetaRestaurante key={t.id} n={i + 1} tarjeta={t} transporte={pedido.transporte} plato={pedido.plato} />)}
        </View>
        {quedan > 0 ? <Boton texto={`Ver ${Math.min(5, quedan)} más`} alPulsar={() => setMostrados(mostrados + Math.min(5, quedan))} /> : null}
      </Pantalla>
    );
  }

  // ----------------------- buscador -----------------------
  const d = yo.datos;
  const dueno = d ? (d.alias ? `@${d.alias}` : d.nombre) : '';
  const total = cocinas.datos?.total ?? d?.lista.total ?? 0;
  const momento = todos ? `🍽️ Todos los restaurantes · ${total} sitios` : `🍽️ Los restaurantes de ${dueno}\n${total} sitios`;
  const listaVacia = !todos && !!d && d.lista.total === 0;
  const precision = actual?.precision;

  return (
    <View style={{ flex: 1, backgroundColor: c.fondo }}>
      <Pantalla>
        {d ? <Portada fotos={portada.datos?.portada ?? []} momento={momento} subtitulo={SUBTITULO} /> : null}
        <Segmentado titulo="Buscar en" opciones={['Mi lista', 'Todos los restaurantes'] as const} elegidas={[fuente]}
          alElegir={(f) => { setFuente(f); setCocina(CUALQUIERA); }} />
        {d?.food_match ? <Boton texto="Food match" icono="swipe" alPulsar={() => router.push('/match')} /> : null}
        {listaVacia ? (
          <>
            <Info>
              Todavía no tienes restaurantes en tu lista. Añádela en tus <Texto tipo="negrita">ajustes</Texto> (toca tu foto en
              el Perfil) o busca en <Texto tipo="negrita">Todos los restaurantes</Texto>.
            </Info>
            <Boton texto="Añadir tu lista" icono="add_location_alt" ancho="contenido" alPulsar={() => router.push('/ajustes')} />
          </>
        ) : (
          <>
            <CampoDireccion etiqueta="¿Desde dónde salís?" valor={direccion} desactivado={!!actual}
              placeholder={actual ? 'Usando tu ubicación' : 'Calle, barrio o sitio'}
              alEscribir={(t) => { setDireccion(t); setSugerida(null); }} alElegir={setSugerida} />
            {/* componentes/ubicacion.*: fondo de la página, 44 px de alto, 📍 */}
            <Boton texto="Usar mi ubicación" emoji="📍" cargando={ocupado === 'ubicacion'} alPulsar={usarMiUbicacion}
              style={{ minHeight: 44, backgroundColor: c.fondo }} />
            {actual ? (
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: HUECO }}>
                <Texto tipo="suave">{`✓ Tu ubicación${precision ? ` · ±${Math.round(precision)} m` : ''}`}</Texto>
                <Boton texto="Quitar" tipo="texto" ancho="contenido" alPulsar={() => setActual(null)} />
              </View>
            ) : null}
            {precision && precision > 1000 ? (
              <Texto tipo="suave">⚠️ Es poco precisa (habitual en ordenador). Si no cuadra, quítala y escribe la dirección.</Texto>
            ) : null}
            {!actual && errorUbicacion ? <Info tipo="aviso">{errorUbicacion}</Info> : null}

            <Segmentado titulo="¿Cómo vais?" opciones={['En coche', 'A pie'] as const} elegidas={[transporte]}
              alElegir={setTransporte} etiqueta={(t) => ETIQUETAS_TRANSPORTE[t]} />
            <Deslizador titulo="Tiempo máximo" min={5} max={60} paso={5} valor={[minutos]} alCambiar={(v) => setMinutos(v[0])}
              formato={(v) => `${v} min`} />
            <Selector titulo="Cocina" opciones={[CUALQUIERA, ...(cocinas.datos?.cocinas ?? [])]} valor={cocina} alElegir={setCocina} />
            <Deslizador titulo="Presupuesto por persona" min={0} max={sinTope} paso={5} valor={presupuesto} alCambiar={setPresupuesto}
              formato={(v) => `${v} €`} ayuda={`Arrastra el máximo hasta ${sinTope} € para no poner tope.`} />
            <Desplegable titulo="Más opciones">
              <Campo etiqueta="¿Algún plato concreto?" placeholder="Ej. sushi" value={plato} onChangeText={setPlato} maxLength={60} />
            </Desplegable>
            {error ? <Info tipo="error">{error}</Info> : null}
          </>
        )}
        <View style={{ height: 70 }} />
      </Pantalla>
      {listaVacia ? null : (
        <BotonFijo>
          <Boton tipo="primario" grande texto="Buscar restaurantes" icono="search" cargando={ocupado === 'buscar'}
            alPulsar={() => buscar()} />
        </BotonFijo>
      )}
    </View>
  );
}

const estilos = StyleSheet.create({
  fijo: { position: 'absolute', left: 0, right: 0, bottom: 0, paddingHorizontal: 15, paddingTop: 16, paddingBottom: 12 },
});
