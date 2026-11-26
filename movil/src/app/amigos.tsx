// Amigos: solicitudes que te han enviado (aceptar / rechazar), buscar gente por nombre o @usuario, tus amigos y
// las solicitudes que has enviado. Al tocar a alguien se abre su perfil.
import { useState } from 'react';
import { View } from 'react-native';

import { FilaPersona } from '@/components/persona';
import { Boton, Campo, Cargando, Pantalla, Seccion, Texto } from '@/components/ui';
import { api, mensaje, Persona } from '@/lib/api';
import { useCarga } from '@/lib/carga';

interface MisAmigos {
  amigos: Persona[];
  recibidas: Persona[];
  enviadas: Persona[];
}

const BOTON_SEGUN_ESTADO: Record<NonNullable<Persona['estado']>, string | null> = {
  nuevo: 'Añadir',
  recibida: 'Aceptar',
  enviada: null,
  amigo: null,
};

export default function Amigos() {
  const [texto, setTexto] = useState('');
  const [error, setError] = useState<string | null>(null);
  const mios = useCarga(() => api<MisAmigos>('GET', '/amigos'), []);
  const q = texto.trim();
  const encontradas = useCarga(
    () => (q.length >= 2 ? api<{ personas: Persona[] }>('GET', '/personas', undefined, { q }) : Promise.resolve(null)),
    [q],
  );

  async function hacer(metodo: 'POST' | 'DELETE', ruta: string) {
    setError(null);
    try {
      await api(metodo, ruta);
      mios.recargar();
      encontradas.recargar();
    } catch (e) {
      setError(mensaje(e));
    }
  }

  const d = mios.datos;
  return (
    <Pantalla recargando={mios.cargando && !!d} alRecargar={mios.recargar}>
      {error ? <Texto tipo="error">{error}</Texto> : null}
      {mios.error ? <Texto tipo="error">{mios.error}</Texto> : null}

      {d?.recibidas.length ? (
        <Seccion titulo="Quieren ser tus amigos">
          {d.recibidas.map((p) => (
            <FilaPersona key={p.alias} persona={p}>
              <View style={{ flexDirection: 'row', gap: 10 }}>
                <View style={{ flex: 1 }}>
                  <Boton texto="Aceptar" alPulsar={() => hacer('POST', `/personas/${p.alias}/aceptar`)} />
                </View>
                <View style={{ flex: 1 }}>
                  <Boton texto="Rechazar" tipo="secundario" alPulsar={() => hacer('DELETE', `/personas/${p.alias}/amistad`)} />
                </View>
              </View>
            </FilaPersona>
          ))}
        </Seccion>
      ) : null}

      <Seccion titulo="Buscar gente">
        <Campo placeholder="Nombre o @usuario" value={texto} onChangeText={setTexto} autoCapitalize="none" autoCorrect={false} />
        {encontradas.cargando && q.length >= 2 && !encontradas.datos ? <Cargando /> : null}
        {encontradas.datos && !encontradas.datos.personas.length ? <Texto tipo="suave">No hay nadie con ese nombre.</Texto> : null}
        {encontradas.datos?.personas.map((p) => {
          const boton = p.estado ? BOTON_SEGUN_ESTADO[p.estado] : null;
          return (
            <FilaPersona key={p.alias} persona={p}
              detalle={p.estado === 'amigo' ? 'Tu amigo' : p.estado === 'enviada' ? 'Solicitud enviada' : undefined}>
              {boton ? (
                <Boton texto={boton} tipo="secundario"
                  alPulsar={() => hacer('POST', p.estado === 'recibida' ? `/personas/${p.alias}/aceptar` : `/personas/${p.alias}/amistad`)} />
              ) : null}
            </FilaPersona>
          );
        })}
      </Seccion>

      <Seccion titulo={d ? `Tus amigos (${d.amigos.length})` : 'Tus amigos'}>
        {mios.cargando && !d ? <Cargando /> : null}
        {d && !d.amigos.length ? <Texto tipo="suave">Todavía no tienes amigos: búscalos arriba por su nombre o @usuario.</Texto> : null}
        {d?.amigos.map((p) => <FilaPersona key={p.alias} persona={p} />)}
      </Seccion>

      {d?.enviadas.length ? (
        <Seccion titulo="Solicitudes enviadas">
          {d.enviadas.map((p) => (
            <FilaPersona key={p.alias} persona={p} detalle="Pendiente">
              <Boton texto="Cancelar solicitud" tipo="texto" alPulsar={() => hacer('DELETE', `/personas/${p.alias}/amistad`)} />
            </FilaPersona>
          ))}
        </Seccion>
      ) : null}
    </Pantalla>
  );
}
