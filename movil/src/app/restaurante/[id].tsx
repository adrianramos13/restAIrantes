// Ficha de un restaurante: fotos, datos, «Ya he ido» (estrellas, fecha, comentario y con quién), reseñas de la
// gente de la app, eatlist, cómo llegar, compartir, quitar de tu lista y buscarlo en Instagram/TikTok/Google.
import DateTimePicker from '@react-native-community/datetimepicker';
import { Image } from 'expo-image';
import { router, Stack, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { Alert, Linking, Platform, ScrollView, useWindowDimensions, View } from 'react-native';

import { Estrellas } from '@/components/estrellas';
import { formatoNota } from '@/components/tarjeta';
import { Boton, Caja, Campo, Cargando, Chips, Pantalla, Seccion, Texto } from '@/components/ui';
import { api, Comensales, Ficha, mensaje, Resena, Tarjeta } from '@/lib/api';
import { useCarga } from '@/lib/carga';
import { compartirRestaurante } from '@/lib/compartir';
import { ESPACIO, RADIO } from '@/lib/tema';

const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre',
  'noviembre', 'diciembre'];

function fechaLarga(iso: string): string {
  const f = new Date(iso);
  return `${f.getDate()} de ${MESES[f.getMonth()]} de ${f.getFullYear()}`;
}

function buscarEnGoogle(consulta: string) {
  Linking.openURL(`https://www.google.com/search?q=${encodeURIComponent(consulta)}`);
}

function Galeria({ fotos }: { fotos: string[] }) {
  const { width } = useWindowDimensions();
  const ancho = width - ESPACIO * 2;
  return (
    <ScrollView horizontal pagingEnabled showsHorizontalScrollIndicator={false} style={{ borderRadius: RADIO }}>
      {fotos.map((url, n) => (
        <View key={url}>
          <Image source={url} style={{ width: ancho, height: ancho * 0.66 }} contentFit="cover" transition={150} />
          {fotos.length > 1 ? (
            <Texto tipo="suave" style={{ position: 'absolute', right: 10, bottom: 8, color: '#fff' }}>
              {`${n + 1}/${fotos.length}`}
            </Texto>
          ) : null}
        </View>
      ))}
    </ScrollView>
  );
}

function diaIso(f: Date): string {   // la fecha local (no UTC) en AAAA-MM-DD, como la espera la API
  return `${f.getFullYear()}-${String(f.getMonth() + 1).padStart(2, '0')}-${String(f.getDate()).padStart(2, '0')}`;
}

function Acompanantes({ id, elegidos, alCambiar }: { id: number; elegidos: string[]; alCambiar: (x: string[]) => void }) {
  const comensales = useCarga(() => api<Comensales>('GET', `/visitas/${id}/comensales`), [id]);
  const d = comensales.datos;
  if (!d) return comensales.cargando ? <Cargando /> : null;
  const yaCon = [
    ...(d.te_anadio ? [`Fuiste con @${d.te_anadio.alias}`] : []),
    ...d.con.map((p) => `Con @${p.alias}`),
  ];
  return (
    <View style={{ gap: 8 }}>
      {yaCon.length ? <Texto tipo="suave">{yaCon.join(' · ')}</Texto> : null}
      {d.pendientes.map((p) => (
        <View key={p.alias} style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <Texto tipo="suave" style={{ flex: 1 }}>{`Con @${p.alias} · pendiente de que lo confirme`}</Texto>
          <Boton texto="Quitar" tipo="texto"
            alPulsar={() => api('DELETE', `/visitas/${id}/comensales/${p.alias}`).then(comensales.recargar, comensales.recargar)} />
        </View>
      ))}
      {d.opciones.length ? (
        <>
          <Texto tipo="suave">¿Con quién fuiste? Tendrán que confirmarlo.</Texto>
          <Chips opciones={d.opciones.map((p) => p.alias)} elegidas={elegidos} etiqueta={(a) => `@${a}`}
            alElegir={(a) => alCambiar(elegidos.includes(a) ? elegidos.filter((x) => x !== a) : [...elegidos, a])} />
        </>
      ) : !d.con.length && !d.pendientes.length ? (
        <Texto tipo="suave">Añade amigos para poder apuntar con quién fuiste.</Texto>
      ) : null}
    </View>
  );
}

function YaHeIdo({ ficha, alGuardar }: { ficha: Ficha; alGuardar: () => void }) {
  const [abierto, setAbierto] = useState(false);
  const [nota, setNota] = useState<number | null>(ficha.mi_visita?.nota ?? null);
  const [comentario, setComentario] = useState(ficha.mi_visita?.comentario ?? '');
  const [fecha, setFecha] = useState(() => (ficha.mi_visita?.fecha ? new Date(ficha.mi_visita.fecha) : new Date()));
  const [con, setCon] = useState<string[]>([]);
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  async function hacer(accion: () => Promise<{ invitados?: number } | unknown>) {
    setError(null);
    setOcupado(true);
    try {
      const r = (await accion()) as { invitados?: number } | undefined;
      setAbierto(false);
      setCon([]);
      setAviso(r?.invitados ? 'Guardado. Tus acompañantes tienen que confirmarlo; cuando lo hagan, les saldrá en su perfil.' : null);
      alGuardar();
    } catch (e) {
      setError(mensaje(e));
    } finally {
      setOcupado(false);
    }
  }

  if (!abierto) {
    return (
      <View style={{ gap: 6 }}>
        <Boton
          texto={ficha.mi_visita ? `✓ Has ido${ficha.mi_visita.nota !== null ? ` · ${formatoNota(ficha.mi_visita.nota)}` : ''} · Editar` : 'Ya he ido'}
          tipo="secundario"
          alPulsar={() => setAbierto(true)}
        />
        {aviso ? <Texto tipo="suave">{aviso}</Texto> : null}
      </View>
    );
  }
  return (
    <Caja>
      <Texto tipo="subtitulo">¿Qué tal fue?</Texto>
      <Estrellas valor={nota} alCambiar={setNota} />
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
        <Texto tipo="suave">Cuándo fuiste</Texto>
        <DateTimePicker value={fecha} mode="date" display="compact" maximumDate={new Date()} locale="es-ES"
          onChange={(_, elegida) => elegida && setFecha(elegida)} />
      </View>
      <Campo placeholder="Lo que más te gustó (opcional)" value={comentario} onChangeText={setComentario} multiline maxLength={1000} />
      <Acompanantes id={ficha.id} elegidos={con} alCambiar={setCon} />
      {error ? <Texto tipo="error">{error}</Texto> : null}
      <Boton texto="Guardar" cargando={ocupado}
        alPulsar={() => hacer(() => api('PUT', `/visitas/${ficha.id}`, {
          nota, comentario: comentario.trim() || null, fecha: diaIso(fecha), con,
        }))} />
      {ficha.mi_visita ? (
        <Boton texto="Ya no he ido (quitar)" tipo="texto" alPulsar={() => hacer(() => api('DELETE', `/visitas/${ficha.id}`))} />
      ) : null}
      <Boton texto="Cancelar" tipo="texto" alPulsar={() => setAbierto(false)} />
    </Caja>
  );
}

function Resenas({ id, total }: { id: number; total: number }) {
  const [abiertas, setAbiertas] = useState(false);
  const resenas = useCarga(
    () => (abiertas ? api<{ resenas: Resena[] }>('GET', `/restaurantes/${id}/resenas`) : Promise.resolve(null)),
    [abiertas, id],
  );
  if (!total) return null;
  if (!abiertas) return <Boton texto={`Ver reseñas (${total})`} tipo="secundario" alPulsar={() => setAbiertas(true)} />;
  return (
    <Seccion titulo="Reseñas">
      {resenas.cargando ? <Cargando /> : null}
      {resenas.datos?.resenas.map((r, n) => (
        <Caja key={n}>
          <Texto tipo="subtitulo" style={{ fontSize: 15 }}>
            {[r.nombre, r.alias ? `@${r.alias}` : null].filter(Boolean).join(' · ')}
          </Texto>
          <Texto tipo="suave">{[r.nota !== null ? formatoNota(r.nota) : null, fechaLarga(r.fecha)].filter(Boolean).join(' · ')}</Texto>
          {r.comentario ? <Texto>{r.comentario}</Texto> : null}
        </Caja>
      ))}
    </Seccion>
  );
}

export default function FichaRestaurante() {
  const { id, plato } = useLocalSearchParams<{ id: string; plato?: string }>();
  const ficha = useCarga(() => api<Ficha>('GET', `/restaurantes/${id}`, undefined, { plato }), [id, plato]);
  const [eatlistTocada, setEatlistTocada] = useState<boolean | null>(null);   // lo que has cambiado aquí
  const [error, setError] = useState<string | null>(null);
  const f = ficha.datos;
  const enEatlist = eatlistTocada ?? f?.en_eatlist ?? false;

  async function cambiarEatlist() {
    if (!f) return;
    setError(null);
    try {
      const actual = await api<{ restaurantes: Tarjeta[] }>('GET', '/eatlist');
      const ids = actual.restaurantes.map((t) => t.id).filter((x) => x !== f.id);
      await api('PUT', '/eatlist', { ids: enEatlist ? ids : [...ids, f.id] });
      setEatlistTocada(!enEatlist);
    } catch (e) {
      setError(mensaje(e));
    }
  }

  function quitarDeMiLista() {
    if (!f) return;
    Alert.alert(
      'Quitar de mi lista',
      'Dejará de estar en tu lista (si vuelves a sincronizarla y sigue en tu lista de Google Maps, volverá). No se borra de la app.',
      [
        { text: 'Cancelar', style: 'cancel' },
        {
          text: 'Sí, quitar',
          style: 'destructive',
          onPress: async () => {
            try {
              await api('DELETE', `/lista/${f.id}`);
              router.back();
            } catch (e) {
              setError(mensaje(e));
            }
          },
        },
      ],
    );
  }

  function comoLlegar() {
    if (!f || f.lat === null || f.lon === null) return;
    const destino = `${f.lat},${f.lon}`;
    Linking.openURL(
      Platform.OS === 'ios'
        ? `https://maps.apple.com/?daddr=${destino}`
        : `https://www.google.com/maps/dir/?api=1&destination=${destino}`,
    );
  }

  if (ficha.cargando && !f) return <Pantalla><Cargando /></Pantalla>;
  if (!f) return <Pantalla><Texto tipo="error">{ficha.error ?? 'No se ha encontrado.'}</Texto></Pantalla>;

  const fotos = f.fotos.length ? f.fotos : f.foto ? [f.foto] : [];
  return (
    <Pantalla>
      <Stack.Screen options={{ title: f.nombre }} />
      {fotos.length ? <Galeria fotos={fotos} /> : null}
      <YaHeIdo key={f.mi_visita?.fecha ?? 'nueva'} ficha={f} alGuardar={ficha.recargar} />

      <View style={{ gap: 4 }}>
        <Texto tipo="titulo">{f.nombre}</Texto>
        {f.cerrado ? <Texto tipo="error">{f.cerrado}</Texto> : null}
        <Texto tipo="subtitulo" style={{ fontSize: 16 }}>{f.cocina}</Texto>
        <Texto tipo="suave">
          {[f.precio ?? 'Precio ?', `${formatoNota(f.nota)}${f.resenas ? ` (${f.resenas} reseñas)` : ''}`].join(' · ')}
        </Texto>
        {f.direccion ? <Texto tipo="suave">{f.direccion}</Texto> : null}
        {f.anadido_en ? <Texto tipo="suave">{`En tu lista desde el ${fechaLarga(f.anadido_en)}`}</Texto> : null}
      </View>

      <Resenas id={f.id} total={f.num_resenas} />
      {plato && f.sobre_plato ? <Texto>{`Sobre «${plato}»: ${f.sobre_plato}`}</Texto> : null}
      {f.platos.length ? (
        <Seccion titulo="Lo que destacan">
          <Texto>{f.platos.join(' · ')}</Texto>
        </Seccion>
      ) : null}

      {error ? <Texto tipo="error">{error}</Texto> : null}
      <Boton texto="Cómo llegar" alPulsar={comoLlegar} />
      <Boton texto={enEatlist ? '✓ En tu eatlist (quitar)' : 'Añadir a mi eatlist'} tipo="secundario" alPulsar={cambiarEatlist} />
      <View style={{ flexDirection: 'row', gap: 10 }}>
        <View style={{ flex: 1 }}>
          <Boton texto="Instagram" tipo="secundario" alPulsar={() => buscarEnGoogle(`site:instagram.com "${f.nombre}" Madrid`)} />
        </View>
        <View style={{ flex: 1 }}>
          <Boton texto="TikTok" tipo="secundario" alPulsar={() => buscarEnGoogle(`site:tiktok.com "${f.nombre}" Madrid`)} />
        </View>
      </View>
      <Boton texto="Compartir" tipo="secundario" alPulsar={() => compartirRestaurante(f.nombre, f.lat, f.lon)} />
      <Boton texto="Buscar en Google" tipo="texto" alPulsar={() => buscarEnGoogle(`${f.nombre} Madrid`)} />
      {f.en_mi_lista ? <Boton texto="Quitar de mi lista" tipo="texto" alPulsar={quitarDeMiLista} /> : null}
    </Pantalla>
  );
}
