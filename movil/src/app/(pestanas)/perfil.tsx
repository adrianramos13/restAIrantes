// Perfil: tu lista (con filtros y orden), tu diario (dónde has ido) y tu eatlist. Arriba, Amigos y Ajustes.
import { router } from 'expo-router';
import { useState } from 'react';
import { View } from 'react-native';

import { TarjetaRestaurante } from '@/components/tarjeta';
import { Avatar } from '@/components/persona';
import { Boton, Campo, Cargando, Chips, Pantalla, Seccion, Texto } from '@/components/ui';
import { api, Tarjeta, Visita, Yo } from '@/lib/api';
import { useCarga } from '@/lib/carga';
import { useColores } from '@/lib/tema';

type Pestana = 'lista' | 'diario' | 'eatlist';
type Orden = 'nota' | 'recientes' | 'nombre' | 'resenas';

const ORDENES: Record<Orden, string> = {
  nota: 'Mejor valorados',
  recientes: 'Recientes',
  nombre: 'Nombre',
  resenas: 'Más reseñas',
};
const NOTAS = [0, 4, 4.5] as const;
const POR_PAGINA = 20;

interface RespuestaLista {
  restaurantes: Tarjeta[];
  total: number;
  resumen: { total: number; nota_media: number | null; precio_medio: number | null; cocinas: Record<string, number> } | null;
}

function MiLista() {
  const [texto, setTexto] = useState('');
  const [cocinas, setCocinas] = useState<string[]>([]);
  const [notaMin, setNotaMin] = useState<number>(0);
  const [sinCerrados, setSinCerrados] = useState(false);
  const [orden, setOrden] = useState<Orden>('nota');
  const [mostrados, setMostrados] = useState(POR_PAGINA);
  const lista = useCarga(
    () => api<RespuestaLista>('GET', '/lista', undefined, {
      texto: texto.trim(), cocina: cocinas, nota_min: notaMin, ocultar_cerrados: sinCerrados, orden,
    }),
    [texto, cocinas, notaMin, sinCerrados, orden],
  );
  const visitas = useCarga(() => api<{ visitas: Visita[] }>('GET', '/visitas'), []);
  const idos = new Set(visitas.datos?.visitas.map((v) => v.restaurante_id));
  const resumen = lista.datos?.resumen;

  return (
    <>
      {resumen ? (
        <Texto tipo="suave">
          {[`${resumen.total} sitios`,
            resumen.nota_media !== null ? `nota media ${resumen.nota_media.toFixed(1).replace('.', ',')}` : null,
            resumen.precio_medio !== null ? `~${Math.round(resumen.precio_medio)} € por persona` : null,
            `${idos.size} en los que has estado`].filter(Boolean).join(' · ')}
        </Texto>
      ) : null}
      <Campo placeholder="Buscar en tu lista" value={texto} onChangeText={setTexto} autoCorrect={false} />
      <Chips opciones={Object.keys(resumen?.cocinas ?? {})} elegidas={cocinas}
        alElegir={(x) => setCocinas(cocinas.includes(x) ? cocinas.filter((y) => y !== x) : [...cocinas, x])} />
      <Chips opciones={NOTAS} elegidas={[notaMin]} alElegir={setNotaMin}
        etiqueta={(n) => (n ? `★ ${String(n).replace('.', ',')}+` : 'Cualquier nota')} />
      <Chips opciones={['abiertos', 'todos'] as const} elegidas={[sinCerrados ? 'abiertos' : 'todos']}
        alElegir={(x) => setSinCerrados(x === 'abiertos')} etiqueta={(x) => (x === 'todos' ? 'Todos' : 'Solo abiertos')} />
      <Chips opciones={Object.keys(ORDENES) as Orden[]} elegidas={[orden]} alElegir={setOrden} etiqueta={(o) => ORDENES[o]} />

      {lista.error ? <Texto tipo="error">{lista.error}</Texto> : null}
      {lista.cargando && !lista.datos ? <Cargando /> : null}
      {lista.datos && !lista.datos.restaurantes.length ? (
        <Texto tipo="suave">{lista.datos.total ? 'Ninguno cumple esos filtros.' : 'Tu lista está vacía: añádela en Ajustes.'}</Texto>
      ) : null}
      {lista.datos?.restaurantes.slice(0, mostrados).map((t) => (
        <TarjetaRestaurante key={t.id} tarjeta={t} visitado={idos.has(t.id)} />
      ))}
      {lista.datos && lista.datos.restaurantes.length > mostrados ? (
        <Boton texto="Ver más" tipo="secundario" alPulsar={() => setMostrados(mostrados + POR_PAGINA)} />
      ) : null}
    </>
  );
}

function Eatlist() {
  const eatlist = useCarga(() => api<{ restaurantes: Tarjeta[] }>('GET', '/eatlist'), []);
  if (eatlist.cargando && !eatlist.datos) return <Cargando />;
  if (eatlist.error) return <Texto tipo="error">{eatlist.error}</Texto>;
  if (!eatlist.datos?.restaurantes.length) {
    return <Texto tipo="suave">Tu eatlist está vacía. Añade sitios que quieras probar desde su ficha.</Texto>;
  }
  return (
    <>
      {eatlist.datos.restaurantes.map((t, n) => (
        <View key={t.id} style={{ gap: 4 }}>
          <Texto tipo="suave">#{n + 1}</Texto>
          <TarjetaRestaurante tarjeta={t} />
        </View>
      ))}
    </>
  );
}

const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre',
  'noviembre', 'diciembre'];

/** Los sitios a los que has ido, por meses (del más reciente), con tu nota y tu comentario. */
function Diario() {
  const diario = useCarga(() => api<{ restaurantes: Tarjeta[] }>('GET', '/diario'), []);
  if (diario.cargando && !diario.datos) return <Cargando />;
  if (diario.error) return <Texto tipo="error">{diario.error}</Texto>;
  if (!diario.datos?.restaurantes.length) {
    return <Texto tipo="suave">Cuando marques «Ya he ido» en la ficha de un restaurante, aparecerá aquí, en tu diario.</Texto>;
  }
  const meses: { titulo: string; tarjetas: Tarjeta[] }[] = [];
  for (const t of diario.datos.restaurantes) {
    const f = new Date(t.visita?.fecha ?? '');
    const titulo = Number.isNaN(f.getTime()) ? 'Sin fecha' : `${MESES[f.getMonth()]} de ${f.getFullYear()}`;
    if (meses.at(-1)?.titulo !== titulo) meses.push({ titulo, tarjetas: [] });
    meses.at(-1)?.tarjetas.push(t);
  }
  return (
    <>
      {meses.map((m) => (
        <Seccion key={m.titulo} titulo={m.titulo[0].toUpperCase() + m.titulo.slice(1)}>
          {m.tarjetas.map((t) => <TarjetaRestaurante key={t.id} tarjeta={t} />)}
        </Seccion>
      ))}
    </>
  );
}

export default function Perfil() {
  const c = useColores();
  const yo = useCarga(() => api<Yo>('GET', '/yo'), []);
  const [pestana, setPestana] = useState<Pestana>('lista');
  const d = yo.datos;

  return (
    <Pantalla recargando={yo.cargando && !!d} alRecargar={yo.recargar}>
      {d ? (
        <View style={{ flexDirection: 'row', gap: 14, alignItems: 'center' }}>
          <Avatar persona={{ inicial: d.nombre[0]?.toUpperCase() ?? '?', color: c.primario, foto: d.foto }} tam={64} />
          <View style={{ flex: 1 }}>
            <Texto tipo="titulo" lineas={1}>{d.nombre}</Texto>
            {d.alias ? <Texto tipo="suave">@{d.alias}</Texto> : <Texto tipo="suave">Elige tu @usuario en Ajustes</Texto>}
          </View>
        </View>
      ) : null}
      {yo.error ? <Texto tipo="error">{yo.error}</Texto> : null}
      <View style={{ flexDirection: 'row', gap: 10 }}>
        <View style={{ flex: 1 }}>
          <Boton texto={d?.solicitudes ? `Amigos (${d.solicitudes} nuevas)` : 'Amigos'} tipo="secundario"
            alPulsar={() => router.push('/amigos')} />
        </View>
        <View style={{ flex: 1 }}>
          <Boton texto="Ajustes" tipo="secundario" alPulsar={() => router.push('/ajustes')} />
        </View>
      </View>

      <Chips opciones={['lista', 'diario', 'eatlist'] as const} elegidas={[pestana]} alElegir={setPestana}
        etiqueta={(p) => ({ lista: 'Mi lista', diario: 'Diario', eatlist: 'Eatlist' })[p]} />

      {pestana === 'lista' ? <MiLista /> : null}
      {pestana === 'diario' ? <Diario /> : null}
      {pestana === 'eatlist' ? <Eatlist /> : null}
    </Pantalla>
  );
}
