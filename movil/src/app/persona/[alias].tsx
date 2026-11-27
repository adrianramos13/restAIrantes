// Perfil de un amigo, copia de amigos._mini_perfil: «Volver», su foto con nombre y @usuario, «🤝 N % de gustos en
// común», Nota media | Ha ido a, cocina favorita, «Sus últimas valoraciones» y «En común» en carrusel y «Quitar de
// amigos» en rojo. Si aún no sois amigos (p. ej. llega por un enlace compartido): añadir, aceptar o cancelar.
import { router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { ScrollView, Text, View } from 'react-native';

import { Avatar } from '@/components/persona';
import { TarjetaRestaurante } from '@/components/tarjeta';
import { Boton, Cargando, Info, Pantalla, Texto } from '@/components/ui';
import { api, mensaje, PerfilPersona, Tarjeta } from '@/lib/api';
import { useCarga } from '@/lib/carga';
import { compartirPerfil } from '@/lib/compartir';
import { LETRA, useColores } from '@/lib/tema';

/** st.metric: la etiqueta pequeña y la cifra grande. */
function Cifra({ etiqueta, valor }: { etiqueta: string; valor: string }) {
  const c = useColores();
  return (
    <View style={{ flex: 1 }}>
      <Text style={{ fontFamily: LETRA.normal, fontSize: 13.125, lineHeight: 21, color: c.texto }}>{etiqueta}</Text>
      <Text style={{ fontFamily: LETRA.normal, fontSize: 33.75, lineHeight: 40.5, color: c.texto }}>{valor}</Text>
    </View>
  );
}

function Carrusel({ tarjetas }: { tarjetas: Tarjeta[] }) {
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} snapToInterval={170} decelerationRate="fast"
      contentContainerStyle={{ gap: 10, padding: 2, paddingBottom: 10 }}>
      {tarjetas.map((t, i) => <TarjetaRestaurante key={`${t.id}-${i}`} tarjeta={t} variante="carrusel" />)}
    </ScrollView>
  );
}

export default function PerfilDePersona() {
  const c = useColores();
  const { alias } = useLocalSearchParams<{ alias: string }>();
  const perfil = useCarga(() => api<PerfilPersona>('GET', `/personas/${encodeURIComponent(alias)}`), [alias]);
  const [error, setError] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);

  async function hacer(metodo: 'POST' | 'DELETE', ruta: string, volver = false) {
    setError(null);
    setOcupado(true);
    try {
      await api(metodo, ruta);
      if (volver) router.back();
      else perfil.recargar();
    } catch (e) {
      setError(mensaje(e));
    } finally {
      setOcupado(false);
    }
  }

  const p = perfil.datos;
  const volver = router.canGoBack()
    ? <Boton texto="Volver" tipo="texto" icono="arrow_back" ancho="contenido" alPulsar={() => router.back()} />
    : <Boton texto="Ir al inicio" tipo="texto" icono="arrow_back" ancho="contenido" alPulsar={() => router.replace('/')} />;
  if (!p) {
    return (
      <Pantalla>
        {volver}
        {perfil.error ? <Info tipo="error">{perfil.error}</Info> : <Cargando />}
      </Pantalla>
    );
  }
  const valoraciones = p.valoraciones ?? [];
  const comunes = p.en_comun_total ?? 0;

  return (
    <Pantalla recargando={perfil.cargando} alRecargar={perfil.recargar}>
      {volver}
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 15 }}>
        <Avatar persona={p} tam={72} />
        <View style={{ flex: 1 }}>
          <Text style={{ fontFamily: LETRA.titulo, fontSize: 20.25, lineHeight: 24.3, color: c.texto }}>{p.nombre}</Text>
          <Text style={{ fontFamily: LETRA.normal, fontSize: 14.25, lineHeight: 18.5, opacity: 0.7, color: c.texto }}>{`@${p.alias}`}</Text>
        </View>
      </View>
      {error ? <Info tipo="error">{error}</Info> : null}

      {p.estado === 'nuevo' ? (
        <Boton texto="Añadir" tipo="primario" icono="person_add" cargando={ocupado} alPulsar={() => hacer('POST', `/personas/${alias}/amistad`)} />
      ) : null}
      {p.estado === 'recibida' ? (
        <>
          <Texto>quiere ser tu amigo</Texto>
          <View style={{ flexDirection: 'row', gap: 15 }}>
            <Boton texto="Aceptar" tipo="primario" icono="check" style={{ flex: 1 }} cargando={ocupado}
              alPulsar={() => hacer('POST', `/personas/${alias}/aceptar`)} />
            <Boton texto="Rechazar" icono="close" style={{ flex: 1 }} alPulsar={() => hacer('DELETE', `/personas/${alias}/amistad`)} />
          </View>
        </>
      ) : null}
      {p.estado === 'enviada' ? (
        <>
          <Texto tipo="suave">Solicitud enviada: cuando la acepte, verás aquí sus valoraciones.</Texto>
          <Boton texto="Cancelar" tipo="texto" ancho="contenido" alPulsar={() => hacer('DELETE', `/personas/${alias}/amistad`)} />
        </>
      ) : null}

      {p.estado === 'amigo' ? (
        <>
          {p.afinidad !== null && p.afinidad !== undefined ? (
            <Texto tipo="negrita" style={{ fontFamily: LETRA.negrita }}>{`🤝 ${p.afinidad} % de gustos en común`}</Texto>
          ) : null}
          <View style={{ flexDirection: 'row', gap: 15 }}>
            <Cifra etiqueta="Nota media" valor={p.nota_media ? `${p.nota_media.toFixed(1).replace('.', ',')} ★` : '–'} />
            <Cifra etiqueta="Ha ido a" valor={String(p.ha_ido ?? 0)} />
          </View>
          {p.cocina_favorita ? (
            <Texto>{'🍽️ Cocina favorita: '}<Text style={{ fontFamily: LETRA.negrita }}>{p.cocina_favorita}</Text></Texto>
          ) : null}

          <Texto tipo="negrita" style={{ fontFamily: LETRA.negrita }}>Sus últimas valoraciones</Texto>
          {valoraciones.length ? <Carrusel tarjetas={valoraciones} />
            : <Texto tipo="suave">Todavía no ha marcado ningún sitio con «He ido».</Texto>}

          <Texto>
            <Text style={{ fontFamily: LETRA.negrita }}>En común</Text>
            {` · ${comunes} restaurante${comunes !== 1 ? 's' : ''} en vuestras listas`}
            {p.idos_los_dos ? ` · habéis ido los dos a ${p.idos_los_dos}` : ''}
          </Texto>
          {/* desde «En común» la ficha no lleva su reseña: solo la tuya */}
          {p.en_comun?.length ? <Carrusel tarjetas={p.en_comun.map((t) => ({ ...t, visita: undefined }))} /> : null}

          {/* global.css .st-key-quitar_amigo: en rojo, que se vea que es serio */}
          <Boton texto="Quitar de amigos" icono="person_remove" alPulsar={() => hacer('DELETE', `/personas/${alias}/amistad`, true)}
            style={{ backgroundColor: 'rgba(220, 38, 38, 0.08)', borderColor: '#DC2626' }}
            colorTexto={c.texto === '#1F1A14' ? '#B91C1C' : '#F87171'} />
        </>
      ) : null}
      <Boton texto="Compartir su perfil" tipo="texto" icono="share" alPulsar={() => compartirPerfil(p.alias)} />
    </Pantalla>
  );
}
