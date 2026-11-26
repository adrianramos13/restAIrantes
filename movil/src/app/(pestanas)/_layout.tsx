// Barra de secciones fija abajo, copia de la web (componentes/barra.*): Inicio, Comer hoy, Buscar y Perfil (con tu
// foto y el globito rojo de solicitudes de amistad). Sin cabecera arriba, como en Streamlit.
import { Image } from 'expo-image';
import { BottomTabBarProps, Tabs } from 'expo-router/js-tabs';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Icono, NombreIcono } from '@/components/icono';
import { api, Yo } from '@/lib/api';
import { useCarga } from '@/lib/carga';
import { LETRA, useColores } from '@/lib/tema';

const SECCIONES: { nombre: string; texto: string; icono: NombreIcono }[] = [
  { nombre: 'index', texto: 'Inicio', icono: 'inicio' },
  { nombre: 'comer', texto: 'Comer hoy', icono: 'comer' },
  { nombre: 'buscar', texto: 'Buscar', icono: 'buscar' },
  { nombre: 'perfil', texto: 'Perfil', icono: 'persona' },
];

function Barra({ state, navigateToTab }: BottomTabBarProps) {
  const c = useColores();
  const zona = useSafeAreaInsets();
  const yo = useCarga(() => api<Yo>('GET', '/yo'), []).datos;
  const activa = state.routes[state.index]?.name;
  return (
    <View style={[estilos.barra, { backgroundColor: c.fondo, borderTopColor: c.borde, paddingBottom: 4 + zona.bottom }]}>
      {SECCIONES.map((s) => {
        const elegida = s.nombre === activa;
        const color = elegida ? c.primario : c.texto;
        const avisos = s.nombre === 'perfil' ? yo?.solicitudes ?? 0 : 0;
        return (
          <Pressable
            key={s.nombre}
            accessibilityRole="button"
            accessibilityState={{ selected: elegida }}
            accessibilityLabel={avisos ? `Perfil, ${avisos} ${avisos === 1 ? 'solicitud' : 'solicitudes'} de amistad` : s.texto}
            onPress={() => {
              const ruta = state.routes.find((r) => r.name === s.nombre);
              if (ruta) navigateToTab(ruta.key);
            }}
            style={estilos.boton}>
            {s.nombre === 'perfil' ? (
              <View style={[estilos.avatar, { borderColor: elegida ? c.primario : 'transparent' }]}>
                {yo?.foto ? <Image source={yo.foto} style={estilos.foto} contentFit="cover" />
                  : <Icono nombre="persona" tam={24} color={color} />}
              </View>
            ) : <Icono nombre={s.icono} tam={24} color={color} />}
            {avisos > 0 ? (
              <View style={[estilos.aviso, { borderColor: c.fondo }]}>
                <Text style={estilos.textoAviso}>{avisos > 9 ? '9+' : String(avisos)}</Text>
              </View>
            ) : null}
            <Text style={[estilos.texto, { color, fontFamily: elegida ? LETRA.negrita : LETRA.normal }]}>{s.texto}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

export default function Pestanas() {
  return (
    <Tabs tabBar={(props) => <Barra {...props} />} screenOptions={{ headerShown: false }}>
      {SECCIONES.map((s) => <Tabs.Screen key={s.nombre} name={s.nombre} options={{ title: s.texto }} />)}
    </Tabs>
  );
}

const estilos = StyleSheet.create({
  barra: { flexDirection: 'row', justifyContent: 'space-around', paddingTop: 4, paddingHorizontal: 8, borderTopWidth: 1 },
  boton: { flex: 1, maxWidth: 120, minHeight: 56, borderRadius: 12, alignItems: 'center', justifyContent: 'center', gap: 3 },
  texto: { fontSize: 12 },
  avatar: {
    width: 26, height: 26, borderRadius: 13, borderWidth: 2, overflow: 'hidden', alignItems: 'center', justifyContent: 'center',
  },
  foto: { width: '100%', height: '100%' },
  aviso: {
    position: 'absolute', top: 2, left: '50%', marginLeft: 6, minWidth: 18, height: 18, paddingHorizontal: 5,
    borderRadius: 9, backgroundColor: '#DC2626', borderWidth: 2, alignItems: 'center', justifyContent: 'center',
  },
  textoAviso: { color: '#FFFFFF', fontFamily: LETRA.negrita, fontSize: 11, lineHeight: 14 },
});
