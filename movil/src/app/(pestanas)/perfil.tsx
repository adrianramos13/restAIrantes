// Perfil, copia de app.seccion_perfil: arriba, estilo Instagram, tu foto (abre tus ajustes), nombre, @usuario y
// tres cifras (Idos y En tu lista abren esa lista en una ventana; Amigos, su listado). Debajo, Perfil | Diario |
// Eatlist: «Tus datos» y «Cerrar sesión»; tu diario por meses; los sitios a los que quieres ir, en tu orden.
import { router } from 'expo-router';
import { useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { Cabecera, TusDatos } from '@/components/cabecera_perfil';
import { Diario, GrupoDiario } from '@/components/diario';
import { abrirFicha } from '@/components/tarjeta';
import { Boton, Caja, Info, Pantalla, Segmentado, Texto } from '@/components/ui';
import { api, Tarjeta, Yo } from '@/lib/api';
import { useCarga } from '@/lib/carga';
import { useSesion } from '@/lib/sesion';
import { LETRA, useColores } from '@/lib/tema';

type Pestana = 'Perfil' | 'Diario' | 'Eatlist';
const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre',
  'noviembre', 'diciembre'];



/** app.bloque_insights: «Tus datos» en tarjetas de dos en dos. */
function TusDatosBloque({ datos }: { datos: TusDatos | null }) {
  const c = useColores();
  return (
    <Caja>
      <Texto tipo="subtitulo" style={{ textAlign: 'center' }}>Tus datos</Texto>
      {datos && !datos.tarjetas.length ? <Texto tipo="suave">Aparecerán cuando tengas restaurantes en tu lista.</Texto> : null}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
        {datos?.tarjetas.map((t) => (
          <View key={t.texto} style={[estilos.insight, { backgroundColor: c.fondo2, borderColor: c.borde }]}>
            <Text style={{ fontSize: 18 }} accessibilityElementsHidden>{t.icono}</Text>
            <Text style={{ fontFamily: LETRA.negrita, fontSize: 18.75, lineHeight: 23.4, color: c.texto, textAlign: 'center' }}>{t.valor}</Text>
            <Text style={{ fontFamily: LETRA.normal, fontSize: 12.75, lineHeight: 16.6, opacity: 0.75, color: c.texto, textAlign: 'center' }}>
              {t.texto}
            </Text>
          </View>
        ))}
      </View>
    </Caja>
  );
}

function PestanaDiario() {
  const diario = useCarga(() => api<{ restaurantes: Tarjeta[] }>('GET', '/diario'), []);
  const visitas = diario.datos?.restaurantes;
  if (diario.error) return <Info tipo="error">{diario.error}</Info>;
  if (!visitas) return null;
  if (!visitas.length) {
    return <Texto tipo="suave">Cuando marques «He ido» en la ficha de un restaurante, aparecerá aquí, en tu diario.</Texto>;
  }
  const grupos: GrupoDiario[] = [];
  for (const t of visitas) {   // ya vienen de la más reciente a la más antigua
    const f = new Date(t.visita?.fecha ?? '');
    const valida = !Number.isNaN(f.getTime());
    const titulo = valida ? `${MESES[f.getMonth()]} ${f.getFullYear()}` : '';
    if (grupos.at(-1)?.titulo !== titulo) grupos.push({ titulo, filas: [] });
    grupos.at(-1)?.filas.push({ id: t.id, caja: valida ? String(f.getDate()) : '', nombre: t.nombre, detalle: t.cocina,
      foto: t.foto, nota: t.visita?.nota ?? null, comentario: !!t.visita?.comentario });
  }
  return (
    <>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 15 }}>
        <Texto tipo="suave">{`${visitas.length} restaurante${visitas.length !== 1 ? 's' : ''}`}</Texto>
        <Boton texto="Aplicar filtros" tipo="texto" icono="tune" ancho="contenido"
          alPulsar={() => router.push({ pathname: '/lista', params: { cual: 'idos' } })} />
      </View>
      <Diario grupos={grupos} alTocar={(id) => { const t = visitas.find((x) => x.id === id); if (t) abrirFicha({ ...t, visita: t.visita ? { ...t.visita, quien: 'Tú' } : undefined }); }} />
    </>
  );
}

function PestanaEatlist() {
  const eatlist = useCarga(() => api<{ restaurantes: Tarjeta[] }>('GET', '/eatlist'), []);
  const lista = eatlist.datos?.restaurantes;
  if (eatlist.error) return <Info tipo="error">{eatlist.error}</Info>;
  if (!lista) return null;
  if (!lista.length) {
    return (
      <Texto tipo="suave">
        Aquí irán los sitios a los que quieres ir, en tu orden. Añádelos desde la ficha de cada restaurante («¿Quieres ir?»),
        eligiendo en qué puesto.
      </Texto>
    );
  }
  return (
    <>
      <Texto tipo="suave">
        {`${lista.length} restaurante${lista.length !== 1 ? 's' : ''} que quieres probar · tócalos para cambiarlos de puesto`}
      </Texto>
      <Diario puestos alTocar={(id) => router.push({ pathname: '/restaurante/[id]', params: { id: String(id) } })} grupos={[{ titulo: null, filas: lista.map((t, i) => ({
        id: t.id, caja: String(i + 1), nombre: t.nombre, detalle: t.cocina, foto: t.foto, nota: null, comentario: false,
      })) }]} />
    </>
  );
}

export default function Perfil() {
  const { salir } = useSesion();
  const yo = useCarga(() => api<Yo>('GET', '/yo'), []);
  const datos = useCarga(() => api<TusDatos>('GET', '/yo/datos'), []);
  const [pestana, setPestana] = useState<Pestana>('Perfil');
  const d = yo.datos;

  return (
    <Pantalla recargando={yo.cargando && !!d} alRecargar={() => { yo.recargar(); datos.recargar(); }}>
      {yo.error ? <Info tipo="error">{yo.error}</Info> : null}
      {d ? <Cabecera yo={d} datos={datos.datos} /> : null}
      <Segmentado opciones={['Perfil', 'Diario', 'Eatlist'] as const} elegidas={[pestana]} alElegir={setPestana} />
      {pestana === 'Diario' ? <PestanaDiario /> : null}
      {pestana === 'Eatlist' ? <PestanaEatlist /> : null}
      {pestana === 'Perfil' ? (
        <>
          <TusDatosBloque datos={datos.datos} />
          <Boton texto="Cerrar sesión" icono="logout" alPulsar={salir} />
        </>
      ) : null}
    </Pantalla>
  );
}

const estilos = StyleSheet.create({
  insight: { width: '47%', flexGrow: 1, alignItems: 'center', gap: 2, padding: 12, borderRadius: 12, borderWidth: 1 },
});
