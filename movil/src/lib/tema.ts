// Los colores de la app de Streamlit (.streamlit/config.toml): crema + terracota, en claro y oscuro.
import { useColorScheme } from 'react-native';

const CLARO = {
  primario: '#C2410C',
  fondo: '#FBF7F2',
  fondo2: '#F3ECE3',
  texto: '#1F1A14',
  textoSuave: '#6B6157',
  borde: '#E9E1D6',
  enlace: '#9A3412',
  sobrePrimario: '#FFFFFF',
  error: '#B91C1C',
};

const OSCURO: typeof CLARO = {
  primario: '#FB923C',
  fondo: '#16130F',
  fondo2: '#221E19',
  texto: '#F3EDE4',
  textoSuave: '#B5AA9C',
  borde: '#3A332B',
  enlace: '#FDBA74',
  sobrePrimario: '#16130F',
  error: '#F87171',
};

export type Colores = typeof CLARO;

export function useColores(): Colores {
  return useColorScheme() === 'dark' ? OSCURO : CLARO;
}

export const RADIO = 12;
export const ESPACIO = 16;
