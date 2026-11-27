// Notificaciones, copia de app.ventana_notificaciones: en cajas, «Ana · @ana dice que fuisteis juntos a X el
// 20/11/2026.» con «Sí, fui» / «No». «Sí, fui» despliega tus estrellas, el día (el que puso quien te invitó, sin
// cambiar) y lo que más te gustó; al guardar, ya te sale en tu perfil.
import { router } from 'expo-router';
import { useState } from 'react';
import { Text, TextInput, View } from 'react-native';

import { Estrellas } from '@/components/estrellas';
import { Boton, Caja, Cargando, Etiqueta, Info, Pantalla, Texto, TituloVentana, useAvisoBreve } from '@/components/ui';
import { api, mensaje, Notificacion } from '@/lib/api';
import { useCarga } from '@/lib/carga';
import { LETRA, RADIO, TAM_PEQUENO, useColores } from '@/lib/tema';
import { olvidarVisitados } from '@/lib/visitados';

function fechaCorta(iso: string): string {
  const [a, m, d] = iso.slice(0, 10).split('-');
  return `${d}/${m}/${a}`;
}

function UnaNotificacion({ n, alAcabar }: { n: Notificacion; alAcabar: (aviso?: string) => void }) {
  const c = useColores();
  const [abierta, setAbierta] = useState(false);
  const [nota, setNota] = useState<number | null>(null);
  const [comentario, setComentario] = useState('');
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ruta = `/notificaciones/${n.de.alias}/${n.restaurante_id}`;

  async function hacer(aceptar: boolean) {
    setError(null);
    setOcupado(true);
    try {
      if (aceptar) {
        await api('POST', ruta, { nota, comentario: comentario.trim() || null });
        olvidarVisitados();
      } else {
        await api('DELETE', ruta);
      }
      alAcabar(aceptar ? '¡Guardado! Ya sale en tu perfil.' : undefined);
    } catch (e) {
      setError(mensaje(e));
      setOcupado(false);
    }
  }

  return (
    <Caja>
      <Texto>
        <Text style={{ fontFamily: LETRA.negrita }}>{n.de.nombre}</Text>
        {` · @${n.de.alias} dice que fuisteis juntos a `}
        <Text style={{ fontFamily: LETRA.negrita }}>{n.restaurante}</Text>
        {` el ${fechaCorta(n.fecha)}.`}
      </Texto>
      {error ? <Info tipo="error">{error}</Info> : null}
      {abierta ? (
        <>
          <Estrellas valor={nota} alCambiar={setNota} />
          <View style={{ opacity: 0.6 }}>
            <Etiqueta texto="Cuándo fuisteis" />
            <View style={{ minHeight: 38, justifyContent: 'center', paddingHorizontal: 11.25, borderRadius: RADIO, borderWidth: 1,
              borderColor: c.borde, backgroundColor: c.fondo2 }}>
              <Text style={{ fontFamily: LETRA.normal, fontSize: TAM_PEQUENO, color: c.texto }}>{fechaCorta(n.fecha)}</Text>
            </View>
          </View>
          <View>
            <Etiqueta texto="Lo que más te gustó" />
            <TextInput value={comentario} onChangeText={setComentario} multiline maxLength={1000}
              placeholder="Lo que más te gustó (opcional)" placeholderTextColor={c.textoSuave}
              style={{ minHeight: 68, borderRadius: RADIO, borderWidth: 1, borderColor: c.borde, backgroundColor: c.fondo2,
                paddingHorizontal: 11.25, paddingVertical: 7.5, fontFamily: LETRA.normal, fontSize: TAM_PEQUENO, color: c.texto,
                textAlignVertical: 'top' }} />
          </View>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 15 }}>
            <Boton tipo="primario" texto="Guardar" icono="check_circle" cargando={ocupado} style={{ flex: 1 }} alPulsar={() => hacer(true)} />
            <Boton texto="Cancelar" tipo="texto" ancho="contenido" alPulsar={() => setAbierta(false)} />
          </View>
        </>
      ) : (
        <View style={{ flexDirection: 'row', gap: 15 }}>
          <Boton texto="Sí, fui" tipo="primario" icono="check" ancho="contenido" alPulsar={() => setAbierta(true)} />
          <Boton texto="No" ancho="contenido" cargando={ocupado} alPulsar={() => hacer(false)} />
        </View>
      )}
    </Caja>
  );
}

export default function Notificaciones() {
  const lista = useCarga(() => api<{ notificaciones: Notificacion[] }>('GET', '/notificaciones'), []);
  const [aviso, avisar] = useAvisoBreve();
  const c = useColores();
  return (
    <View style={{ flex: 1, backgroundColor: c.fondo }}>
      <Pantalla margen={22.5} recargando={lista.cargando && !!lista.datos} alRecargar={lista.recargar}>
        <TituloVentana titulo="Notificaciones" alCerrar={() => router.back()} />
        {lista.cargando && !lista.datos ? <Cargando /> : null}
        {lista.error ? <Info tipo="error">{lista.error}</Info> : null}
        {lista.datos && !lista.datos.notificaciones.length ? <Texto tipo="suave">No tienes notificaciones.</Texto> : null}
        {lista.datos?.notificaciones.map((n) => (
          <UnaNotificacion key={`${n.de.alias}-${n.restaurante_id}`} n={n}
            alAcabar={(t) => { if (t) avisar(t); lista.recargar(); }} />
        ))}
      </Pantalla>
      {aviso}
    </View>
  );
}
