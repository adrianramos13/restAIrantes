// Raíz de la app: la sesión decide qué se ve. Sin sesión, solo «Entrar»; con ella, las pestañas y las fichas.
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

  useEffect(() => {
    if (!cargando) SplashScreen.hideAsync();
  }, [cargando]);

  if (cargando) return null;
  return (
    <ThemeProvider
      value={{
        ...base,
        colors: { ...base.colors, primary: c.primario, background: c.fondo, card: c.fondo, text: c.texto, border: c.borde },
      }}>
      <Stack screenOptions={{ headerBackButtonDisplayMode: 'minimal', headerTintColor: c.primario }}>
        <Stack.Protected guard={!!sesion}>
          <Stack.Screen name="(pestanas)" options={{ headerShown: false }} />
          <Stack.Screen name="restaurante/[id]" options={{ title: '', presentation: 'modal' }} />
          <Stack.Screen name="lugar/[id]" options={{ title: '', presentation: 'modal' }} />
          <Stack.Screen name="persona/[alias]" options={{ title: '' }} />
          <Stack.Screen name="amigos" options={{ title: 'Amigos' }} />
          <Stack.Screen name="ajustes" options={{ title: 'Ajustes' }} />
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
