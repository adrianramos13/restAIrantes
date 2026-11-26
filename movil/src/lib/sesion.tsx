// Quién ha entrado. La sesión se guarda en el llavero del móvil (SecureStore): no hay que entrar cada vez.
import { createContext, ReactNode, useContext, useEffect, useState } from 'react';

import { alCaducarSesion, api, cargarSesion, guardarSesion, Sesion } from './api';

interface ContextoSesion {
  sesion: Sesion | null;
  cargando: boolean;
  entrar: (correo: string, contrasena: string) => Promise<void>;
  salir: () => Promise<void>;
}

const Contexto = createContext<ContextoSesion | null>(null);

export function ProveedorSesion({ children }: { children: ReactNode }) {
  const [sesion, setSesion] = useState<Sesion | null>(null);
  const [cargando, setCargando] = useState(true);

  useEffect(() => {
    alCaducarSesion(() => setSesion(null));
    cargarSesion()
      .then(setSesion)
      .catch(() => setSesion(null))
      .finally(() => setCargando(false));
  }, []);

  async function entrar(correo: string, contrasena: string) {
    const nueva = await api<Sesion>('POST', '/auth/entrar', { correo, contrasena });
    await guardarSesion(nueva);
    setSesion(nueva);
  }

  async function salir() {
    await guardarSesion(null);
    setSesion(null);
  }

  return <Contexto.Provider value={{ sesion, cargando, entrar, salir }}>{children}</Contexto.Provider>;
}

export function useSesion(): ContextoSesion {
  const contexto = useContext(Contexto);
  if (!contexto) throw new Error('useSesion fuera de ProveedorSesion');
  return contexto;
}
