// Barra de abajo, como la de la web (componentes/barra.*): Inicio, Comer hoy, Buscar y Perfil.
import { NativeTabs } from 'expo-router/native-tabs';

import { useColores } from '@/lib/tema';

export default function Pestanas() {
  const c = useColores();
  return (
    <NativeTabs backgroundColor={c.fondo} labelStyle={{ selected: { color: c.primario } }} tintColor={c.primario}>
      <NativeTabs.Trigger name="index">
        <NativeTabs.Trigger.Label>Inicio</NativeTabs.Trigger.Label>
        <NativeTabs.Trigger.Icon sf={{ default: 'house', selected: 'house.fill' }} md="home" />
      </NativeTabs.Trigger>
      <NativeTabs.Trigger name="comer">
        <NativeTabs.Trigger.Label>Comer hoy</NativeTabs.Trigger.Label>
        <NativeTabs.Trigger.Icon sf="fork.knife" md="restaurant" />
      </NativeTabs.Trigger>
      <NativeTabs.Trigger name="buscar">
        <NativeTabs.Trigger.Label>Buscar</NativeTabs.Trigger.Label>
        <NativeTabs.Trigger.Icon sf="magnifyingglass" md="search" />
      </NativeTabs.Trigger>
      <NativeTabs.Trigger name="perfil">
        <NativeTabs.Trigger.Label>Perfil</NativeTabs.Trigger.Label>
        <NativeTabs.Trigger.Icon sf={{ default: 'person.crop.circle', selected: 'person.crop.circle.fill' }} md="person" />
      </NativeTabs.Trigger>
    </NativeTabs>
  );
}
