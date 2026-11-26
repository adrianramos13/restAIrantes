// Inicio, copia de app.seccion_inicio: botón de notificaciones, portada («Los restaurantes de @tú · N sitios»,
// «Hola, X. Una idea para hoy:»), la idea del día, «Tus amigos han ido a» y «Te recomendamos ir a cenar con».
import { Image } from 'expo-image';
import { router } from 'expo-router';
import { useState } from 'react';
import { Linking, ScrollView, Text, View } from 'react-native';

import { Avatar } from '@/components/persona';
import { Portada } from '@/components/portada';
import { resumenValoracion, TarjetaRestaurante } from '@/components/tarjeta';
import { Boton, Caja, Info, Seccion, Texto, Pantalla } from '@/components/ui';
import { api, InicioDatos, mensaje, Notificacion, Persona, Tarjeta, Yo } from '@/lib/api';
import { useCarga } from '@/lib/carga';
import { HUECO, LETRA, useColores } from '@/lib/tema';

type Idea = InicioDatos['idea'];

function BotonNotificaciones({ cuantas }: { cuantas: number }) {
  const lista = useCarga(() => api<{ notificaciones: Notificacion[] }>('GET', '/notificaciones'), [cuantas]);
  const primera = lista.datos?.notificaciones[0];
  const texto = cuantas === 1
    ? `${primera?.de.nombre || primera?.de.alias || 'Un amigo'} dice que fuisteis juntos a comer`
    : `Tienes ${cuantas} notificaciones nuevas`;
  return <Boton texto={texto} icono="notifications_active" alPulsar={() => router.push('/notificaciones')} />;
}

function IdeaDelDia({ idea, total, alOtra }: { idea: Idea; total: number; alOtra: () => void }) {
  const c = useColores();
  if (!idea) {
    return total === 0 ? (
      <>
        <Info>
          Todavía no tienes restaurantes en tu lista. Añádela en tus <Text style={{ fontFamily: LETRA.semi }}>ajustes</Text> (toca
          tu foto en el Perfil) y aquí te propondré qué comer y dónde.
        </Info>
        <Boton texto="Añadir tu lista" icono="add_location_alt" ancho="contenido" alPulsar={() => router.push('/ajustes')} />
      </>
    ) : <Info>Cuando las reseñas de tu lista estén analizadas, aquí te propondré qué comer y dónde.</Info>;
  }
  const r = idea.restaurante;
  const datos = [r.cocina, `${r.precio ?? 'Precio ?'} · ${resumenValoracion(r)}`, r.cerrado].filter(Boolean).join(' · ');
  return (
    <>
      <Caja>
        <Texto tipo="subtitulo">{`¿Te apetece ${idea.plato}?`}</Texto>
        {/* inicio.css: .sugerida */}
        <View>
          {r.foto ? <Image source={r.foto} contentFit="cover" style={{ width: '100%', height: 150, borderRadius: 12, marginBottom: 10 }} /> : null}
          <Texto style={{ lineHeight: 21, marginBottom: 4 }}>
            Te gustará <Text style={{ fontFamily: LETRA.negrita }}>{r.nombre}</Text>
            {`: ${idea.menciones} reseñas hablan bien de su ${idea.plato}.`}
          </Texto>
          <Text style={{ fontFamily: LETRA.normal, fontSize: 13.5, lineHeight: 18.9, marginBottom: 4, color: c.texto, opacity: 0.8 }}>{datos}</Text>
        </View>
        {/* st.container(horizontal=True) con botones width="stretch": crecen según su texto */}
        <View style={{ flexDirection: 'row', gap: HUECO }}>
          <Boton texto="Cómo llegar" tipo="primario" icono="directions" ancho="contenido" style={{ flexGrow: 1 }}
            alPulsar={() => Linking.openURL(`https://www.google.com/maps/dir/?api=1&destination=${r.lat},${r.lon}`)} />
          <Boton texto="Ver ficha" icono="info" ancho="contenido" style={{ flexGrow: 1 }}
            alPulsar={() => router.push({ pathname: '/restaurante/[id]', params: { id: String(r.id), plato: idea.plato } })} />
        </View>
      </Caja>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: HUECO }}>
        <Boton texto="Otra idea" icono="casino" ancho="contenido" alPulsar={alOtra} />
        <Boton texto={`Más sitios con ${idea.plato}`} icono="search" ancho="contenido"
          alPulsar={() => router.navigate({ pathname: '/comer', params: { plato: idea.plato } })} />
      </View>
    </>
  );
}

function VisitasDeAmigos() {
  const visitas = useCarga(() => api<{ tiene_amigos: boolean; restaurantes: Tarjeta[] }>('GET', '/amigos/visitas'), []);
  const d = visitas.datos;
  return (
    <Seccion titulo="Tus amigos han ido a">
      {visitas.error ? <Texto tipo="suave">No se puede ver ahora mismo.</Texto> : null}
      {d && !d.tiene_amigos ? (
        <>
          <Texto tipo="suave">
            Añade amigos (en <Text style={{ fontFamily: LETRA.negrita }}>Buscar → Personas</Text>) y aquí verás los últimos sitios
            a los que han ido.
          </Texto>
          <Boton texto="Buscar amigos" icono="person_add" ancho="contenido"
            alPulsar={() => router.navigate({ pathname: '/buscar', params: { modo: 'personas' } })} />
        </>
      ) : null}
      {d?.tiene_amigos && !d.restaurantes.length ? (
        <Texto tipo="suave">Tus amigos no han marcado ningún sitio con «He ido» en las últimas 2 semanas.</Texto>
      ) : null}
      {d?.restaurantes.length ? (
        <ScrollView horizontal showsHorizontalScrollIndicator={false} snapToInterval={170} decelerationRate="fast"
          contentContainerStyle={{ gap: 10, padding: 2, paddingBottom: 10 }}>
          {d.restaurantes.map((t) => <TarjetaRestaurante key={`${t.id}-${t.visita?.quien}-${t.visita?.fecha}`} tarjeta={t} variante="carrusel" />)}
        </ScrollView>
      ) : null}
    </Seccion>
  );
}

function CenarCon() {
  const c = useColores();
  const sugeridas = useCarga(() => api<{ tiene_zona: boolean; personas: Persona[] }>('GET', '/cenar-con'), []);
  const [enviadas, setEnviadas] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const d = sugeridas.datos;
  if (!d || (!d.personas.length && d.tiene_zona)) return null;

  async function anadir(p: Persona) {
    setError(null);
    try {
      await api('POST', `/personas/${p.alias}/amistad`);
      setEnviadas([...enviadas, p.alias]);
    } catch (e) {
      setError(mensaje(e));
    }
  }

  return (
    <Seccion titulo="Te recomendamos ir a cenar con">
      {!d.personas.length ? (
        <>
          <Texto tipo="suave">Dinos de dónde eres y te propondremos gente de tu zona.</Texto>
          <Boton texto="Poner de dónde soy" icono="location_on" ancho="contenido" alPulsar={() => router.push('/ajustes')} />
        </>
      ) : null}
      {error ? <Info tipo="error">{error}</Info> : null}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: HUECO }}>
        {d.personas.map((p) => (
          <Caja key={p.alias} style={{ width: 150, alignItems: 'center', gap: 7.5 }}>
            <Avatar persona={p} tam={56} />
            <Text style={{ fontFamily: LETRA.negrita, fontSize: 15, lineHeight: 24, color: c.texto, textAlign: 'center' }} numberOfLines={2}>
              {p.nombre}{p.alias ? <Text style={{ fontFamily: LETRA.normal }}>{`\n@${p.alias}`}</Text> : null}
            </Text>
            <Texto tipo="suave" style={{ textAlign: 'center' }}>{p.motivo}</Texto>
            <Boton texto={enviadas.includes(p.alias) ? 'Enviada' : 'Añadir'} icono="person_add"
              desactivado={enviadas.includes(p.alias)} alPulsar={() => anadir(p)} />
          </Caja>
        ))}
      </ScrollView>
    </Seccion>
  );
}

export default function Inicio() {
  const yo = useCarga(() => api<Yo>('GET', '/yo'), []);
  const inicio = useCarga(() => api<InicioDatos>('GET', '/inicio'), []);
  const [otra, setOtra] = useState<Idea | undefined>(undefined);   // tras «Otra idea»; la cinta de fotos no cambia
  const d = yo.datos;
  const idea = otra !== undefined ? otra : inicio.datos?.idea ?? null;

  async function otraIdea() {
    try {
      const r = await api<InicioDatos>('GET', '/inicio', undefined, idea ? { evitar: idea.plato } : undefined);
      setOtra(r.idea);
    } catch {
      // se queda la idea que había
    }
  }

  const dueno = d ? (d.alias ? `@${d.alias}` : d.nombre) : '';
  return (
    <Pantalla recargando={yo.cargando && !!d} alRecargar={() => { yo.recargar(); inicio.recargar(); setOtra(undefined); }}>
      {yo.error ? <Texto tipo="error">{yo.error}</Texto> : null}
      {d && d.notificaciones > 0 ? <BotonNotificaciones cuantas={d.notificaciones} /> : null}
      {d ? (
        <Portada fotos={inicio.datos?.portada ?? []} momento={`🍽️ Los restaurantes de ${dueno}\n${d.lista.total} sitios`}
          subtitulo={`Hola, ${d.nombre}. Una idea para hoy:`} />
      ) : null}
      {d && inicio.datos ? <IdeaDelDia idea={idea} total={d.lista.total} alOtra={otraIdea} /> : null}
      {d ? <VisitasDeAmigos /> : null}
      {d ? <CenarCon /> : null}
    </Pantalla>
  );
}
