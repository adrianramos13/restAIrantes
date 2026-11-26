// Caja de dirección con sugerencias mientras escribes (Photon, el mismo servicio que la web, limitado a la
// Comunidad de Madrid). Si no eliges ninguna, lo escrito se busca después en la API (/geocodificar).
import { useEffect, useState } from 'react';
import { Pressable, Text, View } from 'react-native';

import { Campo } from '@/components/ui';
import { LETRA, RADIO, TAM_TEXTO, useColores } from '@/lib/tema';

const PHOTON = 'https://photon.komoot.io/api/';
const CAJA_MADRID = '-4.58,39.88,-3.05,41.17';   // lon/lat mín,máx
const ESPERA_MS = 300;

export interface Punto {
  lat: number;
  lon: number;
  texto: string;
}

interface Opcion extends Punto {
  principal: string;
  detalle: string;
}

interface Propiedades {
  name?: string;
  street?: string;
  housenumber?: string;
  district?: string;
  city?: string;
}

/** Como componentes/direccion.js: el nombre (o la calle) en grande y el barrio y la ciudad debajo. */
function etiquetas(p: Propiedades): { principal: string; detalle: string } {
  const calle = [p.street, p.housenumber].filter(Boolean).join(' ');
  const principal = p.name || calle || p.district || p.city || '';
  const detalle = [p.name ? calle : null, p.district, p.city].filter((x) => x && x !== principal);
  return { principal, detalle: [...new Set(detalle)].join(', ') };
}

interface Props {
  valor: string;
  alEscribir: (texto: string) => void;
  alElegir: (punto: Punto) => void;
  placeholder: string;
  etiqueta?: string;
  desactivado?: boolean;
  alEnviar?: () => void;   // Intro sin elegir sugerencia
}

export function CampoDireccion({ valor, alEscribir, alElegir, placeholder, etiqueta, desactivado = false, alEnviar }: Props) {
  const c = useColores();
  const [opciones, setOpciones] = useState<Opcion[]>([]);
  const [elegida, setElegida] = useState<string | null>(null);   // no volver a sugerir lo que se acaba de elegir
  const consulta = valor.trim();
  const buscar = !desactivado && consulta.length >= 3 && consulta !== elegida;

  useEffect(() => {
    if (!buscar) return;
    let vigente = true;
    const temporizador = setTimeout(async () => {
      try {
        const url = `${PHOTON}?q=${encodeURIComponent(consulta)}&limit=5&lat=40.4168&lon=-3.7038&bbox=${CAJA_MADRID}`;
        const r = (await (await fetch(url)).json()) as {
          features: { properties: Propiedades; geometry: { coordinates: [number, number] } }[];
        };
        const vistos = new Set<string>();
        const nuevas = r.features
          .map((f) => {
            const { principal, detalle } = etiquetas(f.properties);
            const texto = [principal, detalle].filter(Boolean).join(', ');
            return { principal, detalle, texto, lon: f.geometry.coordinates[0], lat: f.geometry.coordinates[1] };
          })
          .filter((o) => o.principal && !vistos.has(o.texto) && vistos.add(o.texto));
        if (vigente) setOpciones(nuevas);
      } catch {
        if (vigente) setOpciones([]);   // sin sugerencias: se puede seguir escribiendo a mano
      }
    }, ESPERA_MS);
    return () => {
      vigente = false;
      clearTimeout(temporizador);
    };
  }, [consulta, buscar]);

  return (
    <View style={{ zIndex: 10 }}>
      <Campo etiqueta={etiqueta} placeholder={placeholder} value={desactivado ? '' : valor} onChangeText={alEscribir}
        autoCorrect={false} editable={!desactivado} returnKeyType="search" onSubmitEditing={alEnviar}
        style={{ minHeight: 42, paddingVertical: 8, paddingLeft: 12, fontSize: TAM_TEXTO, opacity: desactivado ? 0.6 : 1 }} />
      {buscar && opciones.length ? (
        // direccion.css: la lista flota bajo la caja, con sombra
        <View style={{ position: 'absolute', left: 0, right: 0, top: '100%', marginTop: 4, paddingVertical: 4,
          backgroundColor: c.fondo, borderWidth: 1, borderColor: c.borde, borderRadius: RADIO,
          shadowColor: '#000', shadowOpacity: 0.15, shadowRadius: 8, shadowOffset: { width: 0, height: 4 }, elevation: 6 }}>
          {opciones.map((o) => (
            <Pressable
              key={o.texto}
              accessibilityRole="button"
              onPress={() => {
                setElegida(o.texto);
                alEscribir(o.texto);
                alElegir(o);
              }}
              style={({ pressed }) => ({ minHeight: 44, paddingVertical: 9, paddingHorizontal: 11.25,
                backgroundColor: pressed ? c.fondo2 : 'transparent' })}>
              <Text style={{ fontFamily: LETRA.normal, fontSize: TAM_TEXTO * 0.95, color: c.texto }}>{o.principal}</Text>
              {o.detalle ? (
                <Text style={{ fontFamily: LETRA.normal, fontSize: TAM_TEXTO * 0.8, color: c.texto, opacity: 0.7 }}>{o.detalle}</Text>
              ) : null}
            </Pressable>
          ))}
        </View>
      ) : null}
    </View>
  );
}
