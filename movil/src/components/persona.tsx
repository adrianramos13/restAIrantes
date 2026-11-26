// Una persona (amigo, solicitud, sugerencia): su foto o su inicial sobre su color, nombre y @alias.
import { Image } from 'expo-image';
import { router } from 'expo-router';
import { ReactNode } from 'react';
import { Pressable, View } from 'react-native';

import { Texto } from '@/components/ui';
import { Persona } from '@/lib/api';
import { RADIO, useColores } from '@/lib/tema';

interface AvatarProps {
  persona: { inicial: string; color: string; foto: string | null };
  tam?: number;
}

export function Avatar({ persona: p, tam = 44 }: AvatarProps) {
  const redondo = { width: tam, height: tam, borderRadius: tam / 2 };
  if (p.foto) return <Image source={p.foto} style={redondo} contentFit="cover" />;
  return (
    <View style={[redondo, { backgroundColor: p.color, alignItems: 'center', justifyContent: 'center' }]}>
      <Texto style={{ color: '#fff', fontWeight: '700', fontSize: tam * 0.42 }}>{p.inicial}</Texto>
    </View>
  );
}

interface FilaProps {
  persona: Persona;
  detalle?: string;
  children?: ReactNode;   // botones debajo
}

/** Al tocarla se abre su perfil (/persona/[alias]). */
export function FilaPersona({ persona: p, detalle, children }: FilaProps) {
  const c = useColores();
  return (
    <View style={{ backgroundColor: c.fondo2, borderColor: c.borde, borderWidth: 1, borderRadius: RADIO, padding: 10, gap: 10 }}>
      <Pressable
        accessibilityRole="button"
        onPress={() => router.push({ pathname: '/persona/[alias]', params: { alias: p.alias } })}
        style={({ pressed }) => ({ flexDirection: 'row', gap: 12, alignItems: 'center', opacity: pressed ? 0.8 : 1 })}>
        <Avatar persona={p} />
        <View style={{ flex: 1 }}>
          <Texto tipo="subtitulo" lineas={1} style={{ fontSize: 16 }}>{p.nombre}</Texto>
          <Texto tipo="suave" lineas={2}>{detalle ? `@${p.alias} · ${detalle}` : `@${p.alias}`}</Texto>
        </View>
      </Pressable>
      {children}
    </View>
  );
}
