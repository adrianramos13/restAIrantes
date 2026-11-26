// Ficha de un sitio de Descubrir, copia de explorar._ficha_lugar: si está analizado, la ficha completa del
// restaurante; si no, la etiqueta de su estado, categoría/dirección/ciudad, «Google Maps» y «Web», el teléfono,
// «Analizar este restaurante» (mientras se analiza, mira cada 5 s y se abre sola con el resultado) y
// «¿Ha cerrado? Avísanos».
import { router, Stack, useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { Linking, Text, View } from 'react-native';

import { Icono, NombreIcono } from '@/components/icono';
import { Boton, Cargando, Info, Pantalla, Texto, TituloVentana, useAvisoBreve } from '@/components/ui';
import { api, Lugar, mensaje } from '@/lib/api';
import { useCarga } from '@/lib/carga';
import { ESTADOS } from '@/lib/lugares';
import { LETRA, TAM_PEQUENO, useColores } from '@/lib/tema';

const SEGUNDOS_ENTRE_COMPROBACIONES = 5;
const MARGEN = 22.5;

// explorar.ESTADOS: color e icono de la etiqueta (st.badge)
const ETIQUETA: Record<string, { color: 'green' | 'orange' | 'red' | 'gray'; icono: NombreIcono }> = {
  analizado: { color: 'green', icono: 'verified' },
  pendiente: { color: 'orange', icono: 'hourglass_top' },
  procesando: { color: 'orange', icono: 'hourglass_top' },
  error: { color: 'red', icono: 'error' },
  sin_analizar: { color: 'gray', icono: 'info' },
  cerrado: { color: 'red', icono: 'block' },
};
const COLORES_ETIQUETA = {
  green: { fondo: 'rgba(33, 195, 84, 0.1)', claro: '#158237', oscuro: '#5CE488' },
  orange: { fondo: 'rgba(255, 164, 33, 0.1)', claro: '#E2660C', oscuro: '#FFBD45' },
  red: { fondo: 'rgba(255, 43, 43, 0.09)', claro: '#BD4043', oscuro: '#FF6C6C' },
  gray: { fondo: 'rgba(128, 132, 149, 0.1)', claro: '#555867', oscuro: '#BFC5D3' },
};

export default function FichaLugar() {
  const c = useColores();
  const { id } = useLocalSearchParams<{ id: string }>();
  const lugar = useCarga(() => api<Lugar>('GET', `/lugares/${encodeURIComponent(id)}`), [id]);
  const [error, setError] = useState<string | null>(null);
  const [pidiendo, setPidiendo] = useState(false);
  const [avisado, setAvisado] = useState(false);
  const [aviso, avisar] = useAvisoBreve();
  const l = lugar.datos;
  const estado = l?.estado ?? 'sin_analizar';
  const enCamino = estado === 'pendiente' || estado === 'procesando';

  useEffect(() => {   // analizado: su ficha completa en lugar de esta
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
      avisar('¡Pedido! En un par de minutos tendrá su ficha completa.');
      lugar.recargar();
    } catch (e) {
      setError(mensaje(e));
    } finally {
      setPidiendo(false);
    }
  }

  async function avisarCerrado() {
    setError(null);
    try {
      await api('POST', `/lugares/${encodeURIComponent(id)}/cerrado`);
      setAvisado(true);
      avisar('Gracias: ya no saldrá en Explorar.');
    } catch (e) {
      setError(mensaje(e));
    }
  }

  if (!l) {
    return (
      <Pantalla margen={MARGEN}>
        <Stack.Screen options={{ headerShown: false }} />
        <TituloVentana titulo="" alCerrar={() => router.back()} />
        {lugar.error ? <Info tipo="error">{lugar.error}</Info> : <Cargando />}
      </Pantalla>
    );
  }

  const etiqueta = ETIQUETA[estado] ?? ETIQUETA.sin_analizar;
  const color = COLORES_ETIQUETA[etiqueta.color];
  const colorTexto = c.texto === '#1F1A14' ? color.claro : color.oscuro;
  const consulta = encodeURIComponent(`${l.nombre} ${l.lat},${l.lon}`);
  const datos = [l.categoria ?? l.cocina, l.direccion, l.ciudad].filter(Boolean).join('\n');

  return (
    <View style={{ flex: 1, backgroundColor: c.fondo }}>
      <Stack.Screen options={{ headerShown: false }} />
      <Pantalla margen={MARGEN}>
        <TituloVentana titulo={l.nombre} alCerrar={() => router.back()} />
        <View style={{ flexDirection: 'row', alignSelf: 'flex-start', alignItems: 'center', gap: 4, paddingHorizontal: 6,
          paddingVertical: 1, borderRadius: 6, backgroundColor: color.fondo }}>
          <Icono nombre={etiqueta.icono} tam={13} color={colorTexto} />
          <Text style={{ fontFamily: LETRA.normal, fontSize: TAM_PEQUENO, lineHeight: 21, color: colorTexto }}>{ESTADOS[estado]}</Text>
        </View>
        {datos ? <Texto>{datos}</Texto> : null}
        <View style={{ flexDirection: 'row', gap: 15 }}>
          <Boton texto="Google Maps" icono="map" ancho="contenido"
            alPulsar={() => Linking.openURL(`https://www.google.com/maps/search/?api=1&query=${consulta}`)} />
          {l.web ? <Boton texto="Web" icono="language" ancho="contenido" alPulsar={() => Linking.openURL(l.web as string)} /> : null}
        </View>
        {l.telefono ? <Texto tipo="suave">{`Teléfono: ${l.telefono}`}</Texto> : null}
        {error ? <Info tipo="error">{error}</Info> : null}
        {avisado ? <Info tipo="exito">Gracias por avisar: ya no sale en Explorar.</Info>
          : estado === 'cerrado' ? <Info tipo="aviso">Según Google Maps ha cerrado, así que ya no sale en Explorar.</Info> : (
            <>
              {enCamino ? (
                <Info>Analizando (nota, precio, foto y lo que dicen sus reseñas). Suele tardar uno o dos minutos: esta ventana se actualiza sola.</Info>
              ) : (
                <>
                  <Texto tipo="suave">
                    Aún no sabemos qué dicen sus reseñas. Al analizarlo tendrá su ficha completa (nota, precio, lo que destacan) y
                    podrás añadirlo a tu eatlist o marcar «He ido».
                  </Texto>
                  <Boton texto="Analizar este restaurante" tipo="primario" icono="auto_awesome" cargando={pidiendo} alPulsar={analizar} />
                </>
              )}
              <Boton texto="¿Ha cerrado? Avísanos" tipo="texto" icono="storefront" ancho="contenido" alPulsar={avisarCerrado} />
            </>
          )}
      </Pantalla>
      {aviso}
    </View>
  );
}
