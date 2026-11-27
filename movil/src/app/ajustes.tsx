// Ajustes de usuario, copia de app.ajustes_de_usuario: tu foto (tócala para cambiarla) y «Quitar foto»; Datos
// personales; De dónde eres; Tus listas; Preferencias. Además (no está en la web): tu @usuario, compartir tu perfil
// y borrar la cuenta (lo pide la App Store).
import * as ImagePicker from 'expo-image-picker';
import { Image } from 'expo-image';
import { router } from 'expo-router';
import { useState } from 'react';
import { Alert, Pressable, StyleSheet, Text, View } from 'react-native';

import { CampoDireccion, Punto } from '@/components/direccion';
import { Icono } from '@/components/icono';
import {
  Boton, Campo, Cargando, Deslizador, Info, Pantalla, Segmentado, Texto, TituloVentana, useAvisoBreve,
} from '@/components/ui';
import { api, mensaje, Preferencias, Yo } from '@/lib/api';
import { useCarga } from '@/lib/carga';
import { compartirPerfil } from '@/lib/compartir';
import { useSesion } from '@/lib/sesion';
import { LETRA, useColores } from '@/lib/tema';

const ESTADOS_LISTA: Record<string, string> = {
  sin_lista: 'Todavía no has añadido tu lista.',
  pendiente: '⏳ Pendiente de sincronizar. Las listas nuevas se procesan cuando el procesador del administrador está en '
    + 'marcha; si alguien ya tenía esta misma lista, se copia al momento.',
  procesando: '⚙️ Procesando tu lista ahora mismo…',
  lista: '✓ Tu lista está al día.',
  error: '⚠️ No se pudo procesar tu lista.',
};

type Avisar = (t: string) => void;

function Separador() {
  const c = useColores();
  return <View style={{ height: 1, backgroundColor: c.borde, marginVertical: 8 }} />;
}

function Negrita({ children }: { children: string }) {
  return <Texto style={{ fontFamily: LETRA.negrita }}>{children}</Texto>;
}

/** Un bloque con su botón: su propio error y, al ir bien, el aviso. */
function useGuardar(alGuardar: () => void) {
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function guardar(accion: () => Promise<unknown>) {
    setOcupado(true);
    setError(null);
    try {
      await accion();
      alGuardar();
    } catch (e) {
      setError(mensaje(e));
    } finally {
      setOcupado(false);
    }
  }
  return { guardar, ocupado, error: error ? <Info tipo="error">{error}</Info> : null };
}

/** componentes/avatar_perfil.*: 76 px con la cámara terracota; al tocarla se elige otra foto y se sube sola. */
function Foto({ yo, alCambiar }: { yo: Yo; alCambiar: () => void }) {
  const c = useColores();
  const { guardar, ocupado, error } = useGuardar(alCambiar);
  async function elegir() {
    const r = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'], allowsEditing: true, aspect: [1, 1], quality: 0.6, base64: true,
    });
    const base64 = r.canceled ? null : r.assets[0]?.base64;
    if (base64) await guardar(() => api('PUT', '/yo/foto', { imagen: `data:image/jpeg;base64,${base64}` }));
  }
  return (
    <>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 15 }}>
        <Pressable accessibilityRole="button" accessibilityLabel="Cambiar tu foto de perfil" onPress={elegir} disabled={ocupado}>
          <View style={[estilos.circulo, { backgroundColor: c.primario }]}>
            <Text style={estilos.inicial}>{(yo.nombre.trim()[0] ?? '?').toUpperCase()}</Text>
            {yo.foto ? <Image source={yo.foto} style={StyleSheet.absoluteFill} contentFit="cover" /> : null}
            {ocupado ? <View style={[StyleSheet.absoluteFill, { backgroundColor: 'rgba(0,0,0,0.45)', justifyContent: 'center' }]}><Cargando /></View> : null}
          </View>
          <View style={[estilos.camara, { backgroundColor: c.primario, borderColor: c.fondo }]}>
            <Icono nombre="camara" tam={16} color={c.fondo} />
          </View>
        </Pressable>
        <View>
          <Texto tipo="suave">Toca tu foto para cambiarla.</Texto>
          {yo.foto_propia ? (
            <Boton texto="Quitar foto" tipo="texto" icono="delete" ancho="contenido" alPulsar={() => guardar(() => api('DELETE', '/yo/foto'))} />
          ) : null}
        </View>
      </View>
      {error}
    </>
  );
}

function DatosPersonales({ yo, alCambiar }: { yo: Yo; alCambiar: () => void }) {
  const [nombre, setNombre] = useState(yo.nombre);
  const { guardar, ocupado, error } = useGuardar(alCambiar);
  return (
    <>
      <Negrita>Datos personales</Negrita>
      <Campo etiqueta="Nombre" ayuda="Es el nombre con el que te saluda la app." value={nombre} onChangeText={setNombre} maxLength={40} />
      <Texto tipo="suave">{`Tu correo es ${yo.correo}: identifica tu cuenta y tu lista y no se cambia aquí.`}</Texto>
      <Boton texto="Guardar nombre" cargando={ocupado} alPulsar={() => guardar(() => api('PUT', '/yo/nombre', { nombre }))} />
      {error}
    </>
  );
}

function Zona({ yo, alCambiar }: { yo: Yo; alCambiar: () => void }) {
  const [texto, setTexto] = useState('');
  const [punto, setPunto] = useState<Punto | null>(null);
  const { guardar, ocupado, error } = useGuardar(() => {
    setTexto('');
    setPunto(null);
    alCambiar();
  });
  const elegido = punto && punto.texto === texto ? punto : null;
  return (
    <>
      <Negrita>De dónde eres</Negrita>
      {yo.zona ? <Texto tipo="suave">{`Ahora: ${yo.zona}`}</Texto> : null}
      <CampoDireccion valor={texto} alEscribir={setTexto} alElegir={setPunto} placeholder="Tu barrio o pueblo, p. ej. Chamberí" />
      <Texto tipo="suave">Solo la usamos para proponerte gente de tu zona en Inicio. Nadie ve dónde vives.</Texto>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 15 }}>
        <Boton texto="Guardar zona" cargando={ocupado} desactivado={!texto.trim()} style={{ flex: 1 }}
          alPulsar={() => guardar(() => api('PUT', '/yo/zona', { zona: texto.replace(/\s+/g, ' ').trim().slice(0, 120), lat: elegido?.lat, lon: elegido?.lon }))} />
        {yo.zona ? <Boton texto="Quitar" tipo="texto" ancho="contenido" alPulsar={() => guardar(() => api('DELETE', '/yo/zona'))} /> : null}
      </View>
      {error}
    </>
  );
}

function TusListas({ yo, alCambiar }: { yo: Yo; alCambiar: () => void }) {
  const [enlace, setEnlace] = useState(yo.lista.enlace ?? '');
  const { guardar, ocupado, error } = useGuardar(alCambiar);
  const estado = yo.lista.estado ?? 'sin_lista';
  return (
    <>
      <Negrita>Tus listas</Negrita>
      <Texto>{ESTADOS_LISTA[estado] ?? estado}</Texto>
      {yo.lista.actualizado_en ? (
        <Texto tipo="suave">{`Última sincronización: ${yo.lista.actualizado_en.slice(0, 16).replace('T', ' ')} (UTC)`}</Texto>
      ) : null}
      {yo.lista.mensaje ? <Texto tipo="suave">{yo.lista.mensaje}</Texto> : null}
      <Campo etiqueta="Enlace de tu lista" ayuda="En Google Maps: abre tu lista → Compartir → copiar enlace." value={enlace}
        onChangeText={setEnlace} placeholder="https://maps.app.goo.gl/..." autoCapitalize="none" autoCorrect={false} keyboardType="url" />
      <Boton texto="Guardar y sincronizar" tipo="primario" cargando={ocupado} desactivado={estado === 'procesando'}
        alPulsar={() => guardar(() => api('POST', '/lista/enlace', { enlace }))} />
      {error}
      <Texto tipo="suave">Sincronizar vuelve a leer tu lista de Google Maps: añade los sitios nuevos y quita los que hayas borrado.</Texto>
    </>
  );
}

function PreferenciasComer({ yo, alCambiar, avisar }: { yo: Yo; alCambiar: () => void; avisar: Avisar }) {
  const [p, setP] = useState<Preferencias>(yo.preferencias);
  const { guardar, ocupado, error } = useGuardar(() => {
    avisar('Preferencias guardadas');
    alCambiar();
  });
  return (
    <>
      <Negrita>Preferencias</Negrita>
      <Texto tipo="suave">Lo que viene ya puesto al buscar en <Text style={{ fontFamily: LETRA.negrita }}>Comer hoy</Text>.</Texto>
      <Segmentado titulo="¿Cómo soléis ir?" opciones={['En coche', 'A pie'] as const} elegidas={[p.transporte]}
        alElegir={(t) => setP({ ...p, transporte: t })} etiqueta={(t) => (t === 'A pie' ? '🚶 A pie' : '🚗 Coche')} />
      <Deslizador titulo="Tiempo máximo" min={5} max={60} paso={5} valor={[p.tiempo]} alCambiar={(v) => setP({ ...p, tiempo: v[0] })}
        formato={(v) => `${v} min`} />
      <Deslizador titulo="Presupuesto por persona" min={0} max={yo.presupuesto_sin_limite} paso={5} valor={[...p.presupuesto]}
        alCambiar={(v) => setP({ ...p, presupuesto: [v[0], v[1]] })} formato={(v) => `${v} €`} />
      <Boton texto="Guardar preferencias" cargando={ocupado} alPulsar={() => guardar(() => api('PUT', '/yo/preferencias', p))} />
      {error}
    </>
  );
}

function Cuenta({ yo, alCambiar }: { yo: Yo; alCambiar: () => void }) {
  const { salir } = useSesion();
  const [alias, setAlias] = useState(yo.alias ?? '');
  const [confirmacion, setConfirmacion] = useState('');
  const [abierto, setAbierto] = useState(false);
  const a = useGuardar(alCambiar);
  const b = useGuardar(salir);

  function borrar() {
    Alert.alert('Borrar tu cuenta', 'Se borrarán tu lista, tus valoraciones, tus amigos y tu perfil. No se puede deshacer.', [
      { text: 'Cancelar', style: 'cancel' },
      { text: 'Borrar', style: 'destructive', onPress: () => b.guardar(() => api('POST', '/yo/borrar', { confirmacion: 'BORRAR' })) },
    ]);
  }

  return (
    <>
      <Negrita>Cuenta</Negrita>
      <Campo etiqueta="Nombre de usuario" ayuda="Con él te encuentran tus amigos. Tu correo no lo ve nadie." placeholder="Ej. ana_g"
        value={alias} onChangeText={setAlias} autoCapitalize="none" autoCorrect={false} maxLength={21} />
      <Boton texto="Guardar nombre de usuario" cargando={a.ocupado} desactivado={!alias.trim() || alias.replace('@', '') === yo.alias}
        alPulsar={() => a.guardar(() => api('PUT', '/yo/alias', { alias }))} />
      {a.error}
      {yo.alias ? <Boton texto="Compartir mi perfil" icono="share" alPulsar={() => compartirPerfil(yo.alias ?? '')} /> : null}
      {abierto ? (
        <>
          <Texto>Escribe BORRAR para confirmar.</Texto>
          <Campo value={confirmacion} onChangeText={setConfirmacion} autoCapitalize="characters" autoCorrect={false} />
          <Boton texto="Borrar mi cuenta" icono="delete" cargando={b.ocupado} desactivado={confirmacion.trim() !== 'BORRAR'} alPulsar={borrar} />
          {b.error}
        </>
      ) : (
        <Boton texto="Borrar mi cuenta" tipo="texto" icono="delete" alPulsar={() => setAbierto(true)} />
      )}
    </>
  );
}

export default function Ajustes() {
  const c = useColores();
  const yo = useCarga(() => api<Yo>('GET', '/yo'), []);
  const [aviso, avisar] = useAvisoBreve();
  const d = yo.datos;
  return (
    <View style={{ flex: 1, backgroundColor: c.fondo }}>
      <Pantalla margen={22.5}>
        <TituloVentana titulo="Ajustes de usuario" alCerrar={() => router.back()} />
        {!d ? (yo.error ? <Info tipo="error">{yo.error}</Info> : <Cargando />) : (
          <>
            <Foto yo={d} alCambiar={yo.recargar} />
            <Separador />
            <DatosPersonales yo={d} alCambiar={yo.recargar} />
            <Separador />
            <Zona yo={d} alCambiar={yo.recargar} />
            <Separador />
            <TusListas yo={d} alCambiar={yo.recargar} />
            <Separador />
            <PreferenciasComer yo={d} alCambiar={yo.recargar} avisar={avisar} />
            <Separador />
            <Cuenta yo={d} alCambiar={yo.recargar} />
          </>
        )}
      </Pantalla>
      {aviso}
    </View>
  );
}

const estilos = StyleSheet.create({
  circulo: { width: 76, height: 76, borderRadius: 38, overflow: 'hidden', alignItems: 'center', justifyContent: 'center' },
  inicial: { fontFamily: LETRA.negrita, fontSize: 32, color: '#FFFFFF' },
  camara: {
    position: 'absolute', right: -2, bottom: -2, width: 28, height: 28, borderRadius: 14, borderWidth: 3,
    alignItems: 'center', justifyContent: 'center',
  },
});
