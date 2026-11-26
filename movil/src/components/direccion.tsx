// Caja de dirección con sugerencias mientras escribes (Photon, el mismo servicio que la web, limitado a la
// Comunidad de Madrid). Si no eliges ninguna, lo escrito se busca después en la API (/geocodificar).
import { useEffect, useState } from 'react';
import { Pressable, View } from 'react-native';

import { Campo, Texto } from '@/components/ui';
import { RADIO, useColores } from '@/lib/tema';

const PHOTON = 'https://photon.komoot.io/api/';
const CAJA_MADRID = '-4.58,39.88,-3.05,41.17';   // lon/lat mín,máx
const ESPERA_MS = 300;

export interface Punto {
  lat: number;
  lon: number;
  texto: string;
}

interface Propiedades {
  name?: string;
  street?: string;
  housenumber?: string;
  district?: string;
  city?: string;
}

function textoDe(p: Propiedades): string {
  const calle = [p.street, p.housenumber].filter(Boolean).join(' ');
  const principal = p.name || calle || p.district || p.city || '';
  const detalle = [p.name ? calle : null, p.district, p.city].filter((x) => x && x !== principal);
  return [principal, ...new Set(detalle)].join(', ');
}

interface Props {
  valor: string;
  alEscribir: (texto: string) => void;
  alElegir: (punto: Punto) => void;
  placeholder: string;
  etiqueta?: string;
}

export function CampoDireccion({ valor, alEscribir, alElegir, placeholder, etiqueta }: Props) {
  const c = useColores();
  const [opciones, setOpciones] = useState<Punto[]>([]);
  const [elegida, setElegida] = useState<string | null>(null);   // no volver a sugerir lo que se acaba de elegir
  const consulta = valor.trim();
  const buscar = consulta.length >= 3 && consulta !== elegida;

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
          .map((f) => ({ texto: textoDe(f.properties), lon: f.geometry.coordinates[0], lat: f.geometry.coordinates[1] }))
          .filter((o) => o.texto && !vistos.has(o.texto) && vistos.add(o.texto));
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
    <View style={{ gap: 6 }}>
      <Campo etiqueta={etiqueta} placeholder={placeholder} value={valor} onChangeText={alEscribir} autoCorrect={false} />
      {buscar && opciones.length ? (
        <View style={{ borderWidth: 1, borderColor: c.borde, borderRadius: RADIO, overflow: 'hidden' }}>
          {opciones.map((o) => (
            <Pressable
              key={o.texto}
              accessibilityRole="button"
              onPress={() => {
                setElegida(o.texto);
                alEscribir(o.texto);
                alElegir(o);
              }}
              style={({ pressed }) => ({ padding: 12, backgroundColor: pressed ? c.borde : c.fondo2 })}>
              <Texto lineas={2}>{o.texto}</Texto>
            </Pressable>
          ))}
        </View>
      ) : null}
    </View>
  );
}
