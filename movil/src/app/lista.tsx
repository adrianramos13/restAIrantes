// La ventana de «Idos» / «En tu lista» del Perfil (app.ventana_lista): esa lista con sus filtros.
import { router, Stack, useLocalSearchParams } from 'expo-router';

import { ListaFiltrable } from '@/components/lista_filtrable';
import { Info, Pantalla, TituloVentana } from '@/components/ui';
import { api, Yo } from '@/lib/api';
import { useCarga } from '@/lib/carga';

export default function VentanaLista() {
  const { cual } = useLocalSearchParams<{ cual?: string }>();
  const idos = cual === 'idos';
  const datos = useCarga(() => api<{ idos: number }>('GET', '/yo/datos'), []);
  const yo = useCarga(() => api<Yo>('GET', '/yo'), []);
  const vacia = idos ? datos.datos?.idos === 0 : yo.datos?.lista.total === 0;
  return (
    <Pantalla margen={22.5}>
      <Stack.Screen options={{ headerShown: false }} />
      <TituloVentana titulo={idos ? 'Restaurantes a los que has ido' : 'Tu lista'} alCerrar={() => router.back()} />
      {vacia && idos ? <Info>Todavía no has marcado ningún restaurante con «He ido» (está arriba en la ficha de cada uno).</Info> : null}
      {vacia && !idos ? <Info>Todavía no tienes restaurantes en tu lista. Añádela en tus ajustes (toca tu foto en el Perfil).</Info> : null}
      {vacia === false ? <ListaFiltrable de={idos ? 'idos' : 'lista'} /> : null}
    </Pantalla>
  );
}
