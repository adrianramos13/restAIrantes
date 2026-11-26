// Pedir datos a la API desde una pantalla: guarda el resultado, si está cargando y el error para enseñarlo.
// Se vuelve a pedir cuando cambian las `dependencias` o al llamar a recargar().
import { useCallback, useEffect, useRef, useState } from 'react';

import { mensaje } from './api';

interface Carga<T> {
  datos: T | null;
  error: string | null;
  cargando: boolean;
  recargar: () => void;
}

interface Estado<T> {
  clave: string | null;   // de qué petición son estos datos
  datos: T | null;
  error: string | null;
}

export function useCarga<T>(cargar: () => Promise<T>, dependencias: readonly unknown[]): Carga<T> {
  const [vuelta, setVuelta] = useState(0);
  const clave = `${JSON.stringify(dependencias)}#${vuelta}`;
  const [estado, setEstado] = useState<Estado<T>>({ clave: null, datos: null, error: null });
  const ultimoCargar = useRef(cargar);

  useEffect(() => {
    ultimoCargar.current = cargar;
  });

  useEffect(() => {
    let vigente = true;   // si cambia algo antes de que llegue la respuesta, la vieja no pisa a la nueva
    ultimoCargar.current()
      .then((datos) => vigente && setEstado({ clave, datos, error: null }))
      .catch((e: unknown) => vigente && setEstado((antes) => ({ clave, datos: antes.datos, error: mensaje(e) })));
    return () => {
      vigente = false;
    };
  }, [clave]);

  const recargar = useCallback(() => setVuelta((v) => v + 1), []);
  return { datos: estado.datos, error: estado.error, cargando: estado.clave !== clave, recargar };
}
