// Ficha de un restaurante, copia de app.mostrar_ficha + contenido_ficha: el título con la ✕, las fotos, «Ya he ido»
// (ventanita: estrellas, cuándo, lo que más te gustó y con quién), la reseña de quien fue (si se abre desde su
// visita), los datos, «En tu lista desde…», «Ver reseñas (N)», «Sobre «plato»», «Lo que destacan», «Cómo llegar»,
// la eatlist (ventanita con el puesto), «Quitar de mi lista», Instagram | TikTok y «Buscar en Google».
import DateTimePicker, { DateTimePickerAndroid } from '@react-native-community/datetimepicker';
import { Image } from 'expo-image';
import { router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { Linking, Platform, Pressable, ScrollView, Text, TextInput, useWindowDimensions, View } from 'react-native';

import { Estrellas } from '@/components/estrellas';
import { Icono } from '@/components/icono';
import {
  Boton, Caja, Capa, Cargando, Etiqueta, Info, Pantalla, SelectorMultiple, Texto, TituloVentana, useAvisoBreve,
} from '@/components/ui';
import { api, Comensales, Ficha, mensaje, Resena, Tarjeta } from '@/lib/api';
import { useCarga } from '@/lib/carga';
import { compartirRestaurante } from '@/lib/compartir';
import { HUECO, LETRA, RADIO, TAM_PEQUENO, useColores } from '@/lib/tema';
import { olvidarVisitados } from '@/lib/visitados';

const MARGEN = 22.5;   // st.dialog
const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre',
  'noviembre', 'diciembre'];
const dos = (n: number) => String(n).padStart(2, '0');
const fechaCorta = (f: Date) => `${dos(f.getDate())}/${dos(f.getMonth() + 1)}/${f.getFullYear()}`;
const diaIso = (f: Date) => `${f.getFullYear()}-${dos(f.getMonth() + 1)}-${dos(f.getDate())}`;
const nota1 = (n: number) => String(Number(n)).replace('.', ',');   // f"{nota:g}": 4,5 / 4
const buscar = (q: string) => Linking.openURL(`https://www.google.com/search?q=${encodeURIComponent(q)}`);

/** logica.insertar_en_orden y vista_previa_posicion */
function insertarEnOrden(ids: number[], nuevo: number, puesto: number): number[] {
  const resto = ids.filter((i) => i !== nuevo);
  const p = Math.max(1, Math.min(puesto, resto.length + 1));
  return [...resto.slice(0, p - 1), nuevo, ...resto.slice(p - 1)];
}

function vistaPrevia(ids: number[], nuevo: number, puesto: number): [number, number, boolean][] {
  const orden = insertarEnOrden(ids, nuevo, puesto);
  const i = orden.indexOf(nuevo);
  const filas: [number, number, boolean][] = [];
  for (let j = Math.max(0, i - 1); j < Math.min(orden.length, i + 2); j += 1) filas.push([j + 1, orden[j], j === i]);
  return filas;
}

// ----------------------- fotos -----------------------

/** carrusel.css: fotos 3:2 que se deslizan una a una, con «2/5» abajo a la derecha. Una sola: st.image. */
function Fotos({ fotos }: { fotos: string[] }) {
  const { width } = useWindowDimensions();
  const ancho = width - MARGEN * 2;
  const [proporcion, setProporcion] = useState(1.5);   // st.image: la foto con su forma (se sabe al cargarla)
  if (fotos.length === 1) {
    return (
      <Image source={fotos[0]} style={{ width: ancho, aspectRatio: proporcion, borderRadius: RADIO }} contentFit="cover"
        onLoad={(e) => e.source.height && setProporcion(e.source.width / e.source.height)} />
    );
  }
  return (
    <ScrollView horizontal pagingEnabled={false} snapToInterval={ancho + 8} decelerationRate="fast"
      showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }} style={{ borderRadius: RADIO }}>
      {fotos.map((url, n) => (
        <View key={url}>
          <Image source={url} style={{ width: ancho, aspectRatio: 4 / 3, borderRadius: RADIO }} contentFit="cover" transition={150}
            accessibilityLabel={`Foto ${n + 1} de ${fotos.length}`} />
          <Text style={{ position: 'absolute', right: 8, bottom: 8, paddingHorizontal: 8, paddingVertical: 2, borderRadius: 999,
            overflow: 'hidden', backgroundColor: 'rgba(0,0,0,0.6)', color: '#fff', fontFamily: LETRA.normal, fontSize: 11.25 }}>
            {`${n + 1}/${fotos.length}`}
          </Text>
        </View>
      ))}
    </ScrollView>
  );
}

// ----------------------- «Ya he ido» -----------------------

/** st.date_input: la fecha en una caja; al tocarla, el calendario. */
function CampoFecha({ titulo, valor, alCambiar }: { titulo: string; valor: Date; alCambiar: (d: Date) => void }) {
  const c = useColores();
  const [abierto, setAbierto] = useState(false);
  return (
    <View>
      <Etiqueta texto={titulo} />
      <Pressable accessibilityRole="button" accessibilityLabel={`${titulo}: ${fechaCorta(valor)}`}
        onPress={() => (Platform.OS === 'android'
          ? DateTimePickerAndroid.open({ value: valor, mode: 'date', maximumDate: new Date(), onChange: (e, d) => e.type === 'set' && d && alCambiar(d) })
          : setAbierto(!abierto))}
        style={{ minHeight: 38, justifyContent: 'center', paddingHorizontal: 11.25, borderRadius: RADIO, borderWidth: 1,
          borderColor: c.borde, backgroundColor: c.fondo2 }}>
        <Text style={{ fontFamily: LETRA.normal, fontSize: TAM_PEQUENO, color: c.texto }}>{fechaCorta(valor)}</Text>
      </Pressable>
      {abierto && Platform.OS === 'ios' ? (
        <DateTimePicker value={valor} mode="date" display="inline" maximumDate={new Date()} locale="es-ES" accentColor={c.primario}
          onChange={(_, d) => { if (d) { alCambiar(d); setAbierto(false); } }} />
      ) : null}
    </View>
  );
}

/** app.selector_comensales: los que ya lo confirmaron, los pendientes (con «Quitar») y a quién más invitar. */
function ConQuien({ id, elegidos, alCambiar }: { id: number; elegidos: string[]; alCambiar: (x: string[]) => void }) {
  const comensales = useCarga(() => api<Comensales>('GET', `/visitas/${id}/comensales`), [id]);
  const d = comensales.datos;
  if (!d) return null;
  const quien = (p: { nombre: string; alias: string }) => `${p.nombre} (@${p.alias})`;
  return (
    <>
      {d.te_anadio ? <Texto tipo="suave">{`Fuiste con ${quien(d.te_anadio)}.`}</Texto> : null}
      {d.con.map((p) => <Texto key={p.alias} tipo="suave">{`Con ${quien(p)}`}</Texto>)}
      {d.pendientes.map((p) => (
        <View key={p.alias} style={{ flexDirection: 'row', alignItems: 'center', gap: HUECO }}>
          <Texto tipo="suave" style={{ flex: 1 }}>{`Con ${quien(p)} · pendiente de que lo confirme`}</Texto>
          <Boton texto="Quitar" tipo="texto" ancho="contenido"
            alPulsar={() => api('DELETE', `/visitas/${id}/comensales/${p.alias}`).then(comensales.recargar, comensales.recargar)} />
        </View>
      ))}
      {!d.opciones.length && !d.con.length && !d.pendientes.length && !d.te_anadio ? (
        <Texto tipo="suave">
          Con quién fuiste: añade amigos en <Text style={{ fontFamily: LETRA.negrita }}>Buscar → Personas</Text> para poder apuntarlos.
        </Texto>
      ) : null}
      {d.opciones.length ? (
        <SelectorMultiple titulo="Con quién fuiste" vacio="Escribe su nombre o @usuario (opcional)"
          opciones={d.opciones.map((p) => `${p.nombre} (@${p.alias})`)}
          elegidas={d.opciones.filter((p) => elegidos.includes(p.alias)).map((p) => `${p.nombre} (@${p.alias})`)}
          alCambiar={(marcadas) => alCambiar(d.opciones.filter((p) => marcadas.includes(`${p.nombre} (@${p.alias})`)).map((p) => p.alias))} />
      ) : null}
    </>
  );
}

function CapaVisita({ ficha, alCerrar, alGuardar }: { ficha: Ficha; alCerrar: () => void; alGuardar: (aviso: string) => void }) {
  const c = useColores();
  const v = ficha.mi_visita;
  const [nota, setNota] = useState<number | null>(v?.nota ?? null);
  const [fecha, setFecha] = useState(() => (v?.fecha ? new Date(v.fecha) : new Date()));
  const [comentario, setComentario] = useState(v?.comentario ?? '');
  const [con, setCon] = useState<string[]>([]);
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function hacer(quitar: boolean) {
    setError(null);
    setOcupado(true);
    try {
      if (quitar) {
        await api('DELETE', `/visitas/${ficha.id}`);
      } else {
        await api('PUT', `/visitas/${ficha.id}`, { nota, comentario: comentario.trim() || null, fecha: diaIso(fecha), con });
      }
      olvidarVisitados();
      alGuardar(quitar ? 'Ya no consta que hayas ido.'
        : `¡Guardado!${con.length ? ' Tus acompañantes tienen que confirmarlo; cuando lo hagan, les saldrá en su perfil.' : ''}`);
    } catch (e) {
      setError(mensaje(e));
    } finally {
      setOcupado(false);
    }
  }

  return (
    <Capa visible titulo="¿Qué tal fue?" alCerrar={alCerrar}>
      <Estrellas valor={nota} alCambiar={setNota} />
      <CampoFecha titulo="Cuándo fuiste" valor={fecha} alCambiar={setFecha} />
      <View>
        <Etiqueta texto="Lo que más te gustó" />
        <TextInput value={comentario} onChangeText={setComentario} multiline maxLength={1000}
          placeholder="Lo que más te gustó (opcional)" placeholderTextColor={c.textoSuave}
          style={{ minHeight: 68, borderRadius: RADIO, borderWidth: 1, borderColor: c.borde, backgroundColor: c.fondo2,
            paddingHorizontal: 11.25, paddingVertical: 7.5, fontFamily: LETRA.normal, fontSize: TAM_PEQUENO, color: c.texto,
            textAlignVertical: 'top' }} />
      </View>
      <ConQuien id={ficha.id} elegidos={con} alCambiar={setCon} />
      {error ? <Info tipo="error">{error}</Info> : null}
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: HUECO }}>
        <Boton texto="Guardar" tipo="primario" icono="check_circle" cargando={ocupado} style={{ flex: 1 }} alPulsar={() => hacer(false)} />
        {v ? <Boton texto="Ya no he ido" tipo="texto" icono="close" ancho="contenido" alPulsar={() => hacer(true)} /> : null}
      </View>
    </Capa>
  );
}

// ----------------------- reseñas -----------------------

/** app._resena: en una caja, quién, el día y sus estrellas, y su comentario. */
function CajaResena({ nombre, alias, nota, comentario, fecha }: {
  nombre: string; alias?: string | null; nota: number | null; comentario: string | null; fecha: string;
}) {
  return (
    <Caja>
      <Texto>
        <Text style={{ fontFamily: LETRA.negrita }}>{nombre}</Text>
        {alias ? ` · @${alias}` : ''}
        {`\n${fechaCorta(new Date(fecha))}${nota !== null ? ` · ★ ${nota1(nota)}` : ''}`}
      </Texto>
      {comentario ? <Texto>{`«${comentario}»`}</Texto> : null}
    </Caja>
  );
}

function CapaResenas({ ficha, alCerrar }: { ficha: Ficha; alCerrar: () => void }) {
  const resenas = useCarga(() => api<{ resenas: Resena[] }>('GET', `/restaurantes/${ficha.id}/resenas`), [ficha.id]);
  return (
    <Capa visible titulo="Reseñas" alCerrar={alCerrar}>
      <Texto tipo="suave">{ficha.nombre}</Texto>
      {resenas.cargando && !resenas.datos ? <Cargando /> : null}
      {resenas.datos?.resenas.map((r, n) => <CajaResena key={n} {...r} />)}
    </Capa>
  );
}

// ----------------------- eatlist -----------------------

/** st.number_input: el número con − y + a la derecha. */
function CampoNumero({ titulo, valor, min, max, alCambiar }: { titulo: string; valor: number; min: number; max: number; alCambiar: (n: number) => void }) {
  const c = useColores();
  const boton = (texto: string, nuevo: number) => (
    <Pressable accessibilityRole="button" accessibilityLabel={texto === '−' ? 'Uno menos' : 'Uno más'} disabled={nuevo < min || nuevo > max}
      onPress={() => alCambiar(nuevo)} style={{ width: 38, alignItems: 'center', justifyContent: 'center', opacity: nuevo < min || nuevo > max ? 0.4 : 1 }}>
      <Text style={{ fontSize: 20, color: c.texto }}>{texto}</Text>
    </Pressable>
  );
  return (
    <View>
      <Etiqueta texto={titulo} />
      <View style={{ flexDirection: 'row', minHeight: 38, borderRadius: RADIO, borderWidth: 1, borderColor: c.borde, backgroundColor: c.fondo2 }}>
        <TextInput value={String(valor)} keyboardType="number-pad" accessibilityLabel={titulo}
          onChangeText={(t) => { const n = parseInt(t, 10); if (!Number.isNaN(n)) alCambiar(Math.max(min, Math.min(max, n))); }}
          style={{ flex: 1, paddingHorizontal: 11.25, fontFamily: LETRA.normal, fontSize: TAM_PEQUENO, color: c.texto }} />
        {boton('−', valor - 1)}
        {boton('+', valor + 1)}
      </View>
    </View>
  );
}

function CapaEatlist({ ficha, orden, nombres, alCerrar, alGuardar }: {
  ficha: Ficha; orden: number[]; nombres: Map<number, string>; alCerrar: () => void; alGuardar: (aviso: string) => void;
}) {
  const c = useColores();
  const esta = orden.includes(ficha.id);
  const actual = esta ? orden.indexOf(ficha.id) + 1 : null;
  const ultimo = esta ? orden.length : orden.length + 1;
  const [puesto, setPuesto] = useState(actual ?? ultimo);
  const [error, setError] = useState<string | null>(null);
  const todos = new Map(nombres).set(ficha.id, ficha.nombre);

  async function guardar(quitar: boolean) {
    setError(null);
    const nuevo = quitar ? orden.filter((i) => i !== ficha.id) : insertarEnOrden(orden, ficha.id, puesto);
    try {
      await api('PUT', '/eatlist', { ids: nuevo });
      alGuardar(quitar ? 'Quitado de tu eatlist' : `Nº ${nuevo.indexOf(ficha.id) + 1} en tu eatlist`);
    } catch (e) {
      setError(mensaje(e));
    }
  }

  return (
    <Capa visible titulo="Tu eatlist" alCerrar={alCerrar}>
      <Texto>
        <Text style={{ fontFamily: LETRA.negrita }}>{ficha.nombre}</Text>
        {`\n${esta ? `Ahora es el nº ${actual} de tu eatlist.` : '¿En qué puesto lo quieres? (1 = el que más te apetece)'}`}
      </Texto>
      <CampoNumero titulo="En qué puesto" valor={puesto} min={1} max={ultimo} alCambiar={setPuesto} />
      {orden.length > (esta ? 1 : 0) ? (
        // global.css .eat-previa: así quedaría alrededor (el de antes, este y el de después)
        <View accessibilityLiveRegion="polite" style={{ marginTop: -4, paddingVertical: 6, paddingHorizontal: 10, borderRadius: 10,
          borderWidth: 1, borderStyle: 'dashed', borderColor: c.borde, backgroundColor: c.fondo2 }}>
          {vistaPrevia(orden, ficha.id, puesto).map(([n, i, este]) => (
            <View key={i} style={{ flexDirection: 'row', gap: 10, paddingVertical: 2, opacity: este ? 1 : 0.7 }}>
              <Text style={{ minWidth: 18, textAlign: 'right', fontFamily: este ? LETRA.negrita : LETRA.normal, fontSize: 13.2,
                color: este ? c.primario : c.texto }}>{n}</Text>
              <Text style={{ fontFamily: este ? LETRA.negrita : LETRA.normal, fontSize: 13.2, color: este ? c.primario : c.texto }}>
                {todos.get(i) ?? ''}
              </Text>
            </View>
          ))}
        </View>
      ) : null}
      {error ? <Info tipo="error">{error}</Info> : null}
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: HUECO }}>
        <Boton texto={esta ? 'Mover a este puesto' : 'Añadir a la eatlist'} tipo="primario" style={{ flex: 1 }}
          desactivado={esta && puesto === actual} alPulsar={() => guardar(false)} />
        {esta ? <Boton texto="Quitar" tipo="texto" ancho="contenido" alPulsar={() => guardar(true)} /> : null}
      </View>
    </Capa>
  );
}

// ----------------------- la ficha -----------------------

export default function FichaRestaurante() {
  const c = useColores();
  const p = useLocalSearchParams<{
    id: string; plato?: string; transporte?: string; minutos?: string; quien?: string; vnota?: string; vcomentario?: string; vfecha?: string;
  }>();
  const plato = p.plato?.trim() || '';
  const ficha = useCarga(() => api<Ficha>('GET', `/restaurantes/${p.id}`, undefined, { plato }), [p.id, plato]);
  const eatlist = useCarga(() => api<{ restaurantes: Tarjeta[] }>('GET', '/eatlist'), [p.id]);
  const [capa, setCapa] = useState<'visita' | 'resenas' | 'eatlist' | null>(null);
  const [confirmarQuitar, setConfirmarQuitar] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [aviso, avisar] = useAvisoBreve();
  const f = ficha.datos;

  // Abierta desde la visita de otra persona: su reseña arriba y otro fondo (global.css: .st-key-ficha_valorada)
  const deOtro = !!p.vfecha && p.quien !== 'Tú';
  const fondo = deOtro ? (c.texto === '#1F1A14' ? '#F5EADB' : '#241D16') : c.fondo;
  const cerrar = () => router.back();

  if (!f) {
    return (
      <Pantalla margen={MARGEN} fondo={fondo}>
        <TituloVentana titulo="" alCerrar={cerrar} />
        {ficha.error ? <Info tipo="error">{ficha.error}</Info> : <Cargando />}
      </Pantalla>
    );
  }

  const orden = (eatlist.datos?.restaurantes ?? []).map((t) => t.id);
  const nombres = new Map((eatlist.datos?.restaurantes ?? []).map((t) => [t.id, t.nombre]));
  const enEatlist = orden.includes(f.id);
  const v = f.mi_visita;
  const fotos = f.fotos.length ? f.fotos : f.foto ? [f.foto] : [];
  const transporte = p.transporte === 'En coche' || p.transporte === 'A pie' ? p.transporte : null;
  const lugar = [transporte && p.minutos ? `${transporte === 'En coche' ? '🚗' : '🚶'} ${p.minutos} min` : null, f.direccion]
    .filter(Boolean).join(' · ');
  const resumen = f.nota === null ? 'Sin nota' : `⭐ ${f.nota.toFixed(1).replace('.', ',')}${f.resenas !== null ? ` (${f.resenas})` : ''}`;
  const anadido = f.anadido_en ? new Date(f.anadido_en) : null;
  const verde = c.texto === '#1F1A14' ? '#15803D' : '#4ADE80';

  async function quitarDeMiLista() {
    setError(null);
    try {
      await api('DELETE', `/lista/${f!.id}`);
      router.back();
    } catch (e) {
      setError(mensaje(e));
    }
  }

  function comoLlegar() {
    let url = `https://www.google.com/maps/dir/?api=1&destination=${f!.lat},${f!.lon}`;
    if (transporte) url += `&travelmode=${transporte === 'En coche' ? 'driving' : 'walking'}`;
    Linking.openURL(url);
  }

  return (
    <View style={{ flex: 1, backgroundColor: fondo }}>
      <Pantalla margen={MARGEN} fondo={fondo}>
        <TituloVentana titulo={f.nombre} alCerrar={cerrar} extra={(
          <Pressable accessibilityRole="button" accessibilityLabel="Compartir" hitSlop={12} style={{ paddingTop: 8 }}
            onPress={() => compartirRestaurante(f.id, f.nombre, f.lat, f.lon)}>
            <Icono nombre="share" tam={18} color={c.texto} />
          </Pressable>
        )} />
        {fotos.length ? <Fotos fotos={fotos} /> : null}

        {/* «Ya he ido» / «Has ido · ★ 4,5 · 20/11/2026», en verde si ya has ido (global.css: st-key-visitado_) */}
        <Boton texto={v ? `Has ido${v.nota !== null ? ` · ★ ${nota1(v.nota)}` : ''}${v.fecha ? ` · ${fechaCorta(new Date(v.fecha))}` : ''}` : 'Ya he ido'}
          icono={v ? 'check_circle' : 'restaurant'} alPulsar={() => setCapa('visita')}
          style={v ? { backgroundColor: 'rgba(22, 163, 74, 0.10)', borderColor: '#16A34A' } : undefined}
          colorTexto={v ? verde : undefined} />
        {p.vfecha && (p.vnota || p.vcomentario) ? (
          <CajaResena nombre={p.quien ?? ''} nota={p.vnota ? Number(p.vnota) : null} comentario={p.vcomentario || null} fecha={p.vfecha} />
        ) : null}

        {f.cerrado ? (
          // st.badge gris con el reloj
          <View style={{ flexDirection: 'row', alignSelf: 'flex-start', alignItems: 'center', gap: 4, paddingHorizontal: 6,
            paddingVertical: 1, borderRadius: 6, backgroundColor: 'rgba(128, 132, 149, 0.1)' }}>
            <Icono nombre="schedule" tam={13} color="#808495" />
            <Text style={{ fontFamily: LETRA.normal, fontSize: TAM_PEQUENO, color: c.texto === '#1F1A14' ? '#555867' : '#BFC5D3' }}>{f.cerrado}</Text>
          </View>
        ) : null}

        <Texto>
          <Text style={{ fontFamily: LETRA.negrita }}>{f.cocina}</Text>
          {`\n${f.precio ?? 'Precio ?'} · ${resumen} reseñas`}
          {lugar ? `\n${lugar}` : ''}
        </Texto>
        {anadido ? (
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
            <Icono nombre="bookmark_added" tam={14} color={c.textoSuave} />
            <Texto tipo="suave">{`En tu lista desde el ${anadido.getDate()} de ${MESES[anadido.getMonth()]} de ${anadido.getFullYear()}`}</Texto>
          </View>
        ) : null}
        {f.num_resenas ? <Boton texto={`Ver reseñas (${f.num_resenas})`} icono="reviews" alPulsar={() => setCapa('resenas')} /> : null}

        {plato && f.sobre_plato ? (
          <Texto><Text style={{ fontFamily: LETRA.negrita }}>{`Sobre «${plato}»:`}</Text>{` ${f.sobre_plato}`}</Texto>
        ) : null}
        {f.platos.length ? (
          <View>
            <Texto tipo="negrita" style={{ fontFamily: LETRA.negrita }}>Lo que destacan</Texto>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 5, marginTop: 2 }}>
              {f.platos.map((x) => (
                <Text key={x} style={{ paddingHorizontal: 3.75, borderRadius: 6, overflow: 'hidden', backgroundColor: 'rgba(255, 164, 33, 0.1)',
                  color: c.texto === '#1F1A14' ? '#E2660C' : '#FFBD45', fontFamily: LETRA.normal, fontSize: TAM_PEQUENO, lineHeight: 21 }}>{x}</Text>
              ))}
            </View>
          </View>
        ) : null}

        <Boton texto="Cómo llegar" tipo="primario" icono="directions" alPulsar={comoLlegar} />
        <Boton texto={enEatlist ? `Nº ${orden.indexOf(f.id) + 1} en tu eatlist` : 'Añadir a mi eatlist'}
          icono={enEatlist ? 'bookmark_added' : 'bookmark_add'} alPulsar={() => setCapa('eatlist')} />

        {f.en_mi_lista && !confirmarQuitar ? (
          <Boton texto="Quitar de mi lista" tipo="texto" icono="playlist_remove" alPulsar={() => setConfirmarQuitar(true)}
            style={{ minHeight: 38 }} />
        ) : null}
        {f.en_mi_lista && confirmarQuitar ? (
          <>
            <Texto tipo="suave">
              Dejará de estar en tu lista (si vuelves a sincronizarla y sigue en tu lista de Google Maps, volverá). No se borra de la
              app: sigue para los demás y en tus valoraciones.
            </Texto>
            <View style={{ flexDirection: 'row', gap: HUECO }}>
              <Boton texto="Sí, quitar" tipo="primario" ancho="contenido" alPulsar={quitarDeMiLista} />
              <Boton texto="Cancelar" ancho="contenido" alPulsar={() => setConfirmarQuitar(false)} />
            </View>
          </>
        ) : null}
        {error ? <Info tipo="error">{error}</Info> : null}

        {/* Instagram/TikTok no tienen búsqueda fiable sin cuenta: el operador site: de Google */}
        <View style={{ flexDirection: 'row', gap: HUECO }}>
          <Boton texto="Instagram" ancho="contenido" style={{ flexGrow: 1 }} alPulsar={() => buscar(`site:instagram.com "${f.nombre}" Madrid`)} />
          <Boton texto="TikTok" ancho="contenido" style={{ flexGrow: 1 }} alPulsar={() => buscar(`site:tiktok.com "${f.nombre}" Madrid`)} />
        </View>
        <Boton texto="Buscar en Google" tipo="texto" icono="search" style={{ minHeight: 38 }} alPulsar={() => buscar(`${f.nombre} Madrid`)} />
      </Pantalla>

      {capa === 'visita' ? (
        <CapaVisita ficha={f} alCerrar={() => setCapa(null)}
          alGuardar={(t) => { setCapa(null); avisar(t); ficha.recargar(); eatlist.recargar(); }} />
      ) : null}
      {capa === 'resenas' ? <CapaResenas ficha={f} alCerrar={() => setCapa(null)} /> : null}
      {capa === 'eatlist' ? (
        <CapaEatlist ficha={f} orden={orden} nombres={nombres} alCerrar={() => setCapa(null)}
          alGuardar={(t) => { setCapa(null); avisar(t); eatlist.recargar(); }} />
      ) : null}
      {aviso}
    </View>
  );
}
