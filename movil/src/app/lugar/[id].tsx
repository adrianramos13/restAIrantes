// Ficha de un sitio de Descubrir aún sin analizar: sus datos básicos (y ficha rápida) y el botón «Analizar».
// Mientras se analiza, pregunta cada 5 s; al terminar, abre la ficha completa del restaurante.
import { Image } from 'expo-image';
import { router, Stack, useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { Linking, Platform } from 'react-native';

import { formatoNota } from '@/components/tarjeta';
import { Boton, Caja, Cargando, Pantalla, Texto } from '@/components/ui';
import { api, Lugar, mensaje } from '@/lib/api';
import { useCarga } from '@/lib/carga';
import { ESTADOS } from '@/lib/lugares';
import { RADIO } from '@/lib/tema';

const SEGUNDOS_ENTRE_COMPROBACIONES = 5;

export default function FichaLugar() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const lugar = useCarga(() => api<Lugar>('GET', `/lugares/${encodeURIComponent(id)}`), [id]);
  const [error, setError] = useState<string | null>(null);
  const [pidiendo, setPidiendo] = useState(false);
  const l = lugar.datos;
  const enCamino = l?.estado === 'pendiente' || l?.estado === 'procesando';

  useEffect(() => {
    if (l?.estado === 'analizado' && l.restaurante_id) {
      router.replace({ pathname: '/restaurante/[id]', params: { id: String(l.restaurante_id) } });
    }
  }, [l]);

  useEffect(() => {
    if (!enCamino) return;
    const temporizador = setInterval(lugar.recargar, SEGUNDOS_ENTRE_COMPROBACIONES * 1000);
    return () => clearInterval(temporizador);
  }, [enCamino, lugar.recargar]);

  async function analizar() {
    setError(null);
    setPidiendo(true);
    try {
      await api('POST', `/lugares/${encodeURIComponent(id)}/analizar`);
      lugar.recargar();
    } catch (e) {
      setError(mensaje(e));
    } finally {
      setPidiendo(false);
    }
  }

  if (lugar.cargando && !l) return <Pantalla><Cargando /></Pantalla>;
  if (!l) return <Pantalla><Texto tipo="error">{lugar.error ?? 'No se ha encontrado.'}</Texto></Pantalla>;

  const destino = `${l.lat},${l.lon}`;
  return (
    <Pantalla>
      <Stack.Screen options={{ title: l.nombre }} />
      {l.foto ? <Image source={l.foto} style={{ width: '100%', aspectRatio: 1.5, borderRadius: RADIO }} contentFit="cover" /> : null}
      <Texto tipo="titulo">{l.nombre}</Texto>
      <Texto tipo="suave">{[l.cocina, l.nota !== null ? formatoNota(l.nota) : null].filter(Boolean).join(' · ')}</Texto>
      {l.direccion ? <Texto tipo="suave">{[l.direccion, l.ciudad].filter(Boolean).join(', ')}</Texto> : null}
      <Texto tipo="suave">{l.estado ? ESTADOS[l.estado] : ''}</Texto>

      {l.estado === 'sin_analizar' || l.estado === 'error' ? (
        <Caja>
          <Texto>¿Quieres su ficha completa? La analizamos con sus reseñas: tipo de cocina, platos que destacan y precio.</Texto>
          <Boton texto="Analizar" cargando={pidiendo} alPulsar={analizar} />
        </Caja>
      ) : null}
      {enCamino ? (
        <Caja>
          <Cargando />
          <Texto>Analizando… En un par de minutos tendrá su ficha completa. Puedes salir y volver luego.</Texto>
        </Caja>
      ) : null}
      {error ? <Texto tipo="error">{error}</Texto> : null}

      <Boton texto="Cómo llegar" tipo="secundario" alPulsar={() => Linking.openURL(
        Platform.OS === 'ios' ? `https://maps.apple.com/?daddr=${destino}` : `https://www.google.com/maps/dir/?api=1&destination=${destino}`)} />
      {l.web ? <Boton texto="Web" tipo="texto" alPulsar={() => Linking.openURL(l.web as string)} /> : null}
      {l.telefono ? <Boton texto={`Llamar: ${l.telefono}`} tipo="texto" alPulsar={() => Linking.openURL(`tel:${l.telefono}`)} /> : null}
    </Pantalla>
  );
}
