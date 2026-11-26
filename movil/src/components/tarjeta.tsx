// Las tarjetas de la web (componentes/lista.css/js, app.mostrar_lista): foto (o el icono de su cocina) con su
// número, nombre en Fraunces, cocina, «precio · ⭐ nota (reseñas)», quién fue y sus estrellas, su comentario,
// etiquetas (estado del análisis, cerrado, «✓ Has ido») y la flecha. Variantes: `carrusel` (estrechas, en fila:
// «Tus amigos han ido a») y `poster` (tiras con la foto redonda: «Lo mejor de la semana»).
import { Image } from 'expo-image';
import { router } from 'expo-router';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { Tarjeta } from '@/lib/api';
import { LETRA, useColores } from '@/lib/tema';
import { useVisitados } from '@/lib/visitados';

export function formatoNota(nota: number | null): string {
  return nota === null ? 'Sin nota' : `★ ${nota.toFixed(1).replace('.', ',')}`;
}

/** app.resumen_valoracion: «⭐ 4,5 (1147)» o «Sin nota». */
export function resumenValoracion(t: Pick<Tarjeta, 'nota' | 'resenas'>): string {
  if (t.nota === null) return 'Sin nota';
  return `⭐ ${t.nota.toFixed(1).replace('.', ',')}${t.resenas !== null ? ` (${t.resenas})` : ''}`;
}

const mayuscula = (t: string | null | undefined) => (t ? t[0].toUpperCase() + t.slice(1) : '');

/** Las cinco estrellas grises con las doradas encima hasta la nota, y el número (.lr-estrellas). */
export function Estrellas({ nota, tam = 16, texto = 13 }: { nota: number; tam?: number; texto?: number }) {
  const c = useColores();
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: tam > 14 ? 6 : 4 }}>
      <View>
        <Text style={{ fontSize: tam, lineHeight: tam + 2, color: c.borde }}>★★★★★</Text>
        <View style={[StyleSheet.absoluteFill, { width: `${(nota / 5) * 100}%`, overflow: 'hidden' }]}>
          <Text style={{ fontSize: tam, lineHeight: tam + 2, color: c.estrella, width: tam * 5 + 4 }}>★★★★★</Text>
        </View>
      </View>
      <Text style={{ fontFamily: LETRA.normal, fontSize: texto, color: c.texto }}>{String(nota).replace('.', ',')}</Text>
    </View>
  );
}

export type EstadoLugar = 'analizado' | 'pendiente' | 'procesando' | 'error' | 'sin_analizar' | 'cerrado';

/** Lo que lista.js recibe de cada tarjeta. */
export interface ItemLista {
  id: number | string;
  n?: number;
  nombre: string;
  cocina: string;
  meta: string;
  foto: string | null;
  icono?: string;          // Descubrir: emoji de su cocina cuando no hay foto
  amigo?: string | null;
  cuando?: string | null;
  nota?: number | null;
  cita?: string | null;
  estado?: EstadoLugar;
  estadoTexto?: string;
  cerrado?: string | null;
  visitado?: boolean;
}

const ESTADO_CLARO: Partial<Record<EstadoLugar, [string, string]>> = {
  analizado: ['#DCFCE7', '#14532D'], pendiente: ['#FFEDD5', '#7C2D12'], procesando: ['#FFEDD5', '#7C2D12'],
  error: ['#FEE2E2', '#7F1D1D'],
};

function Etiqueta({ texto, fondo, color }: { texto: string; fondo: string; color: string }) {
  return <Text style={[estilos.etiqueta, { backgroundColor: fondo, color }]}>{texto}</Text>;
}

interface PropsLista {
  item: ItemLista;
  alTocar: () => void;
  variante?: 'normal' | 'carrusel' | 'poster';
}

export function TarjetaLista({ item: r, alTocar, variante = 'normal' }: PropsLista) {
  const c = useColores();
  const oscuro = c.fondo !== '#FBF7F2';
  const carrusel = variante === 'carrusel';
  const poster = variante === 'poster';
  const etiquetaColores = (estado: EstadoLugar): [string, string] => {
    const par = ESTADO_CLARO[estado];
    if (!par) return [c.borde, c.texto];
    return oscuro ? [par[1], par[0]] : par;
  };
  const verde: [string, string] = oscuro ? ['#14532D', '#DCFCE7'] : ['#DCFCE7', '#14532D'];
  const fotoEstilo = [estilos.foto, carrusel && estilos.fotoCarrusel, poster && estilos.fotoPoster];
  const foto = r.foto ? (
    <Image source={r.foto} style={fotoEstilo} contentFit="cover" transition={150} />
  ) : (
    <View style={[fotoEstilo, estilos.inicial, r.icono ? { backgroundColor: c.borde } : { backgroundColor: c.primario, opacity: 0.85 }]}>
      <Text style={r.icono ? { fontSize: 36 } : [estilos.textoInicial, { color: c.fondo }]}>
        {r.icono ?? (r.nombre.trim()[0] ?? '?').toUpperCase()}
      </Text>
    </View>
  );
  const partes = [r.amigo ? `${r.amigo} fue ${r.cuando ?? ''}` : mayuscula(r.cuando), `${r.n ? `${r.n}. ` : ''}${r.nombre}`,
    r.cocina, r.meta, r.nota != null ? `${String(r.nota).replace('.', ',')} de 5 estrellas` : null, r.cita ? `«${r.cita}»` : null,
    r.estadoTexto, r.cerrado, r.visitado ? 'Has ido' : null, 'Ver ficha'];

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={partes.filter(Boolean).join('. ')}
      onPress={alTocar}
      style={({ pressed }) => [
        estilos.tarjeta, carrusel && estilos.tarjetaCarrusel, poster && estilos.tarjetaPoster,
        { backgroundColor: c.fondo2, borderColor: r.visitado ? '#16A34A' : c.borde, opacity: r.cerrado ? 0.6 : 1,
          transform: [{ scale: pressed ? 0.985 : 1 }] },
      ]}>
      <View>
        {foto}
        {r.n && !carrusel ? (
          <View style={[estilos.num, { backgroundColor: c.primario, borderColor: c.fondo2 }]}>
            <Text style={[estilos.textoNum, { color: c.fondo }]}>{r.n}</Text>
          </View>
        ) : null}
      </View>

      {poster ? (
        <View style={[estilos.info, { gap: 6 }]}>
          <View style={[estilos.barra, { borderColor: c.borde, backgroundColor: c.fondo }]}>
            <Text style={[estilos.nombre, { fontSize: 15, lineHeight: 19, color: c.texto }]} numberOfLines={1}>{r.nombre}</Text>
            <Text style={[estilos.pequeno, { fontSize: 12, opacity: 0.8, color: c.texto }]} numberOfLines={1}>{r.meta}</Text>
          </View>
          <View style={{ flexDirection: 'row', gap: 6 }}>
            <View style={[estilos.barra, { gap: 2, borderColor: c.borde, backgroundColor: c.fondo }]}>
              <Text style={[estilos.amigo, { fontSize: 12, maxWidth: 110, color: c.primario }]} numberOfLines={1}>{r.amigo ?? ''}</Text>
              {r.nota != null ? <Estrellas nota={r.nota} tam={13} texto={12} /> : null}
            </View>
            <View style={[estilos.barra, { flex: 1, borderColor: c.borde, backgroundColor: c.fondo }]}>
              <Text style={[estilos.cita, { fontSize: 12, opacity: 0.9, color: c.texto }]} numberOfLines={2}>
                {r.cita ? `«${r.cita}»` : mayuscula(r.cuando)}
              </Text>
            </View>
          </View>
        </View>
      ) : (
        <View style={estilos.info}>
          {r.amigo || r.cuando ? (
            <View style={carrusel ? undefined : estilos.quien}>
              {r.amigo ? <Text style={[estilos.amigo, { color: c.primario }]} numberOfLines={1}>{r.amigo}</Text> : null}
              <Text style={[estilos.pequeno, { color: c.texto, opacity: 0.7 }]}>{mayuscula(r.cuando)}</Text>
            </View>
          ) : null}
          <Text style={[estilos.nombre, carrusel && { fontSize: 15, lineHeight: 19 }, { color: c.texto }]} numberOfLines={2}>{r.nombre}</Text>
          <Text style={[estilos.pequeno, { color: c.texto, opacity: 0.75 }]} numberOfLines={1}>{r.cocina}</Text>
          <Text style={[estilos.pequeno, { color: c.texto }]} numberOfLines={1}>{r.meta}</Text>
          {r.nota != null ? <Estrellas nota={r.nota} /> : null}
          {r.cita ? <Text style={[estilos.cita, { color: c.texto }]} numberOfLines={2}>{`«${r.cita}»`}</Text> : null}
          {r.estado && r.estadoTexto ? <Etiqueta texto={r.estadoTexto} fondo={etiquetaColores(r.estado)[0]} color={etiquetaColores(r.estado)[1]} /> : null}
          {r.visitado ? <Etiqueta texto="✓ Has ido" fondo={verde[0]} color={verde[1]} /> : null}
          {r.cerrado ? <Etiqueta texto={r.cerrado} fondo={c.borde} color={c.texto} /> : null}
        </View>
      )}
      {carrusel || poster ? null : <Text style={[estilos.flecha, { color: c.texto }]}>›</Text>}
    </Pressable>
  );
}

interface Props {
  tarjeta: Tarjeta;
  n?: number;                       // el número de la esquina (posición en la lista)
  transporte?: 'En coche' | 'A pie';
  plato?: string;
  variante?: 'normal' | 'carrusel' | 'poster';
  alTocar?: () => void;             // por defecto, abre su ficha
  cuando?: string;                  // la línea de arriba sin visita: «añadido el 12/10/2025» (app.cuando_anadido)
}

/** Abre su ficha. Si la tarjeta es la visita de alguien (sus estrellas y su comentario), la ficha la enseña arriba
 * (app.resena_de_la_visita) y, si no es tuya, con otro fondo (.st-key-ficha_valorada). */
export function abrirFicha(t: Tarjeta, plato?: string, transporte?: 'En coche' | 'A pie'): void {
  const v = t.visita;
  router.push({ pathname: '/restaurante/[id]', params: {
    id: String(t.id), plato: plato ?? '',
    // de una búsqueda: el tiempo de viaje y el modo para «Cómo llegar»
    ...(transporte && t.minutos !== undefined ? { transporte, minutos: String(Math.round(t.minutos)) } : {}),
    ...(v?.fecha ? { quien: v.quien ?? 'Tú', vnota: v.nota !== null ? String(v.nota) : '', vcomentario: v.comentario ?? '', vfecha: v.fecha } : {}),
  } });
}

/** Un restaurante del catálogo como lo pinta app.mostrar_lista (con «✓ Has ido» si has ido). */
export function TarjetaRestaurante({ tarjeta: t, n, transporte, plato, variante = 'normal', alTocar, cuando }: Props) {
  const visitados = useVisitados();
  let meta = `${t.precio ?? 'Precio ?'} · ${resumenValoracion(t)}`;
  if (transporte && t.minutos !== undefined) meta += ` · ${transporte === 'En coche' ? '🚗' : '🚶'} ${Math.round(t.minutos)}'`;
  const v = t.visita;
  const item: ItemLista = {
    id: t.id, n, nombre: t.nombre, cocina: t.cocina, meta, foto: t.foto, cerrado: t.cerrado, visitado: visitados.has(t.id),
    amigo: v?.quien, cuando: v?.cuando ?? cuando, nota: v?.nota, cita: v?.comentario,
  };
  return (
    <TarjetaLista item={item} variante={variante} alTocar={alTocar ?? (() => abrirFicha(t, plato, transporte))} />
  );
}

/** La columna de tarjetas (.lr: 8 px entre una y otra). */
export function ListaTarjetas({ children }: { children: React.ReactNode }) {
  return <View style={{ gap: 8 }}>{children}</View>;
}

const estilos = StyleSheet.create({
  tarjeta: {
    flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 8, paddingLeft: 8, paddingRight: 10,
    minHeight: 88, borderWidth: 1, borderRadius: 12,
  },
  tarjetaCarrusel: { width: 160, flexDirection: 'column', alignItems: 'stretch', gap: 8, padding: 8, paddingLeft: 8, paddingRight: 8, minHeight: 0 },
  tarjetaPoster: { gap: 10, padding: 8, paddingLeft: 8, paddingRight: 8, minHeight: 0, borderRadius: 18 },
  foto: { width: 72, height: 72, borderRadius: 10 },
  fotoCarrusel: { width: '100%', height: 100 },
  fotoPoster: { width: 64, height: 64, borderRadius: 32 },
  inicial: { alignItems: 'center', justifyContent: 'center' },
  textoInicial: { fontFamily: LETRA.negrita, fontSize: 28 },
  num: {
    position: 'absolute', left: -6, top: -6, minWidth: 22, height: 22, paddingHorizontal: 5, borderRadius: 11,
    borderWidth: 2, alignItems: 'center', justifyContent: 'center',
  },
  textoNum: { fontFamily: LETRA.negrita, fontSize: 12 },
  info: { flex: 1, minWidth: 0, gap: 2 },
  quien: { flexDirection: 'row', alignItems: 'baseline', gap: 6 },
  amigo: { fontFamily: LETRA.negrita, fontSize: 14, flexShrink: 1 },
  nombre: { fontFamily: LETRA.tituloSemi, fontSize: 17, lineHeight: 21.25 },
  pequeno: { fontFamily: LETRA.normal, fontSize: 13, lineHeight: 17.5 },
  cita: { fontFamily: LETRA.italica, fontSize: 13, lineHeight: 17.5, opacity: 0.85 },
  etiqueta: {
    alignSelf: 'flex-start', marginTop: 2, paddingHorizontal: 8, paddingVertical: 1, borderRadius: 999, overflow: 'hidden',
    fontFamily: LETRA.semi, fontSize: 11,
  },
  barra: { justifyContent: 'center', gap: 1, minWidth: 0, paddingVertical: 4, paddingHorizontal: 10, borderRadius: 10, borderWidth: 1 },
  flecha: { fontSize: 22, opacity: 0.4 },
});
