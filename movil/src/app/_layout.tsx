// Raíz de la app: la sesión decide qué se ve. Sin sesión, solo «Entrar»; con ella, las pestañas y las fichas.
import { Fraunces_600SemiBold, Fraunces_700Bold } from '@expo-google-fonts/fraunces';
import {
  Inter_300Light, Inter_400Regular, Inter_400Regular_Italic, Inter_500Medium, Inter_600SemiBold, Inter_700Bold, useFonts,
} from '@expo-google-fonts/inter';
import { DarkTheme, DefaultTheme, Stack, ThemeProvider } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { useEffect } from 'react';
import { useColorScheme } from 'react-native';

import { ProveedorSesion, useSesion } from '@/lib/sesion';
import { useColores } from '@/lib/tema';

SplashScreen.preventAutoHideAsync();

function Navegacion() {
  const { sesion, cargando } = useSesion();
  const c = useColores();
  const oscuro = useColorScheme() === 'dark';
  const base = oscuro ? DarkTheme : DefaultTheme;
  const [letras, errorLetras] = useFonts({   // las de Streamlit (config.toml: Inter y Fraunces)
    Inter_300Light, Inter_400Regular, Inter_400Regular_Italic, Inter_500Medium, Inter_600SemiBold, Inter_700Bold,
    Fraunces_600SemiBold, Fraunces_700Bold,
  });
  const listo = !cargando && (letras || !!errorLetras);   // sin red para las letras: sigue con las del sistema

  useEffect(() => {
    if (listo) SplashScreen.hideAsync();
  }, [listo]);

  if (!listo) return null;
  return (
    <ThemeProvider
      value={{
        ...base,
        colors: { ...base.colors, primary: c.primario, background: c.fondo, card: c.fondo, text: c.texto, border: c.borde },
      }}>
      <Stack screenOptions={{ headerBackButtonDisplayMode: 'minimal', headerTintColor: c.primario,
        headerTitleStyle: { fontFamily: 'Fraunces_600SemiBold', color: c.texto } }}>
        <Stack.Protected guard={!!sesion}>
          <Stack.Screen name="(pestanas)" options={{ headerShown: false }} />
          <Stack.Screen name="restaurante/[id]" options={{ title: '', presentation: 'modal' }} />
          <Stack.Screen name="lugar/[id]" options={{ title: '', presentation: 'modal' }} />
          <Stack.Screen name="lista" options={{ title: '', presentation: 'modal' }} />
          <Stack.Screen name="persona/[alias]" options={{ title: '' }} />
          <Stack.Screen name="amigos" options={{ title: 'Amigos' }} />
          <Stack.Screen name="ajustes" options={{ title: '', presentation: 'modal' }} />
          <Stack.Screen name="notificaciones" options={{ title: 'Notificaciones', presentation: 'modal' }} />
          <Stack.Screen name="match" options={{ title: 'Food match' }} />
        </Stack.Protected>
        <Stack.Protected guard={!sesion}>
          <Stack.Screen name="entrar" options={{ headerShown: false }} />
        </Stack.Protected>
      </Stack>
    </ThemeProvider>
  );
}

export default function Raiz() {
  return (
    <ProveedorSesion>
      <Navegacion />
    </ProveedorSesion>
  );
}
