// Inicio: saludo, notificaciones y solicitudes, estado de tu lista, lo que han hecho tus amigos, gente con la que
// ir a cenar y «Lo mejor de la semana» (las mejores visitas de todos).
import { router } from 'expo-router';
import { useState } from 'react';
import { ScrollView, View } from 'react-native';

import { Avatar } from '@/components/persona';
import { TarjetaRestaurante } from '@/components/tarjeta';
import { Boton, Caja, Cargando, Pantalla, Seccion, Texto } from '@/components/ui';
import { api, mensaje, Persona, Tarjeta, Yo } from '@/lib/api';
import { useCarga } from '@/lib/carga';
import { RADIO, useColores } from '@/lib/tema';

const ESTADOS_LISTA: Record<string, string> = {
  pendiente: 'Tu lista de Google Maps está en cola: en unos minutos la tendrás aquí.',
  procesando: 'Estamos leyendo tu lista de Google Maps…',
  error: 'No se pudo leer tu lista de Google Maps. Vuelve a pegar el enlace en Ajustes.',
};

function CenarCon() {
  const c = useColores();
  const sugeridas = useCarga(() => api<{ tiene_zona: boolean; personas: Persona[] }>('GET', '/cenar-con'), []);
  const [enviadas, setEnviadas] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const d = sugeridas.datos;
  if (!d || (!d.personas.length && d.tiene_zona)) return null;

  async function anadir(alias: string) {
    setError(null);
    try {
      await api('POST', `/personas/${alias}/amistad`);
      setEnviadas([...enviadas, alias]);
    } catch (e) {
      setError(mensaje(e));
    }
  }

  return (
    <Seccion titulo="Te recomendamos ir a cenar con">
      {!d.personas.length ? (
        <>
          <Texto tipo="suave">Dinos de dónde eres y te propondremos gente de tu zona.</Texto>
          <Boton texto="Poner de dónde soy" tipo="secundario" alPulsar={() => router.push('/ajustes')} />
        </>
      ) : null}
      {error ? <Texto tipo="error">{error}</Texto> : null}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 10 }}>
        {d.personas.map((p) => (
          <View key={p.alias} style={{ width: 150, padding: 12, gap: 6, alignItems: 'center', borderRadius: RADIO, borderWidth: 1,
            borderColor: c.borde, backgroundColor: c.fondo2 }}>
            <Avatar persona={p} tam={56} />
            <Texto tipo="subtitulo" lineas={1} style={{ fontSize: 15 }}>{p.nombre}</Texto>
            <Texto tipo="suave" lineas={2} style={{ textAlign: 'center' }}>{p.motivo}</Texto>
            <Boton texto={enviadas.includes(p.alias) ? 'Enviada ✓' : 'Añadir'} tipo="secundario"
              desactivado={enviadas.includes(p.alias)} alPulsar={() => anadir(p.alias)} />
          </View>
        ))}
      </ScrollView>
    </Seccion>
  );
}

function VisitasDeAmigos() {
  const visitas = useCarga(() => api<{ tiene_amigos: boolean; restaurantes: Tarjeta[] }>('GET', '/amigos/visitas'), []);
  const d = visitas.datos;
  if (!d) return null;
  return (
    <Seccion titulo="Tus amigos han ido a">
      {!d.tiene_amigos ? (
        <>
          <Texto tipo="suave">Añade amigos y aquí verás los últimos sitios a los que han ido.</Texto>
          <Boton texto="Buscar amigos" tipo="secundario" alPulsar={() => router.push('/amigos')} />
        </>
      ) : null}
      {d.tiene_amigos && !d.restaurantes.length ? (
        <Texto tipo="suave">Tus amigos no han marcado ningún sitio con «Ya he ido» en las últimas 2 semanas.</Texto>
      ) : null}
      {d.restaurantes.map((t) => <TarjetaRestaurante key={`${t.id}-${t.visita?.quien}-${t.visita?.fecha}`} tarjeta={t} />)}
    </Seccion>
  );
}

export default function Inicio() {
  const yo = useCarga(() => api<Yo>('GET', '/yo'), []);
  const destacados = useCarga(
    () => api<{ de_la_semana: boolean; restaurantes: Tarjeta[] }>('GET', '/destacados'),
    [],
  );
  const recargar = () => {
    yo.recargar();
    destacados.recargar();
  };
  const d = yo.datos;

  return (
    <Pantalla recargando={yo.cargando && !!d} alRecargar={recargar}>
      <Texto tipo="titulo">{d ? `Hola, ${d.nombre.split(' ')[0]}` : '¿Dónde comemos?'}</Texto>
      {yo.error ? <Texto tipo="error">{yo.error}</Texto> : null}

      {d && d.notificaciones > 0 ? (
        <Boton texto={d.notificaciones === 1 ? '🔔 Tienes 1 notificación nueva' : `🔔 Tienes ${d.notificaciones} notificaciones nuevas`}
          alPulsar={() => router.push('/notificaciones')} />
      ) : null}
      {d && d.solicitudes > 0 ? (
        <Boton texto={d.solicitudes === 1 ? 'Tienes 1 solicitud de amistad' : `Tienes ${d.solicitudes} solicitudes de amistad`}
          tipo="secundario" alPulsar={() => router.push('/amigos')} />
      ) : null}

      {d ? (
        <Caja>
          <Texto>
            {d.lista.total ? `Tienes ${d.lista.total} restaurantes en tu lista.` : 'Todavía no tienes restaurantes en tu lista.'}
          </Texto>
          {d.lista.estado && ESTADOS_LISTA[d.lista.estado] ? <Texto tipo="suave">{ESTADOS_LISTA[d.lista.estado]}</Texto> : null}
          {!d.lista.total ? (
            <Boton texto="Añadir mi lista de Google Maps" tipo="secundario" alPulsar={() => router.push('/ajustes')} />
          ) : (
            <Boton texto="¿Dónde comemos hoy?" alPulsar={() => router.push('/comer')} />
          )}
        </Caja>
      ) : null}

      <VisitasDeAmigos />
      <CenarCon />

      <Seccion titulo={destacados.datos?.de_la_semana === false ? 'Lo último que se ha valorado' : 'Lo mejor de la semana'}>
        {destacados.cargando && !destacados.datos ? <Cargando /> : null}
        {destacados.error ? <Texto tipo="error">{destacados.error}</Texto> : null}
        {destacados.datos?.restaurantes.map((t) => <TarjetaRestaurante key={`${t.id}-${t.visita?.fecha}`} tarjeta={t} />)}
      </Seccion>
    </Pantalla>
  );
}
