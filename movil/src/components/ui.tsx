// Piezas de interfaz con el tema de la app: pantalla, textos, botones, campos y chips.
import { ReactNode } from 'react';
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleProp,
  StyleSheet,
  Text,
  TextInput,
  TextInputProps,
  TextStyle,
  View,
} from 'react-native';

import { ESPACIO, RADIO, useColores } from '@/lib/tema';

interface PantallaProps {
  children: ReactNode;
  recargando?: boolean;
  alRecargar?: () => void;
}

export function Pantalla({ children, recargando = false, alRecargar }: PantallaProps) {
  const c = useColores();
  return (
    <ScrollView
      style={{ backgroundColor: c.fondo }}
      contentContainerStyle={estilos.pantalla}
      contentInsetAdjustmentBehavior="automatic"
      keyboardShouldPersistTaps="handled"
      refreshControl={alRecargar ? <RefreshControl refreshing={recargando} onRefresh={alRecargar} /> : undefined}>
      {children}
    </ScrollView>
  );
}

interface TextoProps {
  children: ReactNode;
  tipo?: 'titulo' | 'subtitulo' | 'normal' | 'suave' | 'error';
  style?: StyleProp<TextStyle>;
  lineas?: number;
}

export function Texto({ children, tipo = 'normal', style, lineas }: TextoProps) {
  const c = useColores();
  const porTipo: Record<NonNullable<TextoProps['tipo']>, TextStyle> = {
    titulo: { fontSize: 28, fontWeight: '700', color: c.texto },
    subtitulo: { fontSize: 19, fontWeight: '600', color: c.texto },
    normal: { fontSize: 15, color: c.texto },
    suave: { fontSize: 13, color: c.textoSuave },
    error: { fontSize: 14, color: c.error },
  };
  return (
    <Text style={[porTipo[tipo], style]} numberOfLines={lineas}>
      {children}
    </Text>
  );
}

interface BotonProps {
  texto: string;
  alPulsar: () => void;
  tipo?: 'primario' | 'secundario' | 'texto';
  cargando?: boolean;
  desactivado?: boolean;
}

export function Boton({ texto, alPulsar, tipo = 'primario', cargando = false, desactivado = false }: BotonProps) {
  const c = useColores();
  const fondo = tipo === 'primario' ? c.primario : tipo === 'secundario' ? c.fondo2 : 'transparent';
  const color = tipo === 'primario' ? c.sobrePrimario : tipo === 'secundario' ? c.texto : c.enlace;
  return (
    <Pressable
      accessibilityRole="button"
      onPress={alPulsar}
      disabled={desactivado || cargando}
      style={({ pressed }) => [
        estilos.boton,
        { backgroundColor: fondo, opacity: desactivado ? 0.5 : pressed ? 0.8 : 1 },
        tipo === 'secundario' && { borderWidth: 1, borderColor: c.borde },
      ]}>
      {cargando ? <ActivityIndicator color={color} /> : <Text style={[estilos.textoBoton, { color }]}>{texto}</Text>}
    </Pressable>
  );
}

export function Campo(props: TextInputProps & { etiqueta?: string }) {
  const c = useColores();
  const { etiqueta, style, ...resto } = props;
  return (
    <View style={{ gap: 6 }}>
      {etiqueta ? <Texto tipo="suave">{etiqueta}</Texto> : null}
      <TextInput
        placeholderTextColor={c.textoSuave}
        style={[estilos.campo, { color: c.texto, backgroundColor: c.fondo2, borderColor: c.borde }, style]}
        {...resto}
      />
    </View>
  );
}

interface ChipsProps<T extends string | number> {
  opciones: readonly T[];
  elegidas: readonly T[];
  alElegir: (opcion: T) => void;
  etiqueta?: (opcion: T) => string;
}

/** Fila de opciones que se puede deslizar: una elegida (como un selector) o varias. */
export function Chips<T extends string | number>({ opciones, elegidas, alElegir, etiqueta }: ChipsProps<T>) {
  const c = useColores();
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
      {opciones.map((opcion) => {
        const elegida = elegidas.includes(opcion);
        return (
          <Pressable
            key={String(opcion)}
            accessibilityRole="button"
            accessibilityState={{ selected: elegida }}
            onPress={() => alElegir(opcion)}
            style={[
              estilos.chip,
              { backgroundColor: elegida ? c.primario : c.fondo2, borderColor: elegida ? c.primario : c.borde },
            ]}>
            <Text style={{ color: elegida ? c.sobrePrimario : c.texto, fontWeight: '500' }}>
              {etiqueta ? etiqueta(opcion) : String(opcion)}
            </Text>
          </Pressable>
        );
      })}
    </ScrollView>
  );
}

export function Seccion({ titulo, children }: { titulo?: string; children: ReactNode }) {
  return (
    <View style={{ gap: 10 }}>
      {titulo ? <Texto tipo="subtitulo">{titulo}</Texto> : null}
      {children}
    </View>
  );
}

export function Cargando() {
  const c = useColores();
  return <ActivityIndicator style={{ marginVertical: 24 }} color={c.primario} />;
}

export function Caja({ children }: { children: ReactNode }) {
  const c = useColores();
  return <View style={[estilos.caja, { backgroundColor: c.fondo2, borderColor: c.borde }]}>{children}</View>;
}

const estilos = StyleSheet.create({
  pantalla: { padding: ESPACIO, gap: 20, paddingBottom: 48 },
  boton: { borderRadius: RADIO, paddingVertical: 13, paddingHorizontal: 16, alignItems: 'center' },
  textoBoton: { fontSize: 16, fontWeight: '600' },
  campo: { borderRadius: RADIO, borderWidth: 1, paddingHorizontal: 14, paddingVertical: 12, fontSize: 16 },
  chip: { borderRadius: 999, borderWidth: 1, paddingHorizontal: 14, paddingVertical: 8 },
  caja: { borderRadius: RADIO, borderWidth: 1, padding: ESPACIO, gap: 8 },
});
