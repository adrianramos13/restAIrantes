// Tus amigos, copia de amigos.bloque_amigos: tu cabecera, «Volver», «Amigos», las solicitudes recibidas
// destacadas (Aceptar / Rechazar), «Solicitudes enviadas (N)» que se despliega, y la lista estilo Instagram con su
// buscador (componentes/lista_amigos.*). Al tocar a alguien, su perfil.
import { router, Stack } from 'expo-router';
import { useState } from 'react';
import { Pressable, Text, TextInput, View } from 'react-native';

import { Cabecera, TusDatos } from '@/components/cabecera_perfil';
import { Icono } from '@/components/icono';
import { Avatar } from '@/components/persona';
import { Boton, Info, Pantalla, Texto } from '@/components/ui';
import { api, mensaje, Persona, Yo } from '@/lib/api';
import { useCarga } from '@/lib/carga';
import { LETRA, RADIO, useColores } from '@/lib/tema';

interface MisAmigos {
  amigos: Persona[];
  recibidas: Persona[];
  enviadas: Persona[];
}

const sinTildes = (s: string) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

export default function Amigos() {
  const c = useColores();
  const yo = useCarga(() => api<Yo>('GET', '/yo'), []);
  const datos = useCarga(() => api<TusDatos>('GET', '/yo/datos'), []);
  const mios = useCarga(() => api<MisAmigos>('GET', '/amigos'), []);
  const [texto, setTexto] = useState('');
  const [verEnviadas, setVerEnviadas] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function hacer(metodo: 'POST' | 'DELETE', ruta: string) {
    setError(null);
    try {
      await api(metodo, ruta);
      mios.recargar();
      datos.recargar();
    } catch (e) {
      setError(mensaje(e));
    }
  }

  const d = mios.datos;
  const q = sinTildes(texto.trim().replace(/^@/, ''));
  const filtrados = (d?.amigos ?? []).filter((p) => !q || sinTildes(p.nombre).includes(q) || sinTildes(p.alias).includes(q));

  return (
    <Pantalla recargando={mios.cargando && !!d} alRecargar={mios.recargar}>
      <Stack.Screen options={{ headerShown: false }} />
      {yo.datos ? <Cabecera yo={yo.datos} datos={datos.datos} /> : null}
      <Boton texto="Volver" tipo="texto" icono="arrow_back" ancho="contenido" alPulsar={() => router.back()} />
      <Texto tipo="subtitulo">Amigos</Texto>
      {error ? <Info tipo="error">{error}</Info> : null}
      {mios.error ? <Info tipo="error">{mios.error}</Info> : null}

      {/* las recibidas, destacadas (global.css: st-key-solicitud_) */}
      {d?.recibidas.map((p) => (
        <View key={p.alias} style={{ borderRadius: RADIO, borderWidth: 1, borderColor: c.primario, backgroundColor: 'rgba(194, 65, 12, 0.08)',
          padding: 14, gap: 15 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 15 }}>
            <Avatar persona={p} tam={48} />
            <Texto style={{ flex: 1 }}>
              <Text style={{ fontFamily: LETRA.negrita }}>{p.nombre}</Text>
              {` · @${p.alias}\nquiere ser tu amigo`}
            </Texto>
          </View>
          <View style={{ flexDirection: 'row', gap: 15 }}>
            <Boton texto="Aceptar" tipo="primario" icono="check" style={{ flex: 1 }} alPulsar={() => hacer('POST', `/personas/${p.alias}/aceptar`)} />
            <Boton texto="Rechazar" icono="close" style={{ flex: 1 }} alPulsar={() => hacer('DELETE', `/personas/${p.alias}/amistad`)} />
          </View>
        </View>
      ))}

      {d?.enviadas.length ? (
        // st.popover: el botón y, debajo, la cajita flotante con las enviadas
        <View>
          <Boton texto={`Solicitudes enviadas (${d.enviadas.length})`} icono="schedule_send" ancho="contenido"
            alPulsar={() => setVerEnviadas(!verEnviadas)} />
          {verEnviadas ? (
            <View style={{ marginTop: 6, padding: 15, gap: 8, borderRadius: RADIO, borderWidth: 1, borderColor: c.borde,
              backgroundColor: c.fondo, shadowColor: '#000', shadowOpacity: 0.12, shadowRadius: 8, shadowOffset: { width: 0, height: 4 }, elevation: 4 }}>
              {d.enviadas.map((p) => (
                <View key={p.alias} style={{ flexDirection: 'row', alignItems: 'center', gap: 15 }}>
                  <Texto style={{ flex: 1 }}><Text style={{ fontFamily: LETRA.negrita }}>{p.nombre}</Text>{` · @${p.alias}`}</Texto>
                  <Boton texto="Cancelar" tipo="texto" ancho="contenido" alPulsar={() => hacer('DELETE', `/personas/${p.alias}/amistad`)} />
                </View>
              ))}
            </View>
          ) : null}
        </View>
      ) : null}

      {d && !d.amigos.length ? (
        <Texto tipo="suave">
          Todavía no tienes amigos: búscalos en <Text style={{ fontFamily: LETRA.negrita }}>Buscar → Personas</Text> por su nombre o @usuario.
        </Texto>
      ) : null}
      {d?.amigos.length ? (
        <View>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 12, minHeight: 40, borderRadius: 10,
            backgroundColor: c.fondo2 }}>
            <View style={{ opacity: 0.55 }}><Icono nombre="search" tam={18} color={c.texto} /></View>
            <TextInput value={texto} onChangeText={setTexto} placeholder="Buscar" placeholderTextColor={c.textoSuave}
              accessibilityLabel="Buscar entre tus amigos" autoCapitalize="none" autoCorrect={false}
              style={{ flex: 1, fontFamily: LETRA.normal, fontSize: 16, paddingVertical: 8, color: c.texto }} />
          </View>
          <View style={{ marginTop: 10 }}>
            {filtrados.map((p) => (
              <Pressable key={p.alias} accessibilityRole="button" accessibilityLabel={`${p.nombre}, @${p.alias}. Ver su perfil`}
                onPress={() => router.push({ pathname: '/persona/[alias]', params: { alias: p.alias } })}
                style={({ pressed }) => ({ flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 8, paddingHorizontal: 2,
                  borderRadius: 10, backgroundColor: pressed ? c.fondo2 : 'transparent' })}>
                <Avatar persona={p} tam={52} />
                <View style={{ flex: 1, minWidth: 0 }}>
                  <Text style={{ fontFamily: LETRA.negrita, fontSize: 15, lineHeight: 19.5, color: c.texto }}>{p.alias}</Text>
                  <Text style={{ fontFamily: LETRA.normal, fontSize: 14, lineHeight: 18.2, opacity: 0.65, color: c.texto }}>{p.nombre}</Text>
                </View>
              </Pressable>
            ))}
          </View>
          {q && !filtrados.length ? (
            <Text style={{ marginVertical: 10, marginHorizontal: 2, fontFamily: LETRA.normal, fontSize: 14, opacity: 0.7, color: c.texto }}>
              No hay ningún amigo con ese nombre.
            </Text>
          ) : null}
        </View>
      ) : null}
    </Pantalla>
  );
}
