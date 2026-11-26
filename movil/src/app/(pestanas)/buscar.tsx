// Buscar, copia de app.seccion_mi_lista con cuenta: la cinta de fotos, «Buscar», Descubrir | Personas.
// Descubrir (explorar.seccion): por nombre, en una zona (~1 km) o cerca de ti; sin buscar nada, «Lo mejor de la
// semana». Con resultados: «Filtros», Lista/Mapa, «Solo analizados», el orden y las tarjetas de 15 en 15.
// Personas (amigos.buscador_de_personas): buscar por nombre o @usuario y «Añadir».
import { useLocalSearchParams } from 'expo-router';
import * as Location from 'expo-location';
import { useState } from 'react';
import { Pressable, Text, View } from 'react-native';

import { CampoDireccion } from '@/components/direccion';
import { MapaFotos } from '@/components/mapa_fotos';
import { Avatar } from '@/components/persona';
import { Portada } from '@/components/portada';
import { EstadoLugar, ItemLista, ListaTarjetas, TarjetaLista, TarjetaRestaurante } from '@/components/tarjeta';
import {
  Boton, Campo, Deslizador, Desplegable, Info, Interruptor, Pantalla, Segmentado, SelectorMultiple, Texto,
} from '@/components/ui';
import { api, ErrorApi, InicioDatos, Lugar, mensaje, Persona, Tarjeta, Yo } from '@/lib/api';
import { useCarga } from '@/lib/carga';
import { abrirLugar, ESTADOS } from '@/lib/lugares';
import { HUECO, LETRA, useColores } from '@/lib/tema';

type Modo = 'Descubrir' | 'Personas';
type Orden = 'Más cerca' | 'Mejor nota';
const POR_PAGINA = 15;
const MAX_EN_MAPA = 50;   // con más, sin fotos en los pines

interface Punto {
  lat: number;
  lon: number;
}

function km(a: Punto, b: Punto): number {
  const r = Math.PI / 180;
  const h = Math.sin(((b.lat - a.lat) * r) / 2) ** 2
    + Math.cos(a.lat * r) * Math.cos(b.lat * r) * Math.sin(((b.lon - a.lon) * r) / 2) ** 2;
  return 12742 * Math.asin(Math.sqrt(h));
}

/** explorar._distancia: «350 m» o «1,2 km». */
function distancia(l: Lugar, cerca: Punto | null): string {
  if (!cerca) return '';
  const d = km(cerca, l);
  return d < 1 ? `${Math.round(d * 1000)} m` : `${d.toFixed(1).replace('.', ',')} km`;
}

/** explorar._nota: «★ 4,5» (sin decimales de más). */
function nota(l: Lugar): string {
  return l.nota ? `★ ${String(Number(l.nota)).replace('.', ',')}` : '';
}

function item(l: Lugar, n: number, cerca: Punto | null): ItemLista {
  const estado = (l.estado ?? 'sin_analizar') as EstadoLugar;
  return {
    id: l.id, n, nombre: l.nombre, cocina: l.cocina ?? '', foto: l.foto, icono: l.icono ?? '🍽️',
    meta: [nota(l), l.ciudad, distancia(l, cerca)].filter(Boolean).join(' · '), estado, estadoTexto: ESTADOS[estado],
  };
}

// ----------------------- Personas -----------------------

function Personas({ yo }: { yo: Yo | null }) {
  const c = useColores();
  const [texto, setTexto] = useState('');
  const [alias, setAlias] = useState('');
  const [errorAlias, setErrorAlias] = useState<string | null>(null);
  const [enviando, setEnviando] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const consulta = texto.trim().replace(/^@/, '');
  const personas = useCarga(() => (consulta.length >= 2
    ? api<{ personas: Persona[] }>('GET', '/personas', undefined, { q: consulta })
    : Promise.resolve({ personas: [] as Persona[] })), [consulta]);

  async function guardarAlias() {
    setErrorAlias(null);
    try {
      await api('PUT', '/yo/alias', { alias });
    } catch (e) {
      setErrorAlias(mensaje(e));
    }
  }

  async function anadir(p: Persona) {
    setError(null);
    setEnviando(p.alias);
    try {
      await api('POST', `/personas/${p.alias}/amistad`);
      personas.recargar();
    } catch (e) {
      setError(mensaje(e));
    } finally {
      setEnviando(null);
    }
  }

  const lista = personas.datos?.personas ?? [];
  return (
    <>
      {yo && !yo.alias ? (
        <>
          <Texto tipo="suave">Elige un nombre de usuario para que tus amigos te encuentren. Tu correo no lo ve nadie.</Texto>
          <Campo etiqueta="Nombre de usuario" placeholder="Ej. ana_g" maxLength={21} value={alias} onChangeText={setAlias}
            autoCapitalize="none" autoCorrect={false} />
          <Boton texto="Guardar nombre de usuario" alPulsar={guardarAlias} />
          {errorAlias ? <Info tipo="error">{errorAlias}</Info> : null}
          <View style={{ height: 1, backgroundColor: c.borde, marginVertical: 8 }} />
        </>
      ) : null}
      {error ? <Info tipo="error">{error}</Info> : null}
      {/* componentes/buscador_amigos.*: lupa, 44 px, 16 px de letra */}
      <View>
        <Campo icono="search" placeholder="Busca por nombre o @usuario" value={texto} onChangeText={setTexto}
          autoCapitalize="none" autoCorrect={false} accessibilityLabel="Buscar amigos por nombre o @usuario"
          style={{ minHeight: 42, fontSize: 16, paddingLeft: 8 }} />
        <View style={{ marginTop: 6, gap: 4 }}>
          {lista.slice(0, 8).map((p) => (
            <View key={p.alias} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 6, paddingHorizontal: 4 }}>
              <Avatar persona={{ ...p, foto: null }} tam={40} />
              <View style={{ flex: 1, minWidth: 0 }}>
                <Text style={{ fontFamily: LETRA.semi, fontSize: 15, lineHeight: 19.5, color: c.texto }}>{p.nombre}</Text>
                <Text style={{ fontFamily: LETRA.normal, fontSize: 13, opacity: 0.7, color: c.texto }}>{`@${p.alias}`}</Text>
              </View>
              {p.estado === 'nuevo' ? (
                <Pressable accessibilityRole="button" accessibilityLabel={`Añadir a ${p.nombre} como amigo`}
                  disabled={enviando === p.alias} onPress={() => anadir(p)}
                  style={{ minHeight: 36, paddingHorizontal: 14, borderRadius: 999, backgroundColor: c.primario, justifyContent: 'center',
                    opacity: enviando === p.alias ? 0.6 : 1 }}>
                  <Text style={{ fontFamily: LETRA.semi, fontSize: 14, color: c.fondo }}>{enviando === p.alias ? 'Enviando…' : 'Añadir'}</Text>
                </Pressable>
              ) : (
                <Text style={{ fontFamily: LETRA.normal, fontSize: 13, opacity: 0.75, color: c.texto }}>
                  {p.estado === 'amigo' ? 'Amigos ✓' : 'Pendiente'}
                </Text>
              )}
            </View>
          ))}
        </View>
        {consulta.length >= 2 && personas.datos && !lista.length ? (
          <Text style={{ marginTop: 8, marginHorizontal: 4, fontFamily: LETRA.normal, fontSize: 14, opacity: 0.7, color: c.texto }}>
            No hay nadie con ese nombre o @usuario.
          </Text>
        ) : null}
      </View>
    </>
  );
}

// ----------------------- Descubrir -----------------------

function LoMejorDeLaSemana() {
  const destacados = useCarga(() => api<{ de_la_semana: boolean; restaurantes: Tarjeta[] }>('GET', '/destacados'), []);
  const d = destacados.datos;
  if (!d?.restaurantes.length) return null;
  return (
    <>
      <Texto tipo="subtitulo">{d.de_la_semana ? 'Lo mejor de la semana' : 'Lo último que se ha valorado'}</Texto>
      <ListaTarjetas>
        {d.restaurantes.map((t, i) => <TarjetaRestaurante key={`${t.id}-${i}`} tarjeta={t} n={i + 1} variante="poster" />)}
      </ListaTarjetas>
    </>
  );
}

interface Respuesta {
  lugares: Lugar[];
  cocinas: string[];
  total: number;
}

function Descubrir({ sinTope }: { sinTope: number }) {
  const c = useColores();
  const [escrito, setEscrito] = useState('');
  const [texto, setTexto] = useState('');                 // lo buscado (al pulsar Intro o salir de la caja)
  const [zonaEscrita, setZonaEscrita] = useState('');
  const [zona, setZona] = useState<(Punto & { texto: string }) | null>(null);
  const [avisoZona, setAvisoZona] = useState<string | null>(null);
  const [tu, setTu] = useState<Punto | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [errorUbicacion, setErrorUbicacion] = useState<string | null>(null);
  const [cocinas, setCocinas] = useState<string[]>([]);
  const [presupuesto, setPresupuesto] = useState<number[]>([0, sinTope]);
  const [notaMin, setNotaMin] = useState(0);
  const [platoEscrito, setPlatoEscrito] = useState('');
  const [plato, setPlato] = useState('');
  const [vista, setVista] = useState<'Lista' | 'Mapa'>('Lista');
  const [soloAnalizados, setSoloAnalizados] = useState(false);
  const [orden, setOrden] = useState<Orden>('Más cerca');
  const [visibles, setVisibles] = useState(POR_PAGINA);

  const cerca: Punto | null = zona ?? tu;   // desde dónde se mide la distancia: la zona, si hay, o tú
  const buscando = !!zona || !!texto.trim() || !!tu;
  const parametros = {
    q: texto.trim(), lat: cerca?.lat, lon: cerca?.lon, zona: zona ? 'true' : undefined, cocinas,
    pmin: presupuesto[0], pmax: presupuesto[1], nota: notaMin || undefined, plato: plato.trim(),
  };
  const lugares = useCarga(() => (buscando
    ? api<Respuesta>('GET', '/lugares', undefined, parametros)
    : Promise.resolve(null)), [buscando, JSON.stringify(parametros)]);

  async function elegirZonaEscrita() {
    setAvisoZona(null);
    setVisibles(POR_PAGINA);
    if (!zonaEscrita.trim()) {
      setZona(null);
      return;
    }
    try {
      const g = await api<{ lat: number; lon: number }>('GET', '/geocodificar', undefined, { q: zonaEscrita.trim() });
      setZona({ lat: g.lat, lon: g.lon, texto: zonaEscrita.trim() });
    } catch (e) {
      setZona(null);
      setAvisoZona(e instanceof ErrorApi && e.estado === 404
        ? 'No encontramos esa zona. Prueba a elegir una de las sugerencias.'
        : 'No se ha podido buscar esa zona ahora mismo. Prueba en un momento.');
    }
  }

  async function usarMiUbicacion() {
    setErrorUbicacion(null);
    setOcupado(true);
    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== 'granted') throw new Error('No has dado permiso para ver tu ubicación.');
      const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High });
      setTu({ lat: pos.coords.latitude, lon: pos.coords.longitude });
      setVisibles(POR_PAGINA);
    } catch (e) {
      setErrorUbicacion(mensaje(e));
    } finally {
      setOcupado(false);
    }
  }

  const activos = [cocinas.length > 0, notaMin > 0, !!plato.trim(), presupuesto[0] !== 0 || presupuesto[1] !== sinTope]
    .filter(Boolean).length;
  const r = lugares.datos;
  let encontrados = r?.lugares ?? [];
  if (soloAnalizados) encontrados = encontrados.filter((l) => l.estado === 'analizado');
  const conNota = encontrados.some((l) => l.nota);
  if (conNota && (orden === 'Mejor nota' || !cerca)) {
    encontrados = [...encontrados].sort((a, b) => (b.nota ?? 0) - (a.nota ?? 0));
  }

  let resultados = null;
  if (!buscando) {
    resultados = <LoMejorDeLaSemana />;
  } else if (lugares.error) {
    resultados = <Info tipo="aviso">{lugares.error}</Info>;
  } else if (r && r.total === 0) {
    resultados = <Info>{`No hemos encontrado nada así${cerca ? ' por aquí.' : '. Prueba con otro nombre o usa tu ubicación.'}`}</Info>;
  } else if (r) {
    resultados = (
      <>
        <Desplegable titulo={activos ? `Filtros (${activos})` : 'Filtros'} icono="tune">
          <SelectorMultiple titulo="Cocina" opciones={r.cocinas} elegidas={cocinas} vacio="Cualquiera"
            alCambiar={(x) => { setCocinas(x); setVisibles(POR_PAGINA); }} />
          <Deslizador titulo="Presupuesto por persona" min={0} max={sinTope} paso={5} valor={presupuesto}
            alCambiar={(v) => { setPresupuesto(v); setVisibles(POR_PAGINA); }} formato={(v) => `${v} €`} />
          <Deslizador titulo="Nota mínima en Google" min={0} max={5} paso={0.5} valor={[notaMin]}
            alCambiar={(v) => { setNotaMin(v[0]); setVisibles(POR_PAGINA); }} formato={(v) => `${v.toFixed(1)} ⭐`} />
          <Campo etiqueta="Plato que destaquen" placeholder="Ej. croquetas" value={platoEscrito} onChangeText={setPlatoEscrito}
            onSubmitEditing={() => setPlato(platoEscrito)} onBlur={() => setPlato(platoEscrito)} returnKeyType="search" />
          <Texto tipo="suave">El precio y los platos solo se saben de los analizados.</Texto>
        </Desplegable>
        {!r.lugares.length ? <Info>Ninguno cumple esos filtros.</Info> : (
          <>
            <View style={{ flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: HUECO }}>
              <Segmentado opciones={['Lista', 'Mapa'] as const} elegidas={[vista]} alElegir={setVista} estirar={false} />
              <Interruptor texto="Solo analizados" valor={soloAnalizados}
                alCambiar={(v) => { setSoloAnalizados(v); setVisibles(POR_PAGINA); }} />
              <Texto tipo="suave">{`${encontrados.length} sitio${encontrados.length !== 1 ? 's' : ''}`}</Texto>
            </View>
            {!encontrados.length ? <Info>Aún no hay ninguno analizado por aquí.</Info> : (
              <>
                {conNota ? (
                  <Segmentado opciones={['Más cerca', 'Mejor nota'] as const} elegidas={[orden]} estirar={false}
                    alElegir={(o) => { setOrden(o); setVisibles(POR_PAGINA); }} />
                ) : null}
                {vista === 'Mapa' ? (
                  <>
                    <MapaFotos usuario={tu}
                      alTocar={(p) => { const l = encontrados.find((x) => x.id === p.id); if (l) abrirLugar(l); }}
                      puntos={encontrados.map((l, i) => ({ id: l.id, n: i + 1, nombre: l.nombre, lat: l.lat, lon: l.lon,
                        foto: encontrados.length > MAX_EN_MAPA ? null : l.foto, analizado: l.estado === 'analizado' }))} />
                    <Texto tipo="suave">{`${tu ? '🔵 Tú · ' : ''}Toca un sitio para ver su ficha. Con borde verde, los analizados.`}</Texto>
                  </>
                ) : (
                  <>
                    <ListaTarjetas>
                      {encontrados.slice(0, visibles).map((l, i) => (
                        <TarjetaLista key={l.id} item={item(l, i + 1, cerca)} alTocar={() => abrirLugar(l)} />
                      ))}
                    </ListaTarjetas>
                    {encontrados.length > visibles ? <Boton texto="Ver más" alPulsar={() => setVisibles(visibles + POR_PAGINA)} /> : null}
                  </>
                )}
              </>
            )}
          </>
        )}
      </>
    );
  }

  return (
    <>
      <Campo icono="search" placeholder="Cualquier restaurante, bar o cafetería" value={escrito} onChangeText={setEscrito}
        accessibilityLabel="Buscar un restaurante" returnKeyType="search" autoCorrect={false}
        onSubmitEditing={() => { setTexto(escrito); setVisibles(POR_PAGINA); }} onBlur={() => setTexto(escrito)} />
      <CampoDireccion valor={zonaEscrita} placeholder="Zona: barrio, calle o pueblo" alEnviar={elegirZonaEscrita}
        alEscribir={(t) => { setZonaEscrita(t); if (!t.trim()) setZona(null); }}
        alElegir={(p) => { setZona(p); setAvisoZona(null); setVisibles(POR_PAGINA); }} />
      {avisoZona ? <Info tipo="aviso">{avisoZona}</Info> : null}
      <Boton texto="Usar mi ubicación" emoji="📍" cargando={ocupado} alPulsar={usarMiUbicacion}
        style={{ minHeight: 44, backgroundColor: c.fondo }} />
      {errorUbicacion ? <Info tipo="aviso">{errorUbicacion}</Info> : null}
      {zona ? <Texto tipo="suave">{`✓ En ${zona.texto} (lo que hay en ~1 km)`}</Texto>
        : tu ? <Texto tipo="suave">{`✓ Cerca de tu ubicación${texto.trim() ? '' : ' (lo que hay alrededor)'}`}</Texto> : null}
      {resultados}
    </>
  );
}

export default function Buscar() {
  const params = useLocalSearchParams<{ modo?: string }>();
  const yo = useCarga(() => api<Yo>('GET', '/yo'), []);
  const portada = useCarga(() => api<InicioDatos>('GET', '/inicio'), []);
  const [modo, setModo] = useState<Modo>('Descubrir');
  // «Buscar amigos» de Inicio llega con modo=personas (app.buscar_personas)
  const [modoRecibido, setModoRecibido] = useState<string | undefined>(undefined);
  if (params.modo && params.modo !== modoRecibido) {
    setModoRecibido(params.modo);
    setModo(params.modo === 'personas' ? 'Personas' : 'Descubrir');
  }
  return (
    <Pantalla>
      <Portada soloCinta fotos={portada.datos?.portada ?? []} />
      <Texto tipo="encabezado">Buscar</Texto>
      <Segmentado opciones={['Descubrir', 'Personas'] as const} elegidas={[modo]} alElegir={setModo} />
      {modo === 'Personas' ? <Personas yo={yo.datos} /> : <Descubrir sinTope={yo.datos?.presupuesto_sin_limite ?? 100} />}
    </Pantalla>
  );
}
