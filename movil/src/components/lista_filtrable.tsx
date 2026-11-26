// app.lista_filtrable: buscar por nombre, «Filtros» (cocina, presupuesto, nota, plato, ocultar cerrados, añadidos
// entre dos fechas), el orden, «X de Y restaurantes», las tarjetas de 20 en 20 y «Ver más (N restantes)».
// `de`: tu lista o los restaurantes a los que has ido (las ventanas «En tu lista» / «Idos» del Perfil).
import DateTimePicker, { DateTimePickerAndroid } from '@react-native-community/datetimepicker';
import { useState } from 'react';
import { Platform, Pressable, Text, View } from 'react-native';

import { Icono } from '@/components/icono';
import { ListaTarjetas, TarjetaRestaurante } from '@/components/tarjeta';
import {
  Boton, Campo, Deslizador, Desplegable, Etiqueta, Info, Interruptor, Segmentado, SelectorMultiple, Texto,
} from '@/components/ui';
import { api, Tarjeta } from '@/lib/api';
import { useCarga } from '@/lib/carga';
import { LETRA, RADIO, TAM_TEXTO, useColores } from '@/lib/tema';

type Orden = 'nota' | 'resenas' | 'nombre' | 'recientes';
const POR_PAGINA = 20;

interface Respuesta {
  restaurantes: Tarjeta[];
  total: number;
  cocinas: string[];
}

const dosCifras = (n: number) => String(n).padStart(2, '0');
const fechaCorta = (d: Date) => `${dosCifras(d.getDate())}/${dosCifras(d.getMonth() + 1)}/${d.getFullYear()}`;
const isoDia = (d: Date) => `${d.getFullYear()}-${dosCifras(d.getMonth() + 1)}-${dosCifras(d.getDate())}`;

/** st.date_input con un rango: «DD/MM/YYYY – DD/MM/YYYY». Se elige el «desde» y luego el «hasta». */
function RangoFechas({ titulo, rango, alCambiar, min, max }: {
  titulo: string; rango: Date[]; alCambiar: (r: Date[]) => void; min: Date; max: Date;
}) {
  const c = useColores();
  const [eligiendo, setEligiendo] = useState<number | null>(null);   // iOS: 0 = desde, 1 = hasta
  const texto = rango.length ? rango.map(fechaCorta).join(' – ') : 'DD/MM/YYYY – DD/MM/YYYY';

  function elegir(paso: number) {
    if (Platform.OS === 'android') {
      DateTimePickerAndroid.open({
        value: rango[paso] ?? rango[0] ?? max, mode: 'date', minimumDate: paso ? rango[0] : min, maximumDate: max,
        onChange: (e, d) => {
          if (e.type !== 'set' || !d) return;
          alCambiar(paso ? [rango[0], d] : [d]);
          if (!paso) elegir(1);
        },
      });
    } else {
      setEligiendo(paso);
    }
  }

  return (
    <View>
      <Etiqueta texto={titulo} />
      <View style={{ flexDirection: 'row', alignItems: 'center', minHeight: 38, borderRadius: RADIO, borderWidth: 1,
        borderColor: c.borde, backgroundColor: c.fondo2, paddingHorizontal: 11.25 }}>
        <Pressable accessibilityRole="button" accessibilityLabel={`${titulo}: ${texto}`} style={{ flex: 1, paddingVertical: 7 }}
          onPress={() => elegir(0)} disabled={Platform.OS === 'web'}>
          <Text style={{ fontFamily: LETRA.normal, fontSize: TAM_TEXTO, color: rango.length ? c.texto : c.textoSuave }}>{texto}</Text>
        </Pressable>
        {rango.length ? (
          <Pressable accessibilityRole="button" accessibilityLabel="Quitar las fechas" hitSlop={8} onPress={() => alCambiar([])}>
            <Icono nombre="close" tam={18} color={c.texto} />
          </Pressable>
        ) : null}
      </View>
      {eligiendo !== null && Platform.OS === 'ios' ? (
        <View>
          <Texto tipo="suave">{eligiendo ? 'Hasta:' : 'Desde:'}</Texto>
          <DateTimePicker value={rango[eligiendo] ?? rango[0] ?? max} mode="date" display="inline" locale="es-ES"
            minimumDate={eligiendo ? rango[0] : min} maximumDate={max} accentColor={c.primario}
            onChange={(_, d) => {
              if (!d) return;
              if (eligiendo === 0) {
                alCambiar([d]);
                setEligiendo(1);
              } else {
                alCambiar([rango[0], d]);
                setEligiendo(null);
              }
            }} />
        </View>
      ) : null}
    </View>
  );
}

export function ListaFiltrable({ de = 'lista' }: { de?: 'lista' | 'idos' }) {
  const [texto, setTexto] = useState('');
  const [cocinas, setCocinas] = useState<string[]>([]);
  const [presupuesto, setPresupuesto] = useState<number[]>([0, 100]);
  const [notaMin, setNotaMin] = useState(0);
  const [platoEscrito, setPlatoEscrito] = useState('');
  const [plato, setPlato] = useState('');
  const [ocultarCerrados, setOcultarCerrados] = useState(false);
  const [rango, setRango] = useState<Date[]>([]);
  const [orden, setOrden] = useState<Orden>('nota');
  const [mostrados, setMostrados] = useState(POR_PAGINA);
  const [hoy] = useState(() => Date.now());

  const parametros = {
    de, texto: texto.trim(), cocina: cocinas, presupuesto_min: presupuesto[0], presupuesto_max: presupuesto[1],
    nota_min: notaMin || undefined, plato: plato.trim(), ocultar_cerrados: ocultarCerrados || undefined, orden,
    desde: rango[0] ? isoDia(rango[0]) : undefined, hasta: rango[1] ? isoDia(rango[1]) : undefined,
  };
  const clave = JSON.stringify(parametros);
  const [claveMostrados, setClaveMostrados] = useState(clave);
  if (clave !== claveMostrados) {   // otros filtros: se vuelve a empezar por los 20 primeros
    setClaveMostrados(clave);
    setMostrados(POR_PAGINA);
  }
  const lista = useCarga(() => api<Respuesta>('GET', '/lista', undefined, parametros), [clave]);
  // todas (sin filtros) para saber si hay fechas de «añadido» y entre cuáles
  const todas = useCarga(() => api<Respuesta>('GET', '/lista', undefined, { de }), [de]);
  const fechas = (todas.datos?.restaurantes ?? []).map((t) => t.anadido_en).filter((f): f is string => !!f).map((f) => new Date(f));
  const conFechas = fechas.length > 0;
  const sinTope = 100;

  const activos = [cocinas.length > 0, notaMin > 0, !!plato.trim(), ocultarCerrados, rango.length > 0,
    presupuesto[0] !== 0 || presupuesto[1] !== sinTope].filter(Boolean).length;
  const ordenes: Orden[] = conFechas ? ['nota', 'resenas', 'nombre', 'recientes'] : ['nota', 'resenas', 'nombre'];
  // con cuatro opciones, nombres cortos para que quepan en una fila (global.css: .st-key-ml_orden)
  const nombres: Record<Orden, string> = conFechas
    ? { nota: 'Nota', resenas: 'Reseñas', nombre: 'Nombre', recientes: 'Recientes' }
    : { nota: 'Mejor nota', resenas: 'Más reseñas', nombre: 'Nombre', recientes: 'Recientes' };

  const r = lista.datos;
  const top = r?.restaurantes.slice(0, mostrados) ?? [];
  return (
    <>
      <Campo icono="search" placeholder="Buscar por nombre" value={texto} onChangeText={setTexto} autoCorrect={false}
        accessibilityLabel="Buscar por nombre" />
      <Desplegable titulo={activos ? `Filtros (${activos})` : 'Filtros'} icono="tune">
        <SelectorMultiple titulo="Cocina" opciones={r?.cocinas ?? todas.datos?.cocinas ?? []} elegidas={cocinas} vacio="Cualquiera"
          alCambiar={setCocinas} />
        <Deslizador titulo="Presupuesto por persona" min={0} max={sinTope} paso={5} valor={presupuesto} alCambiar={setPresupuesto}
          formato={(v) => `${v} €`} />
        <Deslizador titulo="Nota mínima en Google" min={0} max={5} paso={0.5} valor={[notaMin]} alCambiar={(v) => setNotaMin(v[0])}
          formato={(v) => `${v.toFixed(1)} ⭐`} />
        <Campo etiqueta="Plato que destaquen" placeholder="Ej. croquetas" value={platoEscrito} onChangeText={setPlatoEscrito}
          onSubmitEditing={() => setPlato(platoEscrito)} onBlur={() => setPlato(platoEscrito)} returnKeyType="search" />
        <Interruptor texto="Ocultar los cerrados" valor={ocultarCerrados} alCambiar={setOcultarCerrados} />
        {conFechas ? (
          <RangoFechas titulo="Añadidos a tu lista entre" rango={rango} alCambiar={setRango}
            min={new Date(Math.min(...fechas.map(Number)))} max={new Date(Math.max(hoy, ...fechas.map(Number)))} />
        ) : null}
      </Desplegable>
      <Segmentado opciones={ordenes} elegidas={[orden]} alElegir={setOrden} etiqueta={(o) => nombres[o]} compacto />
      {lista.error ? <Info tipo="error">{lista.error}</Info> : null}
      {r ? <Texto tipo="suave">{`${r.restaurantes.length} de ${r.total} restaurantes`}</Texto> : null}
      {r && !r.restaurantes.length ? <Info>Ninguno cumple esos filtros.</Info> : null}
      {top.length ? (
        <ListaTarjetas>
          {top.map((t, i) => (
            <TarjetaRestaurante key={t.id} tarjeta={t} n={i + 1} plato={plato.trim()}
              cuando={t.anadido_en ? `añadido el ${fechaCorta(new Date(t.anadido_en))}` : undefined} />
          ))}
        </ListaTarjetas>
      ) : null}
      {r && r.restaurantes.length > top.length ? (
        <Boton texto={`Ver más (${r.restaurantes.length - top.length} restantes)`} alPulsar={() => setMostrados(mostrados + POR_PAGINA)} />
      ) : null}
    </>
  );
}
