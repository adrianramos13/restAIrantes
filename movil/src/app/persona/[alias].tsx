// Perfil de otra persona (desde tus amigos, el buscador o un enlace compartido por WhatsApp). Si sois amigos:
// gustos en común, sus cifras, sus últimas valoraciones y los restaurantes que tenéis los dos en la lista.
import { router, Stack, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { Alert, View } from 'react-native';

import { Avatar } from '@/components/persona';
import { formatoNota, TarjetaRestaurante } from '@/components/tarjeta';
import { Boton, Caja, Cargando, Pantalla, Seccion, Texto } from '@/components/ui';
import { api, mensaje, PerfilPersona } from '@/lib/api';
import { useCarga } from '@/lib/carga';
import { compartirPerfil } from '@/lib/compartir';

export default function PerfilDePersona() {
  const { alias } = useLocalSearchParams<{ alias: string }>();
  const perfil = useCarga(() => api<PerfilPersona>('GET', `/personas/${encodeURIComponent(alias)}`), [alias]);
  const [error, setError] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);

  async function hacer(metodo: 'POST' | 'DELETE', ruta: string) {
    setError(null);
    setOcupado(true);
    try {
      await api(metodo, ruta);
      perfil.recargar();
    } catch (e) {
      setError(mensaje(e));
    } finally {
      setOcupado(false);
    }
  }

  function quitarAmigo(nombre: string) {
    Alert.alert('Quitar de amigos', `${nombre} dejará de ver tus valoraciones y tú las suyas.`, [
      { text: 'Cancelar', style: 'cancel' },
      { text: 'Quitar', style: 'destructive', onPress: () => hacer('DELETE', `/personas/${alias}/amistad`) },
    ]);
  }

  const p = perfil.datos;
  if (perfil.cargando && !p) return <Pantalla><Cargando /></Pantalla>;
  if (!p) return <Pantalla><Texto tipo="error">{perfil.error ?? 'No se ha encontrado.'}</Texto></Pantalla>;
  const amigo = p.estado === 'amigo';

  return (
    <Pantalla recargando={perfil.cargando} alRecargar={perfil.recargar}>
      <Stack.Screen options={{ title: `@${p.alias}` }} />
      <View style={{ alignItems: 'center', gap: 6 }}>
        <Avatar persona={p} tam={88} />
        <Texto tipo="titulo">{p.nombre}</Texto>
        <Texto tipo="suave">@{p.alias}</Texto>
      </View>
      {error ? <Texto tipo="error">{error}</Texto> : null}

      {p.estado === 'nuevo' ? <Boton texto="Añadir a amigos" cargando={ocupado} alPulsar={() => hacer('POST', `/personas/${alias}/amistad`)} /> : null}
      {p.estado === 'recibida' ? (
        <Caja>
          <Texto>{`${p.nombre} quiere ser tu amigo.`}</Texto>
          <Boton texto="Aceptar" cargando={ocupado} alPulsar={() => hacer('POST', `/personas/${alias}/aceptar`)} />
          <Boton texto="Rechazar" tipo="texto" alPulsar={() => hacer('DELETE', `/personas/${alias}/amistad`)} />
        </Caja>
      ) : null}
      {p.estado === 'enviada' ? (
        <Caja>
          <Texto tipo="suave">Solicitud enviada: cuando la acepte, verás aquí sus valoraciones.</Texto>
          <Boton texto="Cancelar solicitud" tipo="texto" alPulsar={() => hacer('DELETE', `/personas/${alias}/amistad`)} />
        </Caja>
      ) : null}

      {amigo ? (
        <>
          {p.afinidad !== null && p.afinidad !== undefined ? (
            <Texto tipo="subtitulo" style={{ textAlign: 'center' }}>{`🤝 ${p.afinidad} % de gustos en común`}</Texto>
          ) : null}
          <Caja>
            <Texto>{`Nota media: ${p.nota_media ? formatoNota(p.nota_media) : '–'} · Ha ido a ${p.ha_ido ?? 0} sitios`}</Texto>
            {p.cocina_favorita ? <Texto>{`🍽️ Cocina favorita: ${p.cocina_favorita}`}</Texto> : null}
          </Caja>
          <Seccion titulo="Sus últimas valoraciones">
            {!p.valoraciones?.length ? <Texto tipo="suave">Todavía no ha marcado ningún sitio con «Ya he ido».</Texto> : null}
            {p.valoraciones?.map((t) => <TarjetaRestaurante key={`${t.id}-${t.visita?.fecha}`} tarjeta={t} />)}
          </Seccion>
          <Seccion titulo={`En común · ${p.en_comun_total ?? 0} en vuestras listas`}>
            {p.idos_los_dos ? <Texto tipo="suave">{`Habéis ido los dos a ${p.idos_los_dos}.`}</Texto> : null}
            {p.en_comun?.map((t) => <TarjetaRestaurante key={t.id} tarjeta={t} />)}
          </Seccion>
          <Boton texto="Quitar de amigos" tipo="texto" alPulsar={() => quitarAmigo(p.nombre)} />
        </>
      ) : null}

      <Boton texto="Compartir su perfil" tipo="secundario" alPulsar={() => compartirPerfil(p.alias)} />
      {router.canGoBack() ? null : <Boton texto="Ir al inicio" tipo="texto" alPulsar={() => router.replace('/')} />}
    </Pantalla>
  );
}
