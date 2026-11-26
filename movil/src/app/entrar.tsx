// Entrar con correo y contraseña (Supabase Auth, a través de la API), crear cuenta o recuperar la contraseña.
// Quien entraba con Google en la web puede crear aquí una contraseña con EL MISMO correo: ve sus mismos datos.
import { useState } from 'react';
import { KeyboardAvoidingView, Platform } from 'react-native';

import { Boton, Campo, Pantalla, Texto } from '@/components/ui';
import { api, guardarSesion, mensaje, Sesion } from '@/lib/api';
import { useSesion } from '@/lib/sesion';

type Modo = 'entrar' | 'registro' | 'recuperar' | 'codigo';

export default function Entrar() {
  const { entrar } = useSesion();
  const [modo, setModo] = useState<Modo>('entrar');
  const [correo, setCorreo] = useState('');
  const [contrasena, setContrasena] = useState('');
  const [nombre, setNombre] = useState('');
  const [codigo, setCodigo] = useState('');
  const [aviso, setAviso] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);

  async function hacer(accion: () => Promise<void>) {
    setError(null);
    setAviso(null);
    setOcupado(true);
    try {
      await accion();
    } catch (e) {
      setError(mensaje(e));
    } finally {
      setOcupado(false);
    }
  }

  const acciones: Record<Modo, () => Promise<void>> = {
    entrar: () => entrar(correo, contrasena),
    registro: async () => {
      const r = await api<{ mensaje: string }>('POST', '/auth/registrar', { correo, contrasena, nombre });
      setAviso(r.mensaje);
      setModo('entrar');
    },
    recuperar: async () => {
      await api('POST', '/auth/recuperar', { correo });
      setAviso('Te hemos enviado un código de 6 cifras por correo.');
      setModo('codigo');
    },
    codigo: async () => {
      const sesion = await api<Sesion>('POST', '/auth/nueva-contrasena', { correo, codigo, contrasena });
      await guardarSesion(sesion);
      await entrar(correo, contrasena);
    },
  };

  const titulos: Record<Modo, string> = {
    entrar: 'Entrar',
    registro: 'Crear cuenta',
    recuperar: 'Recuperar contraseña',
    codigo: 'Nueva contraseña',
  };

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <Pantalla>
        <Texto tipo="titulo" style={{ marginTop: 48 }}>
          ¿Dónde comemos?
        </Texto>
        <Texto tipo="suave">Tus restaurantes, los de tus amigos y sitios nuevos para descubrir.</Texto>
        <Texto tipo="subtitulo">{titulos[modo]}</Texto>

        {modo === 'registro' ? <Campo etiqueta="Nombre" value={nombre} onChangeText={setNombre} maxLength={40} /> : null}
        <Campo
          etiqueta="Correo"
          value={correo}
          onChangeText={setCorreo}
          autoCapitalize="none"
          autoComplete="email"
          keyboardType="email-address"
          editable={modo !== 'codigo'}
        />
        {modo === 'codigo' ? (
          <Campo etiqueta="Código del correo" value={codigo} onChangeText={setCodigo} keyboardType="number-pad" maxLength={6} />
        ) : null}
        {modo !== 'recuperar' ? (
          <Campo
            etiqueta={modo === 'codigo' ? 'Contraseña nueva' : 'Contraseña'}
            value={contrasena}
            onChangeText={setContrasena}
            secureTextEntry
            autoComplete={modo === 'entrar' ? 'current-password' : 'new-password'}
          />
        ) : null}

        {aviso ? <Texto>{aviso}</Texto> : null}
        {error ? <Texto tipo="error">{error}</Texto> : null}
        <Boton texto={titulos[modo]} cargando={ocupado} alPulsar={() => hacer(acciones[modo])} />

        {modo === 'entrar' ? (
          <>
            <Boton texto="Crear una cuenta" tipo="secundario" alPulsar={() => setModo('registro')} />
            <Boton texto="He olvidado mi contraseña" tipo="texto" alPulsar={() => setModo('recuperar')} />
            <Texto tipo="suave">
              ¿Entrabas con Google en la web? Crea una cuenta con el mismo correo y verás tus mismos restaurantes.
            </Texto>
          </>
        ) : (
          <Boton texto="Volver" tipo="texto" alPulsar={() => setModo('entrar')} />
        )}
      </Pantalla>
    </KeyboardAvoidingView>
  );
}
