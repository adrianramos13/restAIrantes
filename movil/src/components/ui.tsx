// Las piezas de Streamlit con su tema (.streamlit/config.toml): página, textos (st.markdown, st.subheader,
// st.caption), botones, campos, st.segmented_control, st.pills, st.slider, st.selectbox, st.expander,
// st.container(border=True) y los avisos. Medidas sacadas del estilo calculado de la web a 390 px de ancho.
import { ReactNode, useState } from 'react';
import {
  ActivityIndicator,
  LayoutChangeEvent,
  Modal,
  PanResponder,
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
  ViewStyle,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Icono, NombreIcono } from '@/components/icono';
import { ESPACIO, HUECO, LETRA, RADIO, TAM_PEQUENO, TAM_TEXTO, useColores } from '@/lib/tema';

interface PantallaProps {
  children: ReactNode;
  recargando?: boolean;
  alRecargar?: () => void;
  conCabecera?: boolean;   // dentro de una pantalla con barra de título (no hace falta dejar la zona de la hora)
  fondo?: string;          // otro fondo (la ficha abierta desde la valoración de otro)
  margen?: number;         // a los lados (las ventanas, st.dialog: 22,5)
}

export function Pantalla({ children, recargando = false, alRecargar, conCabecera = false, fondo, margen }: PantallaProps) {
  const c = useColores();
  const zona = useSafeAreaInsets();
  return (
    <ScrollView
      style={{ backgroundColor: fondo ?? c.fondo }}
      contentContainerStyle={[estilos.pantalla, { paddingTop: conCabecera ? ESPACIO : zona.top + ESPACIO },
        margen !== undefined && { paddingHorizontal: margen }]}
      keyboardShouldPersistTaps="handled"
      refreshControl={alRecargar ? <RefreshControl refreshing={recargando} onRefresh={alRecargar} /> : undefined}>
      {children}
    </ScrollView>
  );
}

type TipoTexto = 'titulo' | 'encabezado' | 'subtitulo' | 'normal' | 'negrita' | 'suave' | 'error';

interface TextoProps {
  children: ReactNode;
  tipo?: TipoTexto;
  style?: StyleProp<TextStyle>;
  lineas?: number;
}

export function Texto({ children, tipo = 'normal', style, lineas }: TextoProps) {
  const c = useColores();
  const porTipo: Record<TipoTexto, TextStyle> = {
    titulo: { fontFamily: LETRA.titulo, fontSize: 35.1, lineHeight: 37, color: c.texto },          // h1 de la portada
    // st.header: h2 33,75 px con 15 de aire arriba
    encabezado: { fontFamily: LETRA.tituloSemi, fontSize: 33.75, lineHeight: 40.5, paddingTop: 15, color: c.texto },
    // st.subheader: h3 26,25 px con 11,25 de aire arriba (el de abajo lo pone el hueco entre bloques)
    subtitulo: { fontFamily: LETRA.tituloSemi, fontSize: 26.25, lineHeight: 31.5, letterSpacing: -0.13, paddingTop: 11.25, color: c.texto },
    normal: { fontFamily: LETRA.normal, fontSize: TAM_TEXTO, lineHeight: 24, color: c.texto },
    negrita: { fontFamily: LETRA.semi, fontSize: TAM_TEXTO, lineHeight: 24, color: c.texto },
    suave: { fontFamily: LETRA.normal, fontSize: TAM_PEQUENO, lineHeight: 21, color: c.textoSuave },   // st.caption
    error: { fontFamily: LETRA.normal, fontSize: TAM_TEXTO, lineHeight: 24, color: c.error },
  };
  return (
    <Text style={[porTipo[tipo], style]} numberOfLines={lineas}>
      {children}
    </Text>
  );
}

/** La etiqueta de un widget (13,125 px) con su «?» de ayuda opcional, que despliega el texto al tocarlo. */
export function Etiqueta({ texto, ayuda }: { texto: string; ayuda?: string }) {
  const c = useColores();
  const [verAyuda, setVerAyuda] = useState(false);
  return (
    <View style={{ marginBottom: 3.75 }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
        <Text style={[estilos.etiqueta, { color: c.texto }]}>{texto}</Text>
        {ayuda ? (
          <Pressable accessibilityRole="button" accessibilityLabel={`Ayuda: ${texto}`} hitSlop={10} onPress={() => setVerAyuda(!verAyuda)}>
            <Icono nombre="help_outline" tam={16} color={c.textoSuave} />
          </Pressable>
        ) : null}
      </View>
      {ayuda && verAyuda ? <Texto tipo="suave">{ayuda}</Texto> : null}
    </View>
  );
}

interface BotonProps {
  texto: string;
  alPulsar: () => void;
  tipo?: 'primario' | 'secundario' | 'texto';   // type="primary" | por defecto | type="tertiary"
  icono?: NombreIcono;
  emoji?: string;                 // los botones de los componentes propios (📍 Usar mi ubicación)
  ancho?: 'lleno' | 'contenido';  // width="stretch" | el de por defecto de Streamlit
  grande?: boolean;               // el de «Buscar restaurantes» (global.css: 52 px, 1,05 rem, seminegrita)
  cargando?: boolean;
  desactivado?: boolean;
  style?: StyleProp<ViewStyle>;
  colorTexto?: string;            // p. ej. el verde de «Has ido»
}

export function Boton({
  texto, alPulsar, tipo = 'secundario', icono, emoji, ancho = 'lleno', grande = false, cargando = false,
  desactivado = false, style, colorTexto,
}: BotonProps) {
  const c = useColores();
  const fondo = tipo === 'primario' ? c.primario : tipo === 'secundario' ? c.boton : 'transparent';
  const color = colorTexto ?? (tipo === 'primario' ? c.sobrePrimario : c.texto);
  const letra: TextStyle = grande ? { fontSize: 15.75, lineHeight: 25, fontFamily: LETRA.semi } : {};
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={texto}
      accessibilityState={{ disabled: desactivado || cargando }}
      onPress={alPulsar}
      disabled={desactivado || cargando}
      style={({ pressed }) => [
        estilos.boton,
        tipo === 'texto' && estilos.botonTexto,
        {
          backgroundColor: fondo,
          borderColor: tipo === 'primario' ? c.primario : tipo === 'secundario' ? c.borde : 'transparent',
          opacity: desactivado ? 0.4 : pressed ? 0.8 : 1,
          alignSelf: ancho === 'lleno' ? 'stretch' : 'flex-start',
          minHeight: grande ? 52 : tipo === 'texto' ? 0 : 38,
        },
        style,
      ]}>
      {cargando ? <ActivityIndicator color={color} /> : (
        <>
          {icono ? <Icono nombre={icono} tam={grande ? 16 : 15} color={color} /> : null}
          {emoji ? <Text style={{ fontSize: TAM_PEQUENO }}>{emoji}</Text> : null}
          <Text style={[estilos.textoBoton, { color }, letra]} numberOfLines={1}>{texto}</Text>
        </>
      )}
    </Pressable>
  );
}

interface CampoProps extends TextInputProps {
  etiqueta?: string;
  ayuda?: string;
  icono?: NombreIcono;   // st.text_input(icon=…): el icono a la izquierda, en gris
}

/** st.text_input: etiqueta pequeña y la caja (fondo secundario, borde, 38 px, texto de 13,125 px). */
export function Campo({ etiqueta, ayuda, icono, style, ...resto }: CampoProps) {
  const c = useColores();
  const [enfocado, setEnfocado] = useState(false);
  return (
    <View>
      {etiqueta ? <Etiqueta texto={etiqueta} ayuda={ayuda} /> : null}
      <View style={[estilos.cajaCampo, { backgroundColor: c.fondo2, borderColor: enfocado ? c.primario : c.borde, paddingLeft: icono ? 7.5 : 0 }]}>
        {icono ? <Icono nombre={icono} tam={15} color={c.textoSuave} /> : null}
        <TextInput
          placeholderTextColor={c.textoSuave}
          onFocus={() => setEnfocado(true)}
          onBlur={() => setEnfocado(false)}
          style={[estilos.campo, { color: c.texto }, style]}
          {...resto}
        />
      </View>
    </View>
  );
}

/** st.toggle: interruptor con su texto a la derecha. */
export function Interruptor({ texto, valor, alCambiar }: { texto: string; valor: boolean; alCambiar: (v: boolean) => void }) {
  const c = useColores();
  return (
    <Pressable accessibilityRole="switch" accessibilityState={{ checked: valor }} accessibilityLabel={texto}
      onPress={() => alCambiar(!valor)} style={{ flexDirection: 'row', alignItems: 'center', gap: 7.5 }}>
      <View style={[estilos.pistaInterruptor, { backgroundColor: valor ? c.primario : c.borde }]}>
        <View style={[estilos.bolaInterruptor, { marginLeft: valor ? 14 : 2 }]} />
      </View>
      <Text style={[estilos.textoCampo, { color: c.texto }]}>{texto}</Text>
    </Pressable>
  );
}

interface OpcionesProps<T extends string | number> {
  opciones: readonly T[];
  elegidas: readonly T[];
  alElegir: (opcion: T) => void;
  etiqueta?: (opcion: T) => string;
  titulo?: string;
  estirar?: boolean;   // Segmentado: width="stretch" (por defecto) o lo que ocupe su texto
  compacto?: boolean;  // Segmentado: las opciones caben en una fila (global.css: .st-key-ml_orden)
}

/** st.segmented_control(width="stretch"): opciones pegadas que ocupan todo el ancho. */
export function Segmentado<T extends string | number>({
  opciones, elegidas, alElegir, etiqueta, titulo, estirar = true, compacto = false,
}: OpcionesProps<T>) {
  const c = useColores();
  return (
    <View>
      {titulo ? <Etiqueta texto={titulo} /> : null}
      <View style={{ flexDirection: 'row' }} accessibilityRole="radiogroup">
        {opciones.map((opcion, i) => {
          const elegida = elegidas.includes(opcion);
          const primera = i === 0;
          const ultima = i === opciones.length - 1;
          return (
            <Pressable
              key={String(opcion)}
              accessibilityRole="radio"
              accessibilityState={{ selected: elegida }}
              onPress={() => alElegir(opcion)}
              style={[estilos.segmento, estirar && { flex: 1, minWidth: 0 }, compacto && { paddingHorizontal: 6 }, {
                backgroundColor: elegida ? c.elegido : c.fondo,
                borderColor: elegida ? c.primario : c.borde,
                borderTopLeftRadius: primera ? RADIO : 0, borderBottomLeftRadius: primera ? RADIO : 0,
                borderTopRightRadius: ultima ? RADIO : 0, borderBottomRightRadius: ultima ? RADIO : 0,
                marginLeft: primera ? 0 : -1, zIndex: elegida ? 1 : 0,
              }]}>
              <Text style={[estilos.textoOpcion, compacto && { fontSize: 13 }, { color: elegida ? c.primario : c.texto }]} numberOfLines={1}>
                {etiqueta ? etiqueta(opcion) : String(opcion)}
              </Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

/** st.pills: pastillas sueltas que bajan de línea si no caben. */
export function Chips<T extends string | number>({ opciones, elegidas, alElegir, etiqueta, titulo }: OpcionesProps<T>) {
  const c = useColores();
  return (
    <View>
      {titulo ? <Etiqueta texto={titulo} /> : null}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 7.5 }}>
        {opciones.map((opcion) => {
          const elegida = elegidas.includes(opcion);
          return (
            <Pressable
              key={String(opcion)}
              accessibilityRole="button"
              accessibilityState={{ selected: elegida }}
              onPress={() => alElegir(opcion)}
              style={[estilos.chip, { backgroundColor: elegida ? c.elegido : c.fondo, borderColor: elegida ? c.primario : c.borde }]}>
              <Text style={[estilos.textoOpcion, { color: elegida ? c.primario : c.texto }]}>
                {etiqueta ? etiqueta(opcion) : String(opcion)}
              </Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

interface DeslizadorProps {
  titulo: string;
  min: number;
  max: number;
  paso: number;
  valor: number[];                       // uno (st.slider) o dos (rango)
  alCambiar: (valor: number[]) => void;
  formato: (v: number) => string;
  ayuda?: string;
}

const BOLA = 12;

/** st.slider: barra fina, bolas terracota y el valor encima de cada una. Con dos valores es un rango. */
export function Deslizador({ titulo, min, max, paso, valor, alCambiar, formato, ayuda }: DeslizadorProps) {
  const c = useColores();
  const [ancho, setAncho] = useState(0);
  const util = Math.max(ancho - BOLA, 1);
  const x = (v: number) => ((v - min) / (max - min)) * util;
  const aValor = (px: number) => Math.min(max, Math.max(min, min + Math.round(((px / util) * (max - min)) / paso) * paso));

  function mover(px: number) {
    const v = aValor(px - BOLA / 2);
    if (valor.length === 1) {
      if (v !== valor[0]) alCambiar([v]);
      return;
    }
    // se mueve la bola más cercana sin cruzar la otra
    const cual = Math.abs(v - valor[0]) <= Math.abs(v - valor[1]) ? 0 : 1;
    const nuevo = cual === 0 ? [Math.min(v, valor[1]), valor[1]] : [valor[0], Math.max(v, valor[0])];
    if (nuevo[0] !== valor[0] || nuevo[1] !== valor[1]) alCambiar(nuevo);
  }

  const gesto = PanResponder.create({
    onStartShouldSetPanResponder: () => true,
    onMoveShouldSetPanResponder: () => true,
    onPanResponderTerminationRequest: () => false,
    onPanResponderGrant: (e) => mover(e.nativeEvent.locationX),
    onPanResponderMove: (e) => mover(e.nativeEvent.locationX),
  });
  const desde = valor.length === 1 ? 0 : x(valor[0]);
  const hasta = x(valor[valor.length - 1]);

  return (
    <View>
      <Etiqueta texto={titulo} ayuda={ayuda} />
      <View
        style={{ height: 39 }}
        onLayout={(e: LayoutChangeEvent) => setAncho(e.nativeEvent.layout.width)}
        accessibilityRole="adjustable"
        accessibilityLabel={titulo}
        accessibilityValue={{ text: valor.map(formato).join(' – ') }}
        onAccessibilityAction={(e) => {
          const ultimo = valor[valor.length - 1];
          const otro = e.nativeEvent.actionName === 'increment' ? Math.min(max, ultimo + paso) : Math.max(valor[0], ultimo - paso);
          alCambiar(valor.length === 1 ? [otro] : [valor[0], otro]);
        }}
        accessibilityActions={[{ name: 'increment' }, { name: 'decrement' }]}
        {...gesto.panHandlers}>
        <View pointerEvents="none" style={StyleSheet.absoluteFill}>
          {valor.map((v, i) => {
            // el valor va centrado sobre su bola; cerca de un extremo, pegado a ese borde (como «0 €» en la web)
            const centro = x(v) + BOLA / 2;
            const pegado = centro < 30 ? { left: 0, textAlign: 'left' as const }
              : centro > ancho - 30 ? { right: 0, textAlign: 'right' as const } : { left: centro - 30 };
            return <Text key={i} style={[estilos.valorDeslizador, { color: c.primario }, pegado]}>{formato(v)}</Text>;
          })}
          <View style={[estilos.pista, { backgroundColor: c.fondo2 }]} />
          <View style={[estilos.pista, { backgroundColor: c.primario, left: BOLA / 2 + desde, width: hasta - desde }]} />
          {valor.map((v, i) => (
            <View key={i} style={[estilos.bola, { backgroundColor: c.primario, left: x(v) }]} />
          ))}
        </View>
      </View>
    </View>
  );
}

interface SelectorProps {
  titulo: string;
  opciones: readonly string[];
  valor: string;
  alElegir: (opcion: string) => void;
}

/** st.selectbox: caja con la opción elegida y la flecha; al tocarla, la lista de opciones. */
export function Selector({ titulo, opciones, valor, alElegir }: SelectorProps) {
  const c = useColores();
  const zona = useSafeAreaInsets();
  const [abierto, setAbierto] = useState(false);
  return (
    <View>
      <Etiqueta texto={titulo} />
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`${titulo}: ${valor}`}
        onPress={() => setAbierto(true)}
        style={[estilos.selector, { backgroundColor: c.fondo2, borderColor: c.borde }]}>
        <Text style={[estilos.textoCampo, { color: c.texto, flex: 1 }]} numberOfLines={1}>{valor}</Text>
        <Icono nombre="expand_more" tam={20} color={c.texto} />
      </Pressable>
      <Modal visible={abierto} transparent animationType="fade" onRequestClose={() => setAbierto(false)}>
        <Pressable style={estilos.velo} onPress={() => setAbierto(false)} accessibilityLabel="Cerrar">
          <View style={[estilos.lista, { backgroundColor: c.fondo, borderColor: c.borde, marginTop: zona.top + 60, marginBottom: zona.bottom + 60 }]}>
            <ScrollView>
              {opciones.map((o) => (
                <Pressable
                  key={o}
                  accessibilityRole="button"
                  accessibilityState={{ selected: o === valor }}
                  onPress={() => { alElegir(o); setAbierto(false); }}
                  style={({ pressed }) => [estilos.opcionLista, { backgroundColor: pressed || o === valor ? c.fondo2 : 'transparent' }]}>
                  <Text style={[estilos.textoCampo, { color: c.texto }]}>{o}</Text>
                </Pressable>
              ))}
            </ScrollView>
          </View>
        </Pressable>
      </Modal>
    </View>
  );
}

interface SelectorMultipleProps {
  titulo: string;
  opciones: readonly string[];
  elegidas: readonly string[];
  alCambiar: (elegidas: string[]) => void;
  vacio?: string;   // placeholder: «Cualquiera»
}

/** st.multiselect: las elegidas como etiquetas con ✕ dentro de la caja; al tocarla, la lista para marcar. */
export function SelectorMultiple({ titulo, opciones, elegidas, alCambiar, vacio = 'Elige' }: SelectorMultipleProps) {
  const c = useColores();
  const zona = useSafeAreaInsets();
  const [abierto, setAbierto] = useState(false);
  const cambiar = (o: string) => alCambiar(elegidas.includes(o) ? elegidas.filter((x) => x !== o) : [...elegidas, o]);
  return (
    <View>
      <Etiqueta texto={titulo} />
      <Pressable accessibilityRole="button" accessibilityLabel={`${titulo}: ${elegidas.join(', ') || vacio}`} onPress={() => setAbierto(true)}
        style={[estilos.selector, { backgroundColor: c.fondo2, borderColor: c.borde, paddingVertical: 4 }]}>
        <View style={{ flex: 1, flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
          {elegidas.length ? elegidas.map((o) => (
            <Pressable key={o} accessibilityRole="button" accessibilityLabel={`Quitar ${o}`} onPress={() => cambiar(o)}
              style={[estilos.etiquetaElegida, { backgroundColor: c.primario }]}>
              <Text style={[estilos.textoOpcion, { color: c.sobrePrimario }]}>{`${o}  ✕`}</Text>
            </Pressable>
          )) : <Text style={[estilos.textoCampo, { color: c.textoSuave }]}>{vacio}</Text>}
        </View>
        <Icono nombre="expand_more" tam={20} color={c.texto} />
      </Pressable>
      <Modal visible={abierto} transparent animationType="fade" onRequestClose={() => setAbierto(false)}>
        <Pressable style={estilos.velo} onPress={() => setAbierto(false)} accessibilityLabel="Cerrar">
          <View style={[estilos.lista, { backgroundColor: c.fondo, borderColor: c.borde, marginTop: zona.top + 60, marginBottom: zona.bottom + 60 }]}>
            <ScrollView>
              {opciones.map((o) => {
                const marcada = elegidas.includes(o);
                return (
                  <Pressable key={o} accessibilityRole="checkbox" accessibilityState={{ checked: marcada }} onPress={() => cambiar(o)}
                    style={({ pressed }) => [estilos.opcionLista, { flexDirection: 'row', justifyContent: 'space-between',
                      backgroundColor: pressed || marcada ? c.fondo2 : 'transparent' }]}>
                    <Text style={[estilos.textoCampo, { color: c.texto }]}>{o}</Text>
                    {marcada ? <Icono nombre="check" tam={18} color={c.primario} /> : null}
                  </Pressable>
                );
              })}
            </ScrollView>
          </View>
        </Pressable>
      </Modal>
    </View>
  );
}

/** st.expander: recuadro con «› Título» que se despliega. */
export function Desplegable({ titulo, children, abierto: inicial = false, icono }: {
  titulo: string; children: ReactNode; abierto?: boolean; icono?: NombreIcono;   // con icono, va en lugar de la flecha
}) {
  const c = useColores();
  const [abierto, setAbierto] = useState(inicial);
  return (
    <View style={[estilos.desplegable, { borderColor: c.borde }]}>
      <Pressable accessibilityRole="button" accessibilityState={{ expanded: abierto }} onPress={() => setAbierto(!abierto)}
        style={estilos.cabeceraDesplegable}>
        <Icono nombre={icono ?? (abierto ? 'keyboard_arrow_down' : 'keyboard_arrow_right')} tam={icono ? 15 : 18} color={c.texto} />
        <Text style={[estilos.textoCampo, { color: c.texto }]}>{titulo}</Text>
      </Pressable>
      {abierto ? <View style={estilos.cuerpoDesplegable}>{children}</View> : null}
    </View>
  );
}

/** El título de una ventana (st.dialog): Inter seminegrita de 22,5 px y la ✕ a la derecha. `extra`: otro botón
 * junto a la ✕ (p. ej. compartir). */
export function TituloVentana({ titulo, alCerrar, extra }: { titulo: string; alCerrar: () => void; extra?: ReactNode }) {
  const c = useColores();
  return (
    <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 12, marginBottom: -3.75 }}>
      <Text accessibilityRole="header" style={{ flex: 1, fontFamily: LETRA.semi, fontSize: 22.5, lineHeight: 33.75, color: c.texto }}>
        {titulo}
      </Text>
      {extra}
      <Pressable accessibilityRole="button" accessibilityLabel="Cerrar" hitSlop={12} onPress={alCerrar} style={{ paddingTop: 8 }}>
        <Icono nombre="close" tam={18} color={c.texto} />
      </Pressable>
    </View>
  );
}

/** Las ventanitas flotantes de la ficha (global.css: .st-key-capa_eatlist/visita/resenas): centradas, de hasta
 * 420 px, con el resto oscurecido; arriba «#### Título» y la ✕. */
export function Capa({ visible, titulo, alCerrar, children }: {
  visible: boolean; titulo: string; alCerrar: () => void; children: ReactNode;
}) {
  const c = useColores();
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={alCerrar}>
      <View style={estilos.veloCapa}>
        <View style={[estilos.capa, { backgroundColor: c.fondo, borderColor: c.texto === '#1F1A14' ? 'rgba(0,0,0,0.08)' : 'rgba(255,255,255,0.12)' }]}>
          <ScrollView contentContainerStyle={{ gap: HUECO, paddingTop: 8, paddingBottom: 20, paddingHorizontal: 20 }}
            keyboardShouldPersistTaps="handled">
            <View style={{ flexDirection: 'row', alignItems: 'center' }}>
              <Text style={[estilos.tituloCapa, { color: c.texto }]}>{titulo}</Text>
              <Pressable accessibilityRole="button" accessibilityLabel="Cerrar" hitSlop={10} onPress={alCerrar}>
                <Icono nombre="close" tam={20} color={c.texto} />
              </Pressable>
            </View>
            {children}
          </ScrollView>
        </View>
      </View>
    </Modal>
  );
}

/** st.toast: un aviso abajo que se va solo a los 4 s. */
export function useAvisoBreve(): [ReactNode, (texto: string) => void] {
  const c = useColores();
  const [texto, setTexto] = useState<string | null>(null);
  const avisar = (t: string) => {
    setTexto(t);
    setTimeout(() => setTexto((actual) => (actual === t ? null : actual)), 4000);
  };
  const vista = texto ? (
    <View pointerEvents="none" style={[estilos.aviso, { backgroundColor: c.fondo, borderColor: c.borde }]}
      accessibilityLiveRegion="polite">
      <Icono nombre="check_circle" tam={18} color={c.texto} />
      <Text style={[estilos.textoCampo, { color: c.texto, flex: 1 }]}>{texto}</Text>
    </View>
  ) : null;
  return [vista, avisar];
}

export function Seccion({ titulo, children }: { titulo?: string; children: ReactNode }) {
  return (
    <View style={{ gap: HUECO }}>
      {titulo ? <Texto tipo="subtitulo">{titulo}</Texto> : null}
      {children}
    </View>
  );
}

export function Cargando() {
  const c = useColores();
  return <ActivityIndicator style={{ marginVertical: 24 }} color={c.primario} />;
}

/** st.container(border=True) */
export function Caja({ children, style }: { children: ReactNode; style?: StyleProp<ViewStyle> }) {
  const c = useColores();
  return <View style={[estilos.caja, { borderColor: c.borde }, style]}>{children}</View>;
}

/** st.info / st.warning / st.error / st.success */
export function Info({ children, tipo = 'info' }: { children: ReactNode; tipo?: 'info' | 'aviso' | 'error' | 'exito' }) {
  const c = useColores();
  const color = c.avisos[tipo];
  return (
    <View style={[estilos.info, { backgroundColor: color.fondo }]}>
      <Text style={{ fontFamily: LETRA.normal, fontSize: TAM_TEXTO, lineHeight: 24, color: color.texto }}>{children}</Text>
    </View>
  );
}

const estilos = StyleSheet.create({
  pantalla: { paddingHorizontal: ESPACIO, gap: HUECO, paddingBottom: 32 },
  boton: {
    borderRadius: RADIO, borderWidth: 1, paddingVertical: 3.75, paddingHorizontal: 11.25,
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 7.5,
  },
  botonTexto: { paddingHorizontal: 0, paddingVertical: 0 },
  textoBoton: { fontFamily: LETRA.normal, fontSize: TAM_PEQUENO, lineHeight: 21, flexShrink: 1 },
  etiqueta: { fontFamily: LETRA.normal, fontSize: TAM_PEQUENO, lineHeight: 21 },
  cajaCampo: { minHeight: 38, borderRadius: RADIO, borderWidth: 1, flexDirection: 'row', alignItems: 'center' },
  campo: {
    flex: 1, alignSelf: 'stretch', paddingLeft: 11.25, paddingRight: 7.5, paddingVertical: 7.5, fontSize: TAM_PEQUENO,
    fontFamily: LETRA.normal,
  },
  pistaInterruptor: { width: 32, height: 20, borderRadius: 10, justifyContent: 'center' },
  bolaInterruptor: { width: 16, height: 16, borderRadius: 8, backgroundColor: '#FFFFFF' },
  textoCampo: { fontFamily: LETRA.normal, fontSize: TAM_TEXTO, lineHeight: 24 },
  segmento: {
    minHeight: 30, borderWidth: 1, paddingVertical: 3.75, paddingHorizontal: 15, alignItems: 'center',
    justifyContent: 'center',
  },
  chip: { minHeight: 30, borderRadius: RADIO, borderWidth: 1, paddingVertical: 3.75, paddingHorizontal: 15, justifyContent: 'center' },
  textoOpcion: { fontFamily: LETRA.normal, fontSize: TAM_PEQUENO, lineHeight: 21 },
  valorDeslizador: { position: 'absolute', top: -8.75, width: 60, textAlign: 'center', fontFamily: LETRA.normal, fontSize: TAM_PEQUENO, lineHeight: 21 },
  pista: { position: 'absolute', top: 15, left: BOLA / 2, right: BOLA / 2, height: 4, borderRadius: 2 },
  bola: { position: 'absolute', top: 11, width: BOLA, height: BOLA, borderRadius: BOLA / 2 },
  selector: {
    minHeight: 38, borderRadius: RADIO, borderWidth: 1, paddingLeft: 11.25, paddingRight: 8, flexDirection: 'row',
    alignItems: 'center',
  },
  velo: { flex: 1, backgroundColor: 'rgba(0, 0, 0, 0.3)', paddingHorizontal: ESPACIO },
  lista: { borderRadius: RADIO, borderWidth: 1, overflow: 'hidden', maxHeight: 420 },
  opcionLista: { paddingHorizontal: 11.25, paddingVertical: 9 },
  etiquetaElegida: { borderRadius: 8, paddingHorizontal: 8, paddingVertical: 1 },
  desplegable: { borderWidth: 1, borderRadius: RADIO },
  cabeceraDesplegable: { minHeight: 36, flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 11.25, paddingVertical: 3.75 },
  cuerpoDesplegable: { paddingHorizontal: 15, paddingBottom: 15, paddingTop: 4, gap: HUECO },
  caja: { borderRadius: RADIO, borderWidth: 1, padding: 14, gap: HUECO },
  veloCapa: { flex: 1, backgroundColor: 'rgba(0, 0, 0, 0.45)', alignItems: 'center', justifyContent: 'center' },
  capa: {
    width: '92%', maxWidth: 420, maxHeight: '85%', borderRadius: 16, borderWidth: 1, overflow: 'hidden',
    shadowColor: '#000', shadowOpacity: 0.3, shadowRadius: 16, shadowOffset: { width: 0, height: 12 }, elevation: 12,
  },
  tituloCapa: { flex: 1, fontFamily: LETRA.tituloSemi, fontSize: 19.5, lineHeight: 26, paddingVertical: 8 },
  aviso: {
    position: 'absolute', left: 15, right: 15, bottom: 24, flexDirection: 'row', alignItems: 'center', gap: 10,
    paddingHorizontal: 16, paddingVertical: 12, borderRadius: RADIO, borderWidth: 1,
    shadowColor: '#000', shadowOpacity: 0.15, shadowRadius: 8, shadowOffset: { width: 0, height: 4 }, elevation: 6,
  },
  info: { borderRadius: RADIO, paddingHorizontal: 16, paddingVertical: 14 },
});
