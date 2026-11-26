// En la web no hay react-native-maps: un recuadro en su lugar (solo para probar la app en el PC).
import { ReactNode } from 'react';
import { Text, View, ViewProps } from 'react-native';

export default function MapView({ style }: ViewProps & { children?: ReactNode }) {
  return (
    <View style={[{ alignItems: 'center', justifyContent: 'center', backgroundColor: '#E5E0D8' }, style]}>
      <Text>Mapa</Text>
    </View>
  );
}

export const Marker = (_: { children?: ReactNode }) => null;
export const Callout = (_: { children?: ReactNode }) => null;
