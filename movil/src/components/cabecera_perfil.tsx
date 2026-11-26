// La cabecera del Perfil (app.cabecera_perfil), estilo Instagram: tu foto (abre tus ajustes), nombre, @usuario y
// tres cifras: Idos y En tu lista abren esa lista en una ventana; Amigos, su listado. También encima de tus amigos.
import { Image } from 'expo-image';
import { router } from 'expo-router';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { Icono } from '@/components/icono';
import { Yo } from '@/lib/api';
import { LETRA, useColores } from '@/lib/tema';

export interface TusDatos {
  idos: number;
  en_lista: number;
  amigos: number;
  tarjetas: { icono: string; valor: string; texto: string }[];
}

/** componentes/avatar_perfil.* en modo «ajustes»: 76 px y el engranaje terracota abajo a la derecha. */
function AvatarAjustes({ yo }: { yo: Yo }) {
  const c = useColores();
  return (
    <Pressable accessibilityRole="button" accessibilityLabel="Tus ajustes" onPress={() => router.push('/ajustes')}>
      <View style={[estilos.circulo, { backgroundColor: c.primario }]}>
        <Text style={estilos.inicial}>{(yo.nombre.trim()[0] ?? '?').toUpperCase()}</Text>
        {yo.foto ? <Image source={yo.foto} style={StyleSheet.absoluteFill} contentFit="cover" /> : null}
      </View>
      <View style={[estilos.engranaje, { backgroundColor: c.primario, borderColor: c.fondo }]}>
        <Icono nombre="ajustes" tam={16} color={c.fondo} />
      </View>
    </Pressable>
  );
}

/** Los contadores de la cabecera: la cifra grande arriba y la palabra debajo (global.css: st-key-contador_). */
function Contador({ cifra, texto, alPulsar, ayuda }: { cifra: number; texto: string; alPulsar: () => void; ayuda: string }) {
  const c = useColores();
  return (
    <Pressable accessibilityRole="button" accessibilityLabel={`${cifra} ${texto}. ${ayuda}`} onPress={alPulsar}
      style={({ pressed }) => ({ alignItems: 'center', opacity: pressed ? 0.6 : 1 })}>
      <Text style={{ fontFamily: LETRA.negrita, fontSize: 19.5, lineHeight: 23.4, color: c.texto }}>{cifra}</Text>
      <Text style={{ fontFamily: LETRA.normal, fontSize: 13, lineHeight: 16.9, color: c.texto }}>{texto}</Text>
    </Pressable>
  );
}

export function Cabecera({ yo, datos }: { yo: Yo; datos: TusDatos | null }) {
  const c = useColores();
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 15 }}>
      <AvatarAjustes yo={yo} />
      <View style={{ flex: 1 }}>
        <Text style={{ fontFamily: LETRA.titulo, fontSize: 20.25, lineHeight: 24.3, color: c.texto }}>{yo.nombre}</Text>
        {yo.alias ? (
          <Text style={{ fontFamily: LETRA.normal, fontSize: 14.25, lineHeight: 18.5, opacity: 0.7, color: c.texto }}>{`@${yo.alias}`}</Text>
        ) : null}
        <View style={{ flexDirection: 'row', gap: 30, marginTop: 6 }}>
          <Contador cifra={datos?.idos ?? 0} texto="Idos" ayuda="Ver a cuáles has ido"
            alPulsar={() => router.push({ pathname: '/lista', params: { cual: 'idos' } })} />
          <Contador cifra={datos?.en_lista ?? yo.lista.total} texto="En tu lista" ayuda="Ver tu lista"
            alPulsar={() => router.push({ pathname: '/lista', params: { cual: 'tu_lista' } })} />
          <Contador cifra={datos?.amigos ?? 0} texto="Amigos" ayuda="Ver tus amigos" alPulsar={() => router.push('/amigos')} />
        </View>
      </View>
    </View>
  );
}

const estilos = StyleSheet.create({
  circulo: { width: 76, height: 76, borderRadius: 38, overflow: 'hidden', alignItems: 'center', justifyContent: 'center' },
  inicial: { fontFamily: LETRA.negrita, fontSize: 32, color: '#FFFFFF' },
  engranaje: {
    position: 'absolute', right: -2, bottom: -2, width: 28, height: 28, borderRadius: 14, borderWidth: 3,
    alignItems: 'center', justifyContent: 'center',
  },
});
