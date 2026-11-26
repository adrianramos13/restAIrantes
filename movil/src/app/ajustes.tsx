// Ajustes: tu foto, nombre, @usuario, «De dónde eres», preferencias de Comer hoy, tu lista de Google Maps,
// compartir tu perfil, cerrar sesión y borrar la cuenta.
import * as ImagePicker from 'expo-image-picker';
import { ReactNode, useState } from 'react';
import { Alert, Pressable, View } from 'react-native';

import { CampoDireccion, Punto } from '@/components/direccion';
import { Avatar } from '@/components/persona';
import { Boton, Campo, Cargando, Chips, Pantalla, Seccion, Texto } from '@/components/ui';
import { api, mensaje, Preferencias, Yo } from '@/lib/api';
import { useCarga } from '@/lib/carga';
import { compartirPerfil } from '@/lib/compartir';
import { useSesion } from '@/lib/sesion';
import { useColores } from '@/lib/tema';

const TIEMPOS = [10, 15, 20, 30, 45, 60] as const;
const DESDE = [0, 10, 20, 30] as const;
const HASTA = [15, 20, 30, 40, 60, 100] as const;   // 100 = sin tope (PRESUPUESTO_SIN_LIMITE)

/** Un bloque con su botón: enseña su propio error o «Guardado». */
function useGuardar(alGuardar: () => void) {
  const [estado, setEstado] = useState<{ ocupado: boolean; error: string | null; hecho: boolean }>(
    { ocupado: false, error: null, hecho: false });
  async function guardar(accion: () => Promise<unknown>) {
    setEstado({ ocupado: true, error: null, hecho: false });
    try {
      await accion();
      setEstado({ ocupado: false, error: null, hecho: true });
      alGuardar();
    } catch (e) {
      setEstado({ ocupado: false, error: mensaje(e), hecho: false });
    }
  }
  const aviso: ReactNode = estado.error ? <Texto tipo="error">{estado.error}</Texto>
    : estado.hecho ? <Texto tipo="suave">Guardado ✓</Texto> : null;
  return { guardar, ocupado: estado.ocupado, aviso };
}

function Foto({ yo, alCambiar }: { yo: Yo; alCambiar: () => void }) {
  const c = useColores();
  const { guardar, ocupado, aviso } = useGuardar(alCambiar);
  async function elegir() {
    const r = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'], allowsEditing: true, aspect: [1, 1], quality: 0.6, base64: true,
    });
    const base64 = r.canceled ? null : r.assets[0]?.base64;
    if (base64) await guardar(() => api('PUT', '/yo/foto', { imagen: `data:image/jpeg;base64,${base64}` }));
  }
  return (
    <View style={{ alignItems: 'center', gap: 8 }}>
      <Pressable accessibilityRole="button" accessibilityLabel="Cambiar tu foto" onPress={elegir}>
        <Avatar persona={{ inicial: yo.nombre[0]?.toUpperCase() ?? '?', color: c.primario, foto: yo.foto }} tam={96} />
      </Pressable>
      {ocupado ? <Cargando /> : <Texto tipo="suave">Toca tu foto para cambiarla</Texto>}
      {yo.foto ? <Boton texto="Quitar foto" tipo="texto" alPulsar={() => guardar(() => api('DELETE', '/yo/foto'))} /> : null}
      {aviso}
    </View>
  );
}

function DatosPersonales({ yo, alCambiar }: { yo: Yo; alCambiar: () => void }) {
  const [nombre, setNombre] = useState(yo.nombre);
  const [alias, setAlias] = useState(yo.alias ?? '');
  const n = useGuardar(alCambiar);
  const a = useGuardar(alCambiar);
  return (
    <>
      <Seccion titulo="Tu nombre">
        <Campo value={nombre} onChangeText={setNombre} maxLength={40} />
        <Boton texto="Guardar nombre" tipo="secundario" cargando={n.ocupado} desactivado={!nombre.trim() || nombre === yo.nombre}
          alPulsar={() => n.guardar(() => api('PUT', '/yo/nombre', { nombre }))} />
        {n.aviso}
      </Seccion>
      <Seccion titulo="Nombre de usuario">
        <Texto tipo="suave">Con él te encuentran tus amigos. Tu correo no lo ve nadie.</Texto>
        <Campo placeholder="Ej. ana_g" value={alias} onChangeText={setAlias} autoCapitalize="none" autoCorrect={false} maxLength={21} />
        <Boton texto="Guardar nombre de usuario" tipo="secundario" cargando={a.ocupado}
          desactivado={!alias.trim() || alias.replace('@', '') === yo.alias}
          alPulsar={() => a.guardar(() => api('PUT', '/yo/alias', { alias }))} />
        {a.aviso}
      </Seccion>
    </>
  );
}

function Zona({ yo, alCambiar }: { yo: Yo; alCambiar: () => void }) {
  const [texto, setTexto] = useState('');
  const [punto, setPunto] = useState<Punto | null>(null);
  const { guardar, ocupado, aviso } = useGuardar(() => {
    setTexto('');
    setPunto(null);
    alCambiar();
  });
  const elegido = punto && punto.texto === texto ? punto : null;
  return (
    <Seccion titulo="De dónde eres">
      <Texto tipo="suave">
        {`${yo.zona ? `Ahora: ${yo.zona}. ` : ''}Solo la usamos para proponerte gente de tu zona y sitios cerca en «Food match». Nadie ve dónde vives.`}
      </Texto>
      <CampoDireccion valor={texto} alEscribir={setTexto} alElegir={setPunto} placeholder="Tu barrio o pueblo, p. ej. Chamberí" />
      <Boton texto="Guardar zona" tipo="secundario" cargando={ocupado} desactivado={texto.trim().length < 2}
        alPulsar={() => guardar(() => api('PUT', '/yo/zona', { zona: texto, lat: elegido?.lat, lon: elegido?.lon }))} />
      {yo.zona ? <Boton texto="Quitar zona" tipo="texto" alPulsar={() => guardar(() => api('DELETE', '/yo/zona'))} /> : null}
      {aviso}
    </Seccion>
  );
}

function PreferenciasComer({ yo, alCambiar }: { yo: Yo; alCambiar: () => void }) {
  const [p, setP] = useState<Preferencias>(yo.preferencias);
  const { guardar, ocupado, aviso } = useGuardar(alCambiar);
  const [desde, hasta] = p.presupuesto;
  return (
    <Seccion titulo="Preferencias">
      <Texto tipo="suave">Lo que viene ya puesto al buscar en Comer hoy.</Texto>
      <Chips opciones={['En coche', 'A pie'] as const} elegidas={[p.transporte]} alElegir={(t) => setP({ ...p, transporte: t })}
        etiqueta={(t) => (t === 'A pie' ? '🚶 A pie' : '🚗 En coche')} />
      <Chips opciones={TIEMPOS} elegidas={[p.tiempo]} alElegir={(t) => setP({ ...p, tiempo: t })} etiqueta={(t) => `${t} min`} />
      <Texto tipo="suave">Presupuesto por persona: desde</Texto>
      <Chips opciones={DESDE} elegidas={[desde]} alElegir={(d) => setP({ ...p, presupuesto: [d, Math.max(d + 5, hasta)] })}
        etiqueta={(d) => `${d} €`} />
      <Texto tipo="suave">hasta</Texto>
      <Chips opciones={HASTA.filter((h) => h > desde)} elegidas={[hasta]} alElegir={(h) => setP({ ...p, presupuesto: [desde, h] })}
        etiqueta={(h) => (h === yo.presupuesto_sin_limite ? 'Sin tope' : `${h} €`)} />
      <Boton texto="Guardar preferencias" tipo="secundario" cargando={ocupado}
        alPulsar={() => guardar(() => api('PUT', '/yo/preferencias', p))} />
      {aviso}
    </Seccion>
  );
}

function TuLista({ yo, alCambiar }: { yo: Yo; alCambiar: () => void }) {
  const [enlace, setEnlace] = useState('');
  const [resultado, setResultado] = useState<string | null>(null);
  const { guardar, ocupado, aviso } = useGuardar(alCambiar);
  return (
    <Seccion titulo="Tu lista de Google Maps">
      <Texto tipo="suave">En Google Maps: abre tu lista → Compartir → copiar enlace, y pégalo aquí. Si ya la tenías, se vuelve a leer.</Texto>
      <Campo placeholder="https://maps.app.goo.gl/…" value={enlace} onChangeText={setEnlace} autoCapitalize="none"
        autoCorrect={false} keyboardType="url" />
      <Boton texto="Añadir o actualizar mi lista" cargando={ocupado} desactivado={!enlace.trim()}
        alPulsar={() => guardar(async () => {
          const r = await api<{ estado: string }>('POST', '/lista/enlace', { enlace });
          setResultado(r.estado === 'lista' ? '¡Lista añadida!' : 'Pedido: en unos minutos tendrás tu lista.');
          setEnlace('');
        })} />
      {resultado ? <Texto>{resultado}</Texto> : aviso}
      {yo.lista.mensaje ? <Texto tipo="suave">{yo.lista.mensaje}</Texto> : null}
    </Seccion>
  );
}

function Cuenta({ yo }: { yo: Yo }) {
  const { salir } = useSesion();
  const [confirmacion, setConfirmacion] = useState('');
  const [abierto, setAbierto] = useState(false);
  const { guardar, ocupado, aviso } = useGuardar(salir);

  function borrar() {
    Alert.alert('Borrar tu cuenta', 'Se borrarán tu lista, tus valoraciones, tus amigos y tu perfil. No se puede deshacer.', [
      { text: 'Cancelar', style: 'cancel' },
      { text: 'Borrar', style: 'destructive', onPress: () => guardar(() => api('POST', '/yo/borrar', { confirmacion: 'BORRAR' })) },
    ]);
  }

  return (
    <Seccion titulo="Cuenta">
      <Texto tipo="suave">{yo.correo}</Texto>
      {yo.alias ? <Boton texto="Compartir mi perfil" tipo="secundario" alPulsar={() => compartirPerfil(yo.alias ?? '')} /> : null}
      <Boton texto="Cerrar sesión" tipo="secundario" alPulsar={salir} />
      {abierto ? (
        <>
          <Texto>Escribe BORRAR para confirmar.</Texto>
          <Campo value={confirmacion} onChangeText={setConfirmacion} autoCapitalize="characters" autoCorrect={false} />
          <Boton texto="Borrar mi cuenta" cargando={ocupado} desactivado={confirmacion.trim() !== 'BORRAR'} alPulsar={borrar} />
          {aviso}
        </>
      ) : (
        <Boton texto="Borrar mi cuenta" tipo="texto" alPulsar={() => setAbierto(true)} />
      )}
    </Seccion>
  );
}

export default function Ajustes() {
  const yo = useCarga(() => api<Yo>('GET', '/yo'), []);
  const d = yo.datos;
  if (!d) return <Pantalla>{yo.error ? <Texto tipo="error">{yo.error}</Texto> : <Cargando />}</Pantalla>;
  return (
    <Pantalla>
      <Foto yo={d} alCambiar={yo.recargar} />
      <DatosPersonales yo={d} alCambiar={yo.recargar} />
      <Zona yo={d} alCambiar={yo.recargar} />
      <PreferenciasComer yo={d} alCambiar={yo.recargar} />
      <TuLista yo={d} alCambiar={yo.recargar} />
      <Cuenta yo={d} />
    </Pantalla>
  );
}
