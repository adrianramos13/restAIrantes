// Entrar, copia de app.pantalla_entrar + acceso.formulario_cuentas: la portada («Tus sitios de Google Maps»),
// «o con tu correo», Entrar | Crear cuenta y, al entrar, «¿Has olvidado tu contraseña?» (código por correo).
// ponytail: sin «Entrar con Google» (necesita el flujo OAuth de Supabase en el móvil); quien entraba con Google en la
// web crea aquí una contraseña con el mismo correo y ve sus mismos datos.
import { useState } from 'react';
import { KeyboardAvoidingView, Platform, View } from 'react-native';

import { Portada } from '@/components/portada';
import { Boton, Campo, Desplegable, Info, Pantalla, Segmentado, Texto } from '@/components/ui';
import { api, guardarSesion, mensaje, Sesion } from '@/lib/api';
import { useSesion } from '@/lib/sesion';

type Modo = 'Entrar' | 'Crear cuenta';

/** Un botón que hace algo con la API y enseña su error (st.error). */
function useAccion() {
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function hacer(accion: () => Promise<void>) {
    setError(null);
    setOcupado(true);
    try {
      await accion();
    } catch (e) {
      setError(mensaje(e));
    } finally {
      setOcupado(false);
    }
  }
  return { hacer, ocupado, error: error ? <Info tipo="error">{error}</Info> : null, setError };
}

function FormularioEntrar() {
  const { entrar } = useSesion();
  const [correo, setCorreo] = useState('');
  const [contrasena, setContrasena] = useState('');
  const { hacer, ocupado, error } = useAccion();
  return (
    <>
      <Campo etiqueta="Correo" value={correo} onChangeText={setCorreo} autoCapitalize="none" autoComplete="email" keyboardType="email-address" />
      <Campo etiqueta="Contraseña" value={contrasena} onChangeText={setContrasena} secureTextEntry autoComplete="current-password" />
      <Boton tipo="primario" texto="Entrar" cargando={ocupado} alPulsar={() => hacer(() => entrar(correo, contrasena))} />
      {error}
    </>
  );
}

function RecuperarContrasena() {
  const { entrar } = useSesion();
  const [correo, setCorreo] = useState('');
  const [codigo, setCodigo] = useState('');
  const [nueva, setNueva] = useState('');
  const [pedido, setPedido] = useState(false);
  const pedir = useAccion();
  const cambiar = useAccion();
  return (
    <Desplegable titulo="¿Has olvidado tu contraseña?">
      <Campo etiqueta="Correo de tu cuenta" value={correo} onChangeText={setCorreo} autoCapitalize="none" autoComplete="email"
        keyboardType="email-address" />
      <Boton texto="Enviarme un código" cargando={pedir.ocupado}
        alPulsar={() => pedir.hacer(async () => { await api('POST', '/auth/recuperar', { correo }); setPedido(true); })} />
      {pedir.error}
      {pedido ? (
        <>
          <Info>Si hay una cuenta con ese correo, te llegará un código de 6 cifras.</Info>
          <Campo etiqueta="Código del correo" value={codigo} onChangeText={setCodigo} keyboardType="number-pad" maxLength={10} />
          <Campo etiqueta="Contraseña nueva" value={nueva} onChangeText={setNueva} secureTextEntry autoComplete="new-password" />
          <Boton tipo="primario" texto="Cambiar contraseña y entrar" cargando={cambiar.ocupado}
            alPulsar={() => cambiar.hacer(async () => {
              const sesion = await api<Sesion>('POST', '/auth/nueva-contrasena', { correo, codigo, contrasena: nueva });
              await guardarSesion(sesion);
              await entrar(correo, nueva);
            })} />
          {cambiar.error}
        </>
      ) : null}
    </Desplegable>
  );
}

function FormularioRegistro() {
  const [nombre, setNombre] = useState('');
  const [correo, setCorreo] = useState('');
  const [contrasena, setContrasena] = useState('');
  const [repetida, setRepetida] = useState('');
  const [listo, setListo] = useState<string | null>(null);
  const { hacer, ocupado, error, setError } = useAccion();
  return (
    <>
      <Campo etiqueta="Nombre" value={nombre} onChangeText={setNombre} maxLength={40} autoComplete="name" />
      <Campo etiqueta="Correo" value={correo} onChangeText={setCorreo} autoCapitalize="none" autoComplete="email" keyboardType="email-address" />
      <Campo etiqueta="Contraseña" ayuda="Al menos 8 caracteres." value={contrasena} onChangeText={setContrasena} secureTextEntry
        autoComplete="new-password" />
      <Campo etiqueta="Repite la contraseña" value={repetida} onChangeText={setRepetida} secureTextEntry autoComplete="new-password" />
      <Boton tipo="primario" texto="Crear cuenta" cargando={ocupado} alPulsar={() => {
        if (contrasena !== repetida) {
          setError('Las dos contraseñas no coinciden.');
          return;
        }
        hacer(async () => {
          await api('POST', '/auth/registrar', { correo, contrasena, nombre });
          setListo(`¡Listo! Te hemos enviado un correo a ${correo.trim().toLowerCase()}. Ábrelo para confirmar tu cuenta y después entra con tu contraseña.`);
        });
      }} />
      {error}
      {listo ? <Info tipo="exito">{listo}</Info> : null}
    </>
  );
}

export default function Entrar() {
  const [modo, setModo] = useState<Modo>('Entrar');
  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <Pantalla>
        <Portada fotos={[]} momento="🍽️ Tus sitios de Google Maps" subtitulo="Entra para ver los restaurantes de tu lista." />
        <Texto tipo="suave">
          ¿Entrabas con Google en la web? Crea aquí una cuenta con el mismo correo y verás tus mismos restaurantes.
        </Texto>
        <View style={{ marginVertical: 7.5 }}>
          <Texto style={{ textAlign: 'center', opacity: 0.7 }}>o con tu correo</Texto>
        </View>
        <Segmentado opciones={['Entrar', 'Crear cuenta'] as const} elegidas={[modo]} alElegir={setModo} />
        {modo === 'Entrar' ? (
          <>
            <FormularioEntrar />
            <RecuperarContrasena />
          </>
        ) : <FormularioRegistro />}
      </Pantalla>
    </KeyboardAvoidingView>
  );
}
