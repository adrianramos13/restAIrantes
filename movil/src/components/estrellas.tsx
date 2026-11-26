// Nota en medias estrellas (0,5 a 5), como en la app de Streamlit: tocar una estrella la llena entera;
// tocarla otra vez la deja a media (estrella hueca).
import { Pressable, Text, View } from 'react-native';

import { useColores } from '@/lib/tema';

interface Props {
  valor: number | null;
  alCambiar: (valor: number) => void;
}

export function Estrellas({ valor, alCambiar }: Props) {
  const c = useColores();
  return (
    <View style={{ flexDirection: 'row', gap: 6, alignItems: 'center' }}>
      {[1, 2, 3, 4, 5].map((n) => {
        const llena = valor !== null && valor >= n;
        const media = valor !== null && valor === n - 0.5;
        return (
          <Pressable
            key={n}
            accessibilityRole="button"
            accessibilityLabel={`${n} estrellas`}
            hitSlop={6}
            onPress={() => alCambiar(valor === n ? n - 0.5 : n)}>
            <Text style={{ fontSize: 32, color: llena || media ? c.primario : c.borde }}>{media ? '☆' : '★'}</Text>
          </Pressable>
        );
      })}
      <Text style={{ color: c.textoSuave, marginLeft: 4 }}>
        {valor === null ? 'Sin nota' : String(valor).replace('.', ',')}
      </Text>
    </View>
  );
}
