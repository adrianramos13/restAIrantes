// Cliente de la API (api/principal.py). La app nunca ve claves de Supabase: solo el token de tu sesión.
import * as SecureStore from 'expo-secure-store';

// En desarrollo: http://<IP del PC>:8787 (ver movil/.env). Al publicar, la URL de la API en internet.
const BASE = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8787';
const CLAVE_SESION = 'sesion';

export interface Sesion {
  correo: string;
  nombre: string | null;
  acceso: string;
  renovacion: string;
}

export interface Tarjeta {
  id: number;
  nombre: string;
  cocina: string;
  precio: string | null;
  nota: number | null;
  resenas: number | null;
  foto: string | null;
  cerrado: string | null;
  lat: number | null;
  lon: number | null;
  anadido_en: string | null;
  minutos?: number;
  puntuacion?: number;
  visita?: Visita;
}

export interface Visita {
  restaurante_id: number;
  nota: number | null;
  comentario: string | null;
  fecha: string | null;
  quien: string | null;
}

export interface Ficha extends Tarjeta {
  direccion: string | null;
  platos: string[];
  fotos: string[];
  en_mi_lista: boolean;
  en_eatlist: boolean;
  mi_visita: Visita | null;
  num_resenas: number;
  sobre_plato: string | null;
}

export interface Resena {
  nombre: string;
  alias: string | null;
  nota: number | null;
  comentario: string | null;
  fecha: string;
}

export interface Lugar {
  id: string;
  nombre: string;
  lat: number;
  lon: number;
  cocina: string | null;
  direccion: string | null;
  ciudad: string | null;
  telefono: string | null;
  web: string | null;
  estado: 'sin_analizar' | 'pendiente' | 'procesando' | 'analizado' | 'error' | 'cerrado' | null;
  restaurante_id: number | null;
  nota: number | null;
  foto: string | null;
}

export interface Preferencias {
  transporte: 'En coche' | 'A pie';
  tiempo: number;
  presupuesto: [number, number];
}

export interface Yo {
  correo: string;
  nombre: string;
  alias: string | null;
  foto: string | null;
  zona: string | null;
  preferencias: Preferencias;
  lista: { estado: string | null; mensaje: string | null; total: number };
  solicitudes: number;
  notificaciones: number;
  food_match: boolean;
  presupuesto_sin_limite: number;
}

/** Otra persona: nunca llega su correo, solo nombre, @alias y avatar. */
export interface Persona {
  alias: string;
  nombre: string;
  inicial: string;
  color: string;
  foto: string | null;
  estado?: 'nuevo' | 'amigo' | 'enviada' | 'recibida';
  motivo?: string;
}

export interface PerfilPersona extends Persona {
  afinidad?: number | null;
  nota_media?: number | null;
  ha_ido?: number;
  cocina_favorita?: string | null;
  valoraciones?: Tarjeta[];
  en_comun?: Tarjeta[];
  en_comun_total?: number;
  idos_los_dos?: number;
}

export interface Notificacion {
  de: Persona;
  restaurante_id: number;
  restaurante: string;
  fecha: string;
}

export interface Comensales {
  con: Persona[];
  pendientes: Persona[];
  te_anadio: Persona | null;
  opciones: Persona[];
}

export interface CartaMatch extends Tarjeta {
  localidad: string | null;
  fotos: string[];
  motivo: string | null;
  gusto: { perfiles: { nombre: string; inicial: string; color: string; foto: string | null }[]; mas: number } | null;
}

export interface Mazo {
  tarjetas: CartaMatch[];
  fin: boolean;
  con_zona: boolean;
}

export class ErrorApi extends Error {
  constructor(message: string, readonly estado: number) {
    super(message);
  }
}

// ----------------------- sesión guardada en el llavero del móvil -----------------------

let sesionActual: Sesion | null = null;
let alCaducar: (() => void) | null = null;

export async function cargarSesion(): Promise<Sesion | null> {
  const guardada = await SecureStore.getItemAsync(CLAVE_SESION);
  sesionActual = guardada ? (JSON.parse(guardada) as Sesion) : null;
  return sesionActual;
}

export async function guardarSesion(sesion: Sesion | null): Promise<void> {
  sesionActual = sesion;
  if (sesion) await SecureStore.setItemAsync(CLAVE_SESION, JSON.stringify(sesion));
  else await SecureStore.deleteItemAsync(CLAVE_SESION);
}

/** Lo que hay que hacer si la sesión ya no se puede renovar (volver a la pantalla de entrar). */
export function alCaducarSesion(funcion: () => void): void {
  alCaducar = funcion;
}

// ----------------------- peticiones -----------------------

type Metodo = 'GET' | 'POST' | 'PUT' | 'DELETE';
type Parametros = Record<string, string | number | boolean | string[] | undefined>;

function url(ruta: string, parametros?: Parametros): string {
  const q = new URLSearchParams();
  for (const [clave, valor] of Object.entries(parametros ?? {})) {
    if (valor === undefined || valor === '') continue;
    for (const v of Array.isArray(valor) ? valor : [valor]) q.append(clave, String(v));
  }
  const texto = q.toString();
  return `${BASE}${ruta}${texto ? `?${texto}` : ''}`;
}

async function enviar(metodo: Metodo, ruta: string, cuerpo?: unknown, parametros?: Parametros): Promise<Response> {
  try {
    return await fetch(url(ruta, parametros), {
      method: metodo,
      headers: {
        'Content-Type': 'application/json',
        ...(sesionActual ? { Authorization: `Bearer ${sesionActual.acceso}` } : {}),
      },
      body: cuerpo === undefined ? undefined : JSON.stringify(cuerpo),
    });
  } catch {
    throw new ErrorApi('No hay conexión con el servidor. Comprueba tu internet.', 0);
  }
}

async function renovar(): Promise<boolean> {
  if (!sesionActual) return false;
  const r = await enviar('POST', '/auth/renovar', { renovacion: sesionActual.renovacion });
  if (!r.ok) return false;
  await guardarSesion((await r.json()) as Sesion);
  return true;
}

async function mensajeDeError(r: Response): Promise<string> {
  try {
    const cuerpo = (await r.json()) as { detail?: unknown };
    if (typeof cuerpo.detail === 'string') return cuerpo.detail;
  } catch {
    // sin cuerpo JSON: mensaje genérico
  }
  return r.status === 422 ? 'Revisa los datos.' : 'No se ha podido hacer ahora mismo. Inténtalo en un momento.';
}

export async function api<T>(metodo: Metodo, ruta: string, cuerpo?: unknown, parametros?: Parametros): Promise<T> {
  let r = await enviar(metodo, ruta, cuerpo, parametros);
  if (r.status === 401 && sesionActual && !ruta.startsWith('/auth/')) {
    // el token de acceso dura ~1 h: se renueva con el de renovación y se repite la petición
    if (await renovar()) r = await enviar(metodo, ruta, cuerpo, parametros);
    else {
      await guardarSesion(null);
      alCaducar?.();
    }
  }
  if (!r.ok) throw new ErrorApi(await mensajeDeError(r), r.status);
  return (await r.json()) as T;
}

export function mensaje(error: unknown): string {
  return error instanceof Error ? error.message : 'Algo ha fallado. Inténtalo de nuevo.';
}
