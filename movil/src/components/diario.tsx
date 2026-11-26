// Perfil, «Diario» y «Eatlist» (componentes/diario.*): como un diario estilo Letterboxd. Cabecera por mes y, en
// cada fila, un recuadro con el día (o el puesto en la eatlist), la foto, el nombre con su cocina, la nota en
// estrellas y un icono si tiene comentario. Al tocar una fila se abre su ficha.
import { Image } from 'expo-image';
import { Fragment } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { Icono } from '@/components/icono';
import { LETRA, useColores } from '@/lib/tema';

export interface FilaDiario {
  id: number;
  caja: string;           // el día del mes o el puesto
  nombre: string;
  detalle: string;        // su cocina
  foto: string | null;
  nota: number | null;
  comentario: boolean;
}

export interface GrupoDiario {
  titulo: string | null;  // «noviembre 2026»
  filas: FilaDiario[];
}

interface Props {
  grupos: GrupoDiario[];
  puestos?: boolean;      // Eatlist: el recuadro es el puesto, en terracota
  alTocar: (id: number) => void;
}

function Estrellas({ nota }: { nota: number }) {
  const c = useColores();
  return (
    <View accessibilityElementsHidden importantForAccessibility="no-hide-descendants">
      <Text style={{ fontSize: 16, lineHeight: 17, color: c.borde }}>★★★★★</Text>
      <View style={[StyleSheet.absoluteFill, { width: `${(nota / 5) * 100}%`, overflow: 'hidden' }]}>
        <Text style={{ fontSize: 16, lineHeight: 17, color: '#F5A524', width: 84 }}>★★★★★</Text>
      </View>
    </View>
  );
}

export function Diario({ grupos, puestos = false, alTocar }: Props) {
  const c = useColores();
  return (
    <View>
      {grupos.map((g, i) => (
        <Fragment key={g.titulo ?? i}>
          {g.titulo ? (
            <View style={[estilos.mes, { backgroundColor: c.fondo2, marginTop: i ? 14 : 0 }]}>
              <Text style={[estilos.textoMes, { color: c.texto }]}>{g.titulo.toUpperCase()}</Text>
            </View>
          ) : null}
          {g.filas.map((r) => (
            <Pressable
              key={`${r.id}-${r.caja}`}
              accessibilityRole="button"
              accessibilityLabel={[puestos ? `Puesto ${r.caja}` : `Día ${r.caja}`, r.nombre, r.detalle,
                r.nota != null ? `${String(r.nota).replace('.', ',')} de 5 estrellas` : null, r.comentario ? 'Con comentario' : null,
                'Ver ficha'].filter(Boolean).join('. ')}
              onPress={() => alTocar(r.id)}
              style={({ pressed }) => [estilos.fila, { borderBottomColor: c.borde, backgroundColor: pressed ? c.fondo2 : 'transparent' }]}>
              <View style={[estilos.caja, { borderColor: c.borde }]}>
                <Text style={[estilos.textoCaja, puestos ? { fontFamily: LETRA.semi, color: c.primario } : { color: c.texto }]}>{r.caja}</Text>
              </View>
              <View style={[estilos.foto, { backgroundColor: c.primario }]}>
                <Text style={estilos.inicial}>{(r.nombre.trim()[0] ?? '?').toUpperCase()}</Text>
                {r.foto ? <Image source={r.foto} style={StyleSheet.absoluteFill} contentFit="cover" /> : null}
              </View>
              <View style={estilos.info}>
                <Text style={[estilos.nombre, { color: c.texto }]}>
                  {`${r.nombre} `}
                  {r.detalle ? <Text style={[estilos.detalle, { color: c.texto }]}>{r.detalle}</Text> : null}
                </Text>
                {r.nota != null || r.comentario ? (
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                    {r.nota != null ? <Estrellas nota={r.nota} /> : null}
                    {r.comentario ? <View style={{ opacity: 0.6 }}><Icono nombre="comentario" tam={16} color={c.texto} /></View> : null}
                  </View>
                ) : null}
              </View>
            </Pressable>
          ))}
        </Fragment>
      ))}
    </View>
  );
}

const estilos = StyleSheet.create({
  mes: { paddingVertical: 8, paddingHorizontal: 12, borderRadius: 8, opacity: 0.85 },
  textoMes: { fontFamily: LETRA.semi, fontSize: 13, letterSpacing: 1.56 },
  fila: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 10, paddingHorizontal: 4, borderBottomWidth: 1 },
  caja: { width: 48, height: 54, borderWidth: 1, borderRadius: 6, alignItems: 'center', justifyContent: 'center' },
  textoCaja: { fontFamily: LETRA.fina, fontSize: 24, fontVariant: ['tabular-nums'] },
  foto: { width: 54, height: 54, borderRadius: 8, overflow: 'hidden', alignItems: 'center', justifyContent: 'center' },
  inicial: { fontFamily: LETRA.negrita, fontSize: 20, color: '#FFFFFF' },
  info: { flex: 1, minWidth: 0, gap: 3 },
  nombre: { fontFamily: LETRA.tituloSemi, fontSize: 17, lineHeight: 21.25 },
  detalle: { fontFamily: LETRA.normal, fontSize: 13, opacity: 0.65 },
});
