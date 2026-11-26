// El tema de la app de Streamlit (.streamlit/config.toml y componentes/*.css): crema + terracota, Inter para el texto
// y Fraunces para los títulos, en claro y oscuro.
import { useColorScheme } from 'react-native';

const CLARO = {
  primario: '#C2410C',
  fondo: '#FBF7F2',          // backgroundColor
  fondo2: '#F3ECE3',         // secondaryBackgroundColor (tarjetas de las listas)
  texto: '#1F1A14',
  textoSuave: 'rgba(31, 26, 20, 0.6)',   // st.caption
  borde: '#E9E1D6',
  enlace: '#9A3412',
  sobrePrimario: '#FFFFFF',
  boton: '#FEFDFB',          // botones secundarios de Streamlit (medido)
  elegido: 'rgba(194, 65, 12, 0.1)',   // opción elegida de st.segmented_control / st.pills
  error: '#B91C1C',
  estrella: '#F5A524',
  verde: '#16A34A',
  avisos: {   // st.info / st.warning / st.error / st.success
    info: { fondo: 'rgba(28, 131, 225, 0.1)', texto: '#0054A3' },
    aviso: { fondo: 'rgba(255, 189, 69, 0.2)', texto: '#926C05' },
    error: { fondo: 'rgba(255, 43, 43, 0.09)', texto: '#7D353B' },
    exito: { fondo: 'rgba(33, 195, 84, 0.1)', texto: '#177233' },
  },
  capa: '#FBF7F2',           // ventanitas flotantes de la ficha
};

const OSCURO: typeof CLARO = {
  primario: '#FB923C',
  fondo: '#16130F',
  fondo2: '#221E19',
  texto: '#F3EDE4',
  textoSuave: 'rgba(243, 237, 228, 0.6)',
  borde: '#3A332B',
  enlace: '#FDBA74',
  sobrePrimario: '#16130F',  // global.css: en oscuro el texto del botón principal va oscuro (8:1)
  boton: '#1E1A15',
  elegido: 'rgba(251, 146, 60, 0.1)',
  error: '#F87171',
  estrella: '#F5A524',
  verde: '#4ADE80',
  avisos: {
    info: { fondo: 'rgba(61, 157, 243, 0.2)', texto: '#C7EBFF' },
    aviso: { fondo: 'rgba(255, 227, 18, 0.2)', texto: '#FFFFC2' },
    error: { fondo: 'rgba(255, 108, 108, 0.2)', texto: '#FFDEDE' },
    exito: { fondo: 'rgba(61, 213, 109, 0.2)', texto: '#DFFDE9' },
  },
  capa: '#16130F',
};

export type Colores = typeof CLARO;

export function useColores(): Colores {
  return useColorScheme() === 'dark' ? OSCURO : CLARO;
}

/** Familias cargadas en app/_layout.tsx (@expo-google-fonts). */
export const LETRA = {
  fina: 'Inter_300Light',
  normal: 'Inter_400Regular',
  media: 'Inter_500Medium',
  semi: 'Inter_600SemiBold',
  negrita: 'Inter_700Bold',
  italica: 'Inter_400Regular_Italic',
  titulo: 'Fraunces_700Bold',
  tituloSemi: 'Fraunces_600SemiBold',
} as const;

export const RADIO = 12;
export const ESPACIO = 15;     // margen de la página a los lados (1 rem)
export const HUECO = 15;       // entre bloques (gap de st.container)
export const TAM_TEXTO = 15;   // baseFontSize
export const TAM_PEQUENO = 13.125;   // etiquetas, botones, st.caption (0,875 rem)
