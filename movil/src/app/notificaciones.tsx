// Notificaciones: «Ana dice que fuisteis juntos a X». «Sí, fui» despliega tus estrellas y tu comentario (la fecha
// es la que puso quien te invitó); «No» la borra. Hasta que no la aceptas, no te sale en tu perfil.
import { useState } from 'react';
import { View } from 'react-native';

import { Estrellas } from '@/components/estrellas';
import { FilaPersona } from '@/components/persona';
import { Boton, Campo, Cargando, Pantalla, Texto } from '@/components/ui';
import { api, mensaje, Notificacion } from '@/lib/api';
import { useCarga } from '@/lib/carga';

function fechaCorta(iso: string): string {
  const [a, m, d] = iso.slice(0, 10).split('-');
  return `${d}/${m}/${a}`;
}

function UnaNotificacion({ n, alAcabar }: { n: Notificacion; alAcabar: () => void }) {
  const [abierta, setAbierta] = useState(false);
  const [nota, setNota] = useState<number | null>(null);
  const [comentario, setComentario] = useState('');
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ruta = `/notificaciones/${n.de.alias}/${n.restaurante_id}`;

  async function hacer(accion: () => Promise<unknown>) {
    setError(null);
    setOcupado(true);
    try {
      await accion();
      alAcabar();
    } catch (e) {
      setError(mensaje(e));
      setOcupado(false);
    }
  }

  return (
    <FilaPersona persona={n.de} detalle={`dice que fuisteis juntos a ${n.restaurante} el ${fechaCorta(n.fecha)}`}>
      {error ? <Texto tipo="error">{error}</Texto> : null}
      {abierta ? (
        <View style={{ gap: 10 }}>
          <Estrellas valor={nota} alCambiar={setNota} />
          <Campo placeholder="Lo que más te gustó (opcional)" value={comentario} onChangeText={setComentario} multiline maxLength={1000} />
          <Boton texto="Guardar" cargando={ocupado}
            alPulsar={() => hacer(() => api('POST', ruta, { nota, comentario: comentario.trim() || null }))} />
          <Boton texto="Cancelar" tipo="texto" alPulsar={() => setAbierta(false)} />
        </View>
      ) : (
        <View style={{ flexDirection: 'row', gap: 10 }}>
          <View style={{ flex: 1 }}>
            <Boton texto="Sí, fui" alPulsar={() => setAbierta(true)} />
          </View>
          <View style={{ flex: 1 }}>
            <Boton texto="No" tipo="secundario" cargando={ocupado} alPulsar={() => hacer(() => api('DELETE', ruta))} />
          </View>
        </View>
      )}
    </FilaPersona>
  );
}

export default function Notificaciones() {
  const lista = useCarga(() => api<{ notificaciones: Notificacion[] }>('GET', '/notificaciones'), []);
  return (
    <Pantalla recargando={lista.cargando && !!lista.datos} alRecargar={lista.recargar}>
      {lista.cargando && !lista.datos ? <Cargando /> : null}
      {lista.error ? <Texto tipo="error">{lista.error}</Texto> : null}
      {lista.datos && !lista.datos.notificaciones.length ? <Texto tipo="suave">No tienes notificaciones.</Texto> : null}
      {lista.datos?.notificaciones.map((n) => (
        <UnaNotificacion key={`${n.de.alias}-${n.restaurante_id}`} n={n} alAcabar={lista.recargar} />
      ))}
    </Pantalla>
  );
}
